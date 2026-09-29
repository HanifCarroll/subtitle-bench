#!/usr/bin/env python3
"""Offline regression for binding a saved audio review to current subtitles."""

import hashlib
import json
import runpy
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parent
BINDER = runpy.run_path(str(SCRIPTS / "bind-gemini-review.py"))
SOURCE = runpy.run_path(str(SCRIPTS / "source-review.py"))
GEMINI = runpy.run_path(str(SCRIPTS / "gemini-audio-review.py"))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value) + "\n", encoding="utf-8")


class BindGeminiReviewTest(unittest.TestCase):
    def test_prose_wrapped_single_json_fence_can_be_parsed_without_another_call(self):
        raw = 'Observation follows.\n```json\n{"label":"relevant_speech"}\n```\n'
        self.assertEqual(GEMINI["parsed_response"](raw),
                         {"label": "relevant_speech"})
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            GEMINI["parsed_response"](raw + raw)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.case = self.root / "case"
        self.case.mkdir()
        self.working = self.case / "working.tr.srt"
        self.working.write_text(
            "1\n00:00:10,000 --> 00:00:20,000\nAday sözler.\n",
            encoding="utf-8",
        )
        self.video_hash = "a" * 64
        save(self.case / "case.json", {
            "video_sha256": self.video_hash, "language": "tr",
        })
        self.clip = self.root / "original.wav"
        self.clip.write_bytes(b"synthetic audio evidence")
        self.bundle = self.root / "bundle.json"
        save(self.bundle, {
            "video_sha256": self.video_hash,
            "source_sha256": "b" * 64,
            "clips": [{"audio_clip": str(self.clip),
                       "audio_sha256": digest(self.clip)}],
        })
        self.receipt = self.root / "provider.json"
        provider = {
            "provider": "google-gemini", "status": "complete",
            "provider_file_deleted": True, "model_calls_attempted": 2,
            "video_sha256": self.video_hash, "source_sha256": "b" * 64,
            "start_ms": 0, "end_ms": 30000,
            "bundle": str(self.bundle), "bundle_sha256": digest(self.bundle),
            "clip_sha256": digest(self.clip), "model": "gemini-3.8-flash",
            "prompt_version": "test-v1",
        }
        for stage in ("independent", "comparison"):
            raw = self.root / f"{stage}.txt"
            prompt = self.root / f"{stage}-prompt.txt"
            raw.write_text('{"label":"music_without_relevant_words"}',
                           encoding="utf-8")
            prompt.write_text("Assess original audio.", encoding="utf-8")
            provider.update({
                f"{stage}_raw_response": str(raw),
                f"{stage}_raw_sha256": digest(raw),
                f"{stage}_prompt": str(prompt),
                f"{stage}_prompt_sha256": digest(prompt),
                f"{stage}_response_id": stage + "-response",
                f"{stage}_parsed": {"label": "music_without_relevant_words"},
            })
        save(self.receipt, provider)

    def bind(self, name):
        return BINDER["bind"](
            self.receipt, self.case, 10000, 20000,
            "model_artifact", "music_without_relevant_words",
            "test reviewer", "Music and no words in approved interval.",
            self.case / name,
        )

    def test_saved_receipts_bind_to_current_source_interval(self):
        result = self.bind("review.json")
        self.assertFalse(result["heard_original_audio"])
        self.assertEqual(result["provider_compared_source_sha256"], "b" * 64)
        interval_hash = SOURCE["source_interval_sha256"](
            SOURCE["READ_CUES"](self.working), 10000, 20000)
        self.assertEqual([], SOURCE["review_result_blockers"](
            self.case, "review.json", 10000, 20000,
            self.video_hash, digest(self.working), interval_hash))

    def test_rejects_tampered_audio_and_provider_response(self):
        self.clip.write_bytes(b"different audio")
        with self.assertRaisesRegex(ValueError, "clip or compared candidate changed"):
            self.bind("bad-clip.json")
        self.clip.write_bytes(b"synthetic audio evidence")
        (self.root / "independent.txt").write_text("changed", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "response is missing or changed"):
            self.bind("bad-response.json")

    def test_rejects_incomplete_provider_cleanup_and_outside_interval(self):
        provider = json.loads(self.receipt.read_text())
        provider["provider_file_deleted"] = False
        save(self.receipt, provider)
        with self.assertRaisesRegex(ValueError, "incomplete or outside"):
            self.bind("undeleted.json")
        provider["provider_file_deleted"] = True
        provider["end_ms"] = 15000
        save(self.receipt, provider)
        with self.assertRaisesRegex(ValueError, "incomplete or outside"):
            self.bind("short.json")


if __name__ == "__main__":
    unittest.main()
