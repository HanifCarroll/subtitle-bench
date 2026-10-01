#!/usr/bin/env python3
"""Ensure paired revisions can replace read-only frozen input copies."""

import json
import os
import runpy
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parent
WORKBENCH = runpy.run_path(str(SCRIPTS / "subtitle-workbench.py"))
WRITE_SRT = runpy.run_path(str(SCRIPTS / "join-clip-drafts.py"))["write_srt"]
READ_CUES = runpy.run_path(str(SCRIPTS / "subtitle-timing.py"))["read_cues"]


class ReadOnlyPairTest(unittest.TestCase):
    def test_staged_replacement_preserves_before_and_after(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "working.tr.srt"
            target = root / "working.en.srt"
            WRITE_SRT(source, [{"start_ms": 1000, "end_ms": 2000,
                                "text": "Yanlış."}])
            WRITE_SRT(target, [{"start_ms": 1000, "end_ms": 2000,
                                "text": "Wrong."}])
            os.chmod(source, 0o444)
            os.chmod(target, 0o444)
            revised = ([{"start_ms": 1000, "end_ms": 2000,
                         "text": "Doğru."}],
                       [{"start_ms": 1000, "end_ms": 2000,
                         "text": "Correct."}])
            WORKBENCH["save_pair_revision"](
                root, {"duration_ms": 3000}, source, target, revised,
                {"start_ms": 1000, "end_ms": 2000, "reviewer": "test",
                 "reason": "synthetic staged-write test"},
            )
            self.assertEqual(READ_CUES(source)[0]["text"], "Doğru.")
            self.assertEqual(READ_CUES(target)[0]["text"], "Correct.")
            revision = next((root / "decisions").iterdir())
            self.assertEqual(READ_CUES(revision / "source-before.srt")[0]["text"],
                             "Yanlış.")
            self.assertEqual(READ_CUES(revision / "target-before.srt")[0]["text"],
                             "Wrong.")
            self.assertEqual(json.loads((revision / "decision.json").read_text())[
                "status"], "resolved")


if __name__ == "__main__":
    unittest.main()
