#!/usr/bin/env python3
"""Offline checks for cue timing questions from Turkish alignment."""

import runpy
import unittest
from pathlib import Path


AUDIT = runpy.run_path(str(Path(__file__).with_name("layout-audit.py")))


class LayoutAuditTests(unittest.TestCase):
    def test_early_tail_gap_and_missing_link_are_review_flags(self):
        manifest = {"utterances": [
            {"id": "u1", "text": "Merhaba.", "start_ms": 1000,
             "end_ms": 4000},
            {"id": "u2", "text": "Nasılsın?", "start_ms": 6500,
             "end_ms": 7500},
            {"id": "u3", "text": "Evet.", "start_ms": 8000,
             "end_ms": 9000},
        ], "translations": [
            {"id": "t1", "text": "Hello. How are you?", "start_ms": 1000,
             "end_ms": 7500, "source_ids": ["u1", "u2"]},
        ]}
        results = {"u1": {"word_timings": [
            {"start_ms": 2000, "end_ms": 2500}]},
            "u2": {"word_timings": [
                {"start_ms": 6600, "end_ms": 7000}]}}
        flags = AUDIT["audit"](manifest, results, set())
        kinds = {flag["kind"] for flag in flags}
        self.assertIn("possible_early_cue", kinds)
        self.assertIn("possible_lingering_cue", kinds)
        self.assertIn("translation_spans_dialogue_gap", kinds)
        self.assertIn("missing_english_link", kinds)
        self.assertIn("missing_word_timing", kinds)
        self.assertEqual(manifest["utterances"][0]["start_ms"], 1000)


if __name__ == "__main__":
    unittest.main()
