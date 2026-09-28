#!/usr/bin/env python3
"""Offline checks for the paid Google second-opinion workflow."""

import contextlib
import io
import json
import runpy
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


SCRIPT = runpy.run_path(str(Path(__file__).with_name("google-second-opinion.py")))
RUN = SCRIPT["run"]
GOOGLE_TRANSLATE = SCRIPT["google_translate"]


def write_srt(path, count, suffix):
    blocks = []
    for number in range(1, count + 1):
        start = number * 3
        blocks.append(
            f"{number}\n00:{start // 60:02}:{start % 60:02},000 --> "
            f"00:{(start + 1) // 60:02}:{(start + 1) % 60:02},000\n"
            f"Line {number} {suffix}\n"
        )
    path.write_text("\n".join(blocks), encoding="utf-8")


class SecondOpinionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        root = Path(self.directory.name)
        self.source = root / "source.srt"
        self.draft = root / "draft.srt"
        self.output = root / "review.json"
        write_srt(self.source, 101, "Turkish")
        write_srt(self.draft, 101, "English")
        self.args = SimpleNamespace(
            source=self.source, english_draft=self.draft, output=self.output,
            source_language="tr", google_project="test-project", run=False,
            max_source_characters=None,
        )

    def test_dry_run_and_cap_make_no_paid_request(self):
        with patch.dict(RUN.__globals__, {"google_translate": lambda *_: self.fail("paid call")}):
            with contextlib.redirect_stdout(io.StringIO()):
                RUN(self.args)
            self.assertFalse(self.output.exists())

            self.args.run = True
            self.args.max_source_characters = 1
            with self.assertRaisesRegex(ValueError, "max-source-characters"):
                RUN(self.args)

    def test_resume_keeps_cue_order_and_does_not_edit_draft(self):
        self.args.run = True
        self.args.max_source_characters = 100_000
        original_draft = self.draft.read_bytes()
        requests = []

        def first_attempt(cues, language, project):
            requests.append([cue["id"] for cue in cues])
            if len(requests) == 2:
                raise RuntimeError("simulated Google outage")
            return [f"Google {cue['id']}" for cue in cues]

        with patch.dict(RUN.__globals__, {"google_translate": first_attempt}):
            with contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(RuntimeError, "simulated"):
                    RUN(self.args)
        self.assertEqual(len(requests), 2)
        self.assertTrue(self.output.with_suffix(".progress.json").exists())

        def second_attempt(cues, language, project):
            requests.append([cue["id"] for cue in cues])
            return [f"Google {cue['id']}" for cue in cues]

        with patch.dict(RUN.__globals__, {"google_translate": second_attempt}):
            with contextlib.redirect_stdout(io.StringIO()):
                RUN(self.args)

        report = json.loads(self.output.read_text(encoding="utf-8"))
        self.assertEqual(requests[0], list(range(1, 101)))
        self.assertEqual(requests[2], [101])
        self.assertEqual(len(report["rows"]), 101)
        self.assertEqual(len(report["windows"]), 2)
        self.assertEqual(report["rows"][100]["google_nmt"], "Google 101")
        self.assertEqual(report["rows"][100]["english_draft"], "Line 101 English")
        self.assertEqual(self.draft.read_bytes(), original_draft)
        self.assertFalse(self.output.with_suffix(".progress.json").exists())

    def test_rejects_mismatched_timing_and_stale_checkpoint(self):
        draft_text = self.draft.read_text(encoding="utf-8")
        self.draft.write_text(draft_text.replace("00:00:03,000", "00:00:02,000", 1),
                              encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "timing differs"):
            RUN(self.args)

        self.draft.write_text(draft_text, encoding="utf-8")
        self.args.run = True
        self.args.max_source_characters = 100_000
        calls = 0

        def partial_attempt(cues, language, project):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("stop after first saved request")
            return [f"Google {cue['id']}" for cue in cues]

        with patch.dict(RUN.__globals__, {"google_translate": partial_attempt}):
            with self.assertRaises(RuntimeError):
                with contextlib.redirect_stdout(io.StringIO()):
                    RUN(self.args)

        # A checkpoint for different source bytes must not trigger another paid call.
        self.source.write_text(self.source.read_text(encoding="utf-8").replace(
            "Line 1 Turkish", "Changed 1 Turkish", 1), encoding="utf-8")
        with patch.dict(RUN.__globals__, {"google_translate": lambda *_: self.fail("paid call")}):
            with self.assertRaisesRegex(ValueError, "different inputs"):
                RUN(self.args)

    def test_google_response_keeps_one_result_per_source_cue(self):
        source = SCRIPT["READ_CUES"](self.source)[:2]
        response = {"data": {"translations": [
            {"translatedText": "I&#39;m ready"}, {"translatedText": "Go now"},
        ]}}
        requests = []

        def urlopen(request, timeout):
            requests.append(json.loads(request.data.decode("utf-8")))
            return io.BytesIO(json.dumps(response).encode("utf-8"))

        with patch("subprocess.run", return_value=SimpleNamespace(stdout="private-token")):
            with patch("urllib.request.urlopen", side_effect=urlopen):
                result = GOOGLE_TRANSLATE(source, "tr", "test-project")

        self.assertEqual(result, ["I'm ready", "Go now"])
        self.assertEqual(requests[0]["q"], [cue["text"] for cue in source])


if __name__ == "__main__":
    unittest.main()
