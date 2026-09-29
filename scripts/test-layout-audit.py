#!/usr/bin/env python3
"""Offline checks for cue timing questions from Turkish alignment."""

import runpy
import json
import tempfile
import unittest
from pathlib import Path


AUDIT = runpy.run_path(str(Path(__file__).with_name("layout-audit.py")))
SEMANTIC = runpy.run_path(str(Path(__file__).with_name("semantic-review.py")))
ALIGNER = runpy.run_path(str(Path(__file__).with_name("align-turkish.py")))


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

    def test_material_timing_decision_is_bound_to_current_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            video = root / "video.webm"
            video.write_bytes(b"synthetic video identity")
            source, target = root / "tr.srt", root / "en.srt"
            source.write_text(
                "1\n00:00:01,000 --> 00:00:07,000\nGeldi.\n", encoding="utf-8")
            target.write_text(
                "1\n00:00:01,000 --> 00:00:07,000\nHe came.\n", encoding="utf-8")
            manifest_path = root / "map.json"
            manifest = SEMANTIC["prepare"](source, target, manifest_path)
            unit = manifest["utterances"][0]
            alignment_dir = root / "alignment"
            alignment_dir.mkdir()
            result = {
                "video_sha256": ALIGNER["digest"](video),
                "model": "synthetic", "audio_start_ms": 0,
                "audio_end_ms": 10_000,
                "input_sha256": ALIGNER["alignment_input"](
                    [unit], 0, 10_000, ALIGNER["digest"](video), "synthetic"
                ),
                "utterances": [{"id": unit["id"], "text": unit["text"],
                                "source_cue_ids": unit["cue_ids"],
                                "status": "aligned", "word_timings": [
                                    {"text": "Geldi.", "start_ms": 4000,
                                     "end_ms": 6500}] }],
            }
            (alignment_dir / "000.json").write_text(json.dumps(result), encoding="utf-8")
            report = root / "layout.json"
            AUDIT["run"](video, manifest_path, alignment_dir, report, 700, 25)
            self.assertTrue(AUDIT["layout_blockers"](report, manifest_path, video))
            self.assertFalse(AUDIT["needs_resolution"]({"kind": "fast_cue"}))
            audio = root / "original.wav"
            audio.write_bytes(b"synthetic audio fixture")
            decision_path = root / "decision.json"
            decisions = root / "timing-decisions.json"
            flags = json.loads(report.read_text())["flags"]
            decision_path.write_text(json.dumps({
                "findings": [AUDIT["decision_key"](flag) for flag in flags
                             if AUDIT["needs_resolution"](flag)],
                "disposition": "accepted_exception", "reviewer": "test agent",
                "reason": "Synthetic original-audio fixture supports the held display.",
                "evidence": [{"kind": "original_audio", "path": str(audio),
                              "sha256": SEMANTIC["digest"](audio)}],
            }), encoding="utf-8")
            AUDIT["adjudicate"](report, manifest_path, video,
                                decisions, decision_path)
            self.assertEqual(AUDIT["layout_blockers"](
                report, manifest_path, video, decisions), [])
            source.write_text(source.read_text().replace("00:00:01,000",
                                                       "00:00:02,000"),
                              encoding="utf-8")
            self.assertTrue(AUDIT["layout_blockers"](
                report, manifest_path, video, decisions))


if __name__ == "__main__":
    unittest.main()
