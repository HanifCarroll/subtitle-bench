#!/usr/bin/env python3
"""Check source-bound, resumable agent translation batches."""

import json
import runpy
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parent
TRANSLATE = runpy.run_path(str(SCRIPTS / "agent-translate.py"))
WRITE_SRT = runpy.run_path(str(SCRIPTS / "join-clip-drafts.py"))["write_srt"]
READ_CUES = runpy.run_path(str(SCRIPTS / "subtitle-timing.py"))["read_cues"]


class AgentTranslateTest(unittest.TestCase):
    def test_checkpoint_export_and_source_change(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.tr.srt"
            progress = root / "progress.json"
            english = root / "english.en.srt"
            WRITE_SRT(source, [
                {"start_ms": 0, "end_ms": 1000, "text": "Merhaba."},
                {"start_ms": 1200, "end_ms": 2200, "text": "Nasılsın?"},
            ])
            for number, text in ((1, "Hello."), (2, "How are you?")):
                cues, saved = TRANSLATE["current"](source, progress, 1)
                request = TRANSLATE["batch_input"](cues, saved, number)
                response = root / f"batch-{number}.json"
                response.write_text(json.dumps({
                    "batch_number": number, "input_sha256": request["input_sha256"],
                    "reviewer": "fresh agent",
                    "translations": [{"cue_id": number, "text": text}],
                }), encoding="utf-8")
                TRANSLATE["apply"](source, progress, response)
                if number == 1:
                    with self.assertRaisesRegex(ValueError, "incomplete"):
                        TRANSLATE["export"](source, progress, english)
            report = TRANSLATE["export"](source, progress, english)
            self.assertEqual(report["cues"], 2)
            self.assertEqual([item["text"] for item in READ_CUES(english)],
                             ["Hello.", "How are you?"])
            WRITE_SRT(source, [{"start_ms": 0, "end_ms": 1000,
                                "text": "Changed Turkish."}])
            _, rebased = TRANSLATE["current"](source, progress, 1)
            self.assertEqual(rebased["translations"], {})
            self.assertEqual(rebased["cue_count"], 1)

    def test_defer_continue_partial_export_and_local_rebase(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.tr.srt"
            progress = root / "progress.json"
            original = [
                {"start_ms": index * 2000, "end_ms": index * 2000 + 1000,
                 "text": f"Turkish sentence {index + 1}."}
                for index in range(6)
            ]
            WRITE_SRT(source, original)
            for number in range(1, 7):
                cues, saved = TRANSLATE["current"](source, progress, 1)
                request = TRANSLATE["batch_input"](cues, saved, number)
                response = root / f"batch-{number}.json"
                row = ({"cue_id": number, "defer_reason": "Turkish words disputed"}
                       if number == 2 else
                       {"cue_id": number, "text": f"English sentence {number}."})
                response.write_text(json.dumps({
                    "batch_number": number, "input_sha256": request["input_sha256"],
                    "reviewer": "fresh agent", "translations": [row],
                }), encoding="utf-8")
                TRANSLATE["apply"](source, progress, response)

            partial = root / "working.partial.en.srt"
            report = TRANSLATE["export"](source, progress, partial, partial=True)
            self.assertEqual(report["untranslated_source_ids"], [2])
            self.assertEqual(report["status"], "partial")
            self.assertEqual(len(READ_CUES(partial)), 5)
            with self.assertRaisesRegex(ValueError, "incomplete"):
                TRANSLATE["export"](source, progress, root / "premature.en.srt")

            cues, saved = TRANSLATE["current"](source, progress, 1)
            request = TRANSLATE["batch_input"](cues, saved, 2)
            self.assertEqual(request["deferred_ids"], [2])
            resolved = root / "resolved-2.json"
            resolved.write_text(json.dumps({
                "batch_number": 2, "input_sha256": request["input_sha256"],
                "reviewer": "fresh agent", "translations": [
                    {"cue_id": 2, "text": "English sentence 2."}],
            }), encoding="utf-8")
            TRANSLATE["apply"](source, progress, resolved)
            final = root / "complete.en.srt"
            self.assertEqual(TRANSLATE["export"](source, progress, final)["status"],
                             "complete_draft")

            changed = list(original)
            changed[1] = {**changed[1], "text": "Repaired Turkish sentence 2."}
            WRITE_SRT(source, changed)
            _, rebased = TRANSLATE["current"](source, progress, 1)
            self.assertEqual(set(rebased["translations"]), {"5", "6"})
            self.assertEqual(len(rebased["history"]), 2)

            inserted = [{"start_ms": 0, "end_ms": 500, "text": "New opening."}]
            inserted.extend(changed)
            WRITE_SRT(source, inserted)
            _, shifted = TRANSLATE["current"](source, progress, 1)
            self.assertEqual(shifted["translations"]["6"], "English sentence 5.")
            self.assertEqual(shifted["translations"]["7"], "English sentence 6.")


if __name__ == "__main__":
    unittest.main()
