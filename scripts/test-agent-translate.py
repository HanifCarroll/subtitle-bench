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
            with self.assertRaisesRegex(ValueError, "another source version"):
                TRANSLATE["current"](source, progress, 1)


if __name__ == "__main__":
    unittest.main()
