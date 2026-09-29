#!/usr/bin/env python3
"""Ensure a local evidence route is traceable and never claims hearing."""

import json
import runpy
import tempfile
import unittest
from pathlib import Path


SOURCE = runpy.run_path(str(Path(__file__).with_name("source-review.py")))
LOCAL = runpy.run_path(str(Path(__file__).with_name("local-audio-review.py")))
WRITE_SRT = runpy.run_path(str(Path(__file__).with_name("join-clip-drafts.py")))["write_srt"]


class LocalAudioReviewTest(unittest.TestCase):
    def test_receipt_is_built_from_current_whisper_and_qwen_runs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            video = root / "video.webm"
            video.write_bytes(b"video")
            video_hash = SOURCE["FILE_HASH"](video)
            source = root / "source.srt"
            WRITE_SRT(source, [{"start_ms": 100, "end_ms": 900,
                                "text": "Merhaba."}])
            transcription = root / "transcription"
            transcription.mkdir()
            model = root / "model.bin"
            model.write_bytes(b"test model")
            whisper_srt = transcription / "000.srt"
            WRITE_SRT(whisper_srt, [{"start_ms": 100, "end_ms": 900,
                                     "text": "Merhaba."}])
            clip = {"srt": str(whisper_srt), "core_start_ms": 0,
                    "core_end_ms": 1000, "offset_ms": 0}
            (transcription / "000.complete.json").write_text(json.dumps({
                "srt_sha256": SOURCE["FILE_HASH"](whisper_srt),
                "clip": {key: clip[key] for key in
                         ("core_start_ms", "core_end_ms", "offset_ms")},
            }), encoding="utf-8")
            (transcription / "run.json").write_text(json.dumps({
                "video": str(video), "video_sha256": video_hash,
                "language": "tr", "model": str(model),
                "model_sha256": SOURCE["FILE_HASH"](model),
            }), encoding="utf-8")
            (transcription / "manifest.json").write_text(json.dumps({
                "video": str(video), "clips": [clip],
            }), encoding="utf-8")
            (transcription / "joined").mkdir()
            (transcription / "joined/manifest.sha256").write_text(
                SOURCE["FILE_HASH"](transcription / "manifest.json") + "\n",
                encoding="utf-8",
            )
            audio_report = root / "audio-check.json"
            audio_report.write_text(json.dumps({
                "video_sha256": video_hash,
                "source_sha256": SOURCE["FILE_HASH"](source),
                "language": "Turkish", "model": "qwen3-asr",
                "model_revision": "pinned-qwen-revision",
                "windows": [{"start_ms": 0, "end_ms": 1000,
                             "status": "complete", "text": "Merhaba."}],
            }), encoding="utf-8")
            decision = root / "decision.json"
            decision.write_text(json.dumps({
                "status": "supported", "reviewer": "fresh agent",
                "reason": "Two independent local outputs support this short cue.",
                "heard_original_audio": False,
            }), encoding="utf-8")
            result = LOCAL["create"](video, source, 100, 900, transcription,
                                      audio_report, decision, root / "result.json")
            self.assertEqual(result["route"], "local_asr_agent")
            self.assertTrue((root / "result.whisper.json").is_file())
            self.assertTrue((root / "result.qwen.json").is_file())
            qwen = json.loads(audio_report.read_text(encoding="utf-8"))
            qwen["windows"][0]["status"] = "questionable"
            audio_report.write_text(json.dumps(qwen), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unusable window"):
                LOCAL["create"](video, source, 100, 900, transcription,
                                audio_report, decision, root / "second-result.json")

    def test_two_distinct_local_receipts_and_agent_assessment(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name, text in (("whisper.json", '{"text":"Merhaba"}'),
                               ("qwen.json", '{"text":"Merhaba"}')):
                (root / name).write_text(text, encoding="utf-8")
            result = {
                "route": "local_asr_agent", "video_sha256": "video",
                "source_interval_sha256": "interval",
                "start_ms": 0, "end_ms": 1000, "status": "supported",
                "observations": [
                    {"method": "local_asr", "model": model,
                     "model_version": "pinned-test-revision", "video_sha256": "video",
                     "start_ms": 0, "end_ms": 1000, "raw_response": name,
                     "raw_response_sha256": SOURCE["FILE_HASH"](root / name)}
                    for model, name in (("whisper-large-v3", "whisper.json"),
                                        ("qwen3-asr", "qwen.json"))
                ],
                "agent_assessment": {
                    "reviewer": "fresh agent", "reason": "Two independent outputs support the cue.",
                    "heard_original_audio": False,
                },
            }

            def check():
                (root / "review.json").write_text(json.dumps(result), encoding="utf-8")
                return SOURCE["review_result_blockers"](
                    root, "review.json", 100, 900, "video", "source", "interval"
                )

            self.assertEqual(check(), [])
            result["observations"][1]["model"] = "whisper-large-v3"
            self.assertIn("distinct", " ".join(check()))
            result["observations"][1]["model"] = "qwen3-asr"
            result["observations"][1]["raw_response_sha256"] = "stale"
            self.assertIn("stale", " ".join(check()))
            result["observations"][1]["raw_response_sha256"] = SOURCE["FILE_HASH"](
                root / "qwen.json"
            )
            result["agent_assessment"]["heard_original_audio"] = True
            self.assertIn("honest", " ".join(check()))


if __name__ == "__main__":
    unittest.main()
