#!/usr/bin/env python3
"""Portable regressions for reference selection and resumable transcription."""

import json
import runpy
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch


SCRIPTS = Path(__file__).resolve().parent
REFERENCE = runpy.run_path(str(SCRIPTS / "reference-source.py"))
TRANSCRIBE = runpy.run_path(str(SCRIPTS / "transcribe-video.py"))
QUALIFICATION = runpy.run_path(str(SCRIPTS / "qualification-runner.py"))
WRITE_SRT = runpy.run_path(str(SCRIPTS / "join-clip-drafts.py"))["write_srt"]


class ProductionPathsTest(unittest.TestCase):
    def test_reference_proposal_needs_consistent_full_cut_anchors(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            video = root / "video.webm"
            video.write_bytes(b"test video identity")
            transcript = root / "asr.srt"
            reference = root / "source.srt"
            draft_cues, reference_cues = [], []
            for index in range(30):
                start = 10_000 + index * 120_000
                text = f"Distinct Turkish dialogue sentence number {index:02d}."
                draft_cues.append({"start_ms": start, "end_ms": start + 1500,
                                   "text": text})
                reference_cues.append({"start_ms": start + 5000,
                                       "end_ms": start + 6500, "text": text})
            WRITE_SRT(transcript, draft_cues)
            WRITE_SRT(reference, reference_cues)
            with patch.dict(REFERENCE["propose"].__globals__,
                            {"duration_ms": lambda _: 3_600_000}):
                result = REFERENCE["propose"](
                    video, transcript, reference, root / "aligned"
                )
            self.assertEqual(result["status"], "timing_proposal")
            self.assertTrue(all(result["checks"].values()))
            self.assertEqual(result["alignment"]["offset_ms"], 5000)
            self.assertEqual(json.loads((root / "aligned/report.json").read_text())
                             ["candidate_sha256"], result["candidate_sha256"])

            for index, cue in enumerate(reference_cues):
                cue["start_ms"] += (index // 10) * 2500
                cue["end_ms"] += (index // 10) * 2500
            WRITE_SRT(reference, reference_cues)
            with patch.dict(REFERENCE["propose"].__globals__,
                            {"duration_ms": lambda _: 3_600_000}):
                changed = REFERENCE["propose"](
                    video, transcript, reference, root / "drifting"
                )
            self.assertEqual(changed["status"], "insufficient_timing_evidence")
            self.assertIsNone(changed["candidate"])

    def test_clip_resume_requires_a_matching_completion_receipt(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "clips").mkdir()
            clip = {"offset_ms": 0, "core_start_ms": 0,
                    "core_end_ms": 1000, "audio_end_ms": 1000}
            srt = root / "clips/000.srt"
            srt.write_text("partial", encoding="utf-8")

            def fake_run(command, **_):
                if command[0] == "ffmpeg":
                    Path(command[-1]).write_bytes(b"audio")
                else:
                    prefix = Path(command[command.index("-of") + 1])
                    WRITE_SRT(prefix.with_suffix(".srt"), [
                        {"start_ms": 0, "end_ms": 500, "text": "Merhaba."}
                    ])

            with patch.object(TRANSCRIBE["run_clip"].__globals__["subprocess"],
                              "run", side_effect=fake_run):
                result = TRANSCRIBE["run_clip"](
                    clip, 0, root, root / "video.webm", "tr",
                    root / "model.bin", None, "ffmpeg", "whisper-cli"
                )
            self.assertEqual(result, srt)
            receipt = root / "clips/000.complete.json"
            self.assertTrue(receipt.exists())
            with patch.object(TRANSCRIBE["run_clip"].__globals__["subprocess"],
                              "run", side_effect=AssertionError("ran again")):
                TRANSCRIBE["run_clip"](clip, 0, root, root / "video.webm", "tr",
                                       root / "model.bin", None, "ffmpeg", "whisper-cli")
            srt.write_text("changed", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Completed clip changed"):
                TRANSCRIBE["run_clip"](clip, 0, root, root / "video.webm", "tr",
                                       root / "model.bin", None, "ffmpeg", "whisper-cli")

    def test_qualification_run_rejects_changed_inputs_on_resume(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            video = root / "video.webm"
            video.write_bytes(b"first video")
            workflow = root / "workflow.md"
            workflow.write_text("frozen", encoding="utf-8")
            model = root / "model.bin"
            model.write_bytes(b"frozen model")
            freeze = root / "freeze.json"
            freeze.write_text(json.dumps({
                "version": 1,
                "workflow_sha256": {"workflow.md": QUALIFICATION["digest"](workflow)},
                "model_files": [{"path": str(model),
                                 "sha256": QUALIFICATION["digest"](model)}],
            }), encoding="utf-8")
            args = Namespace(episode_id="heldout", mode="video_only", video=video,
                             output=root / "run", source=None, english=None)
            loader = QUALIFICATION["load_freeze"]
            with patch.dict(QUALIFICATION["start"].__globals__,
                            {"ROOT": root, "FREEZE": freeze,
                             "load_freeze": lambda: loader(freeze)}):
                QUALIFICATION["start"](args)
                QUALIFICATION["start"](args)
                video.write_bytes(b"changed video")
                with self.assertRaisesRegex(ValueError, "different inputs"):
                    QUALIFICATION["start"](args)


if __name__ == "__main__":
    unittest.main()
