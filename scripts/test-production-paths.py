#!/usr/bin/env python3
"""Portable regressions for reference selection and resumable transcription."""

import json
import runpy
import tempfile
import sys
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch, MagicMock


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

    def test_whisper_zero_duration_preserves_raw_and_flags_provisional_timing(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "clips").mkdir()
            clip = {"offset_ms": 0, "core_start_ms": 0, "core_end_ms": 1000, "audio_end_ms": 1000}
            def fake_run(command, **_):
                if command[0] == "ffmpeg":
                    Path(command[-1]).write_bytes(b"audio")
                else:
                    prefix = Path(command[command.index("-of") + 1])
                    prefix.with_suffix(".srt").write_text("1\n00:00:00,500 --> 00:00:00,500\nAh.\n")
            with patch.object(TRANSCRIBE["run_clip"].__globals__["subprocess"], "run", side_effect=fake_run):
                TRANSCRIBE["run_clip"](clip, 0, root, root / "video", "tr", root / "model", None, "ffmpeg", "whisper")
            self.assertIn("00:00:00,500 --> 00:00:00,500", (root / "clips/000.raw.srt").read_text())
            self.assertIn("00:00:00,500 --> 00:00:00,501", (root / "clips/000.srt").read_text())
            self.assertEqual(len(json.loads((root / "clips/000.complete.json").read_text())["provisional_timing_fixes"]), 1)

    def test_gemini_profile_plans_tested_chunks_without_upload(self):
        gemini = runpy.run_path(str(SCRIPTS / "gemini-chunks.py"))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            video = root / "video.webm"
            video.write_bytes(b"video")
            with patch.dict(gemini["TRANSCRIBE"], {"video_duration": lambda *_: 610000}):
                result = gemini["transcribe"](video, root / "run", None)
            self.assertEqual(result["clips"], 3)
            self.assertEqual(result["settings"]["overlap_ms"], 5000)
            self.assertEqual(result["settings"]["max_output_tokens"], 32768)
            self.assertEqual(gemini["parse_transcript"]("00:01.250 --> 00:02.500 | Merhaba.", 10000)[0]["start_ms"], 1250)
            for invalid in ("summary only", "00:01.000 --> 00:01.000 | Ah.", "00:01.000 --> 00:12.000 | Ah."):
                with self.assertRaises(ValueError):
                    gemini["parse_transcript"](invalid, 10000)

    def test_gemini_incomplete_response_is_saved_and_deleted(self):
        gemini = runpy.run_path(str(SCRIPTS / "gemini-chunks.py"))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            video = root / "video"
            video.write_bytes(b"video")
            client = MagicMock()
            client.files.upload.return_value.name = "remote-file"
            client.files.get.return_value.name = "remote-file"
            client.files.get.return_value.state.name = "ACTIVE"
            result = client.interactions.create.return_value
            result.model_dump.return_value = {"status": "incomplete", "outputs": []}
            result.output_text = "00:01.000 --> 00:02.000 | Merhaba."
            result.usage.model_dump.return_value = {"total_output_tokens": 10}
            fake_genai = MagicMock()
            fake_genai.Client.return_value = client
            budget = MagicMock()
            budget.sha256 = "auth"
            def extract(_, __, audio):
                audio.write_bytes(b"audio")
            with patch.dict(sys.modules, {"google": MagicMock(genai=fake_genai),
                                          "google.genai": fake_genai}), \
                 patch.dict(gemini["TRANSCRIBE"], {"video_duration": lambda *_: 10000}), \
                 patch.dict(gemini["REVIEW"], {"EpisodeBudget": lambda *_: budget, "extract_audio": extract}):
                with self.assertRaisesRegex(ValueError, "provider response is incomplete"):
                    gemini["transcribe"](video, root / "run", root / "auth.json", apply=True)
            receipt = json.loads((root / "run/clips/000.json").read_text())
            self.assertEqual(receipt["provider_status"], "incomplete")
            self.assertEqual(receipt["provider_file_deletion"], "deleted")
            self.assertFalse((root / "run/clips/000.srt").exists())
            client.files.delete.assert_called_once_with(name="remote-file")

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
