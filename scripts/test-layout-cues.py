#!/usr/bin/env python3
"""Offline checks for independent, speech-preserving cue layout."""

import json
import runpy
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parent
LAYOUT = runpy.run_path(str(SCRIPTS / "layout-cues.py"))
SEMANTIC = runpy.run_path(str(SCRIPTS / "semantic-review.py"))


class LayoutTests(unittest.TestCase):
    def test_split_long_hold_and_keep_following_dialogue(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.srt"
            english = root / "english.srt"
            mapping = root / "map.json"
            source.write_text(
                "1\n00:00:01,000 --> 00:00:42,000\nAyyy!\n", encoding="utf-8")
            english.write_text(
                "1\n00:00:01,000 --> 00:00:42,000\nAyyy!\n", encoding="utf-8")
            manifest = SEMANTIC["prepare"](source, english, mapping)
            manifest["utterances"] = [
                {**manifest["utterances"][0], "id": "cry", "end_ms": 5000},
                {**manifest["utterances"][0], "id": "reply", "text": "Buradayım.",
                 "start_ms": 6000, "end_ms": 8000},
            ]
            manifest["translations"] = [
                {**manifest["translations"][0], "id": "cry-en", "source_ids": ["cry"],
                 "end_ms": 5000},
                {**manifest["translations"][0], "id": "reply-en",
                 "source_ids": ["reply"], "text": "I'm here.",
                 "start_ms": 6000, "end_ms": 8000},
            ]
            mapping.write_text(json.dumps(manifest), encoding="utf-8")
            report = LAYOUT["render"](
                mapping, root / "draft.tr.srt", root / "draft.en.srt",
                root / "layout.json")
            self.assertEqual(report["source_cues"], 2)
            self.assertEqual(report["english_cues"], 2)
            self.assertIn("Buradayım.", (root / "draft.tr.srt").read_text())
            self.assertNotIn("00:00:42,000", (root / "draft.tr.srt").read_text())

    def test_one_english_cue_can_cover_two_source_utterances(self):
        units = [
            {"id": "u1", "text": "Merhaba.", "start_ms": 1000, "end_ms": 2000,
             "alignment_status": "aligned"},
            {"id": "u2", "text": "Nasılsın?", "start_ms": 2000, "end_ms": 3000,
             "alignment_status": "aligned"},
        ]
        translations = [{"id": "t1", "text": "Hello. How are you?",
                         "source_ids": ["u1", "u2"], "start_ms": 1000,
                         "end_ms": 3000, "link_status": "confirmed"}]
        source, english, report = LAYOUT["layout"]({
            "utterances": units, "translations": translations})
        self.assertEqual((len(source), len(english)), (2, 1))
        self.assertEqual(report["provisional_links"], [])

    def test_missing_translation_blocks_layout(self):
        with self.assertRaisesRegex(ValueError, "lack English"):
            LAYOUT["layout"]({"utterances": [{"id": "u1", "text": "Hey.",
                "start_ms": 1000, "end_ms": 2000,
                "alignment_status": "unreviewed"}], "translations": []})


if __name__ == "__main__":
    unittest.main()
