#!/usr/bin/env python3
"""Offline approval and credential checks for the bounded Scribe trial."""

import json
import os
import runpy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


TRIAL = runpy.run_path(str(Path(__file__).with_name("elevenlabs-scribe-trial.py")))


class ScribeTrialTests(unittest.TestCase):
    def test_three_clip_cap_and_private_receipts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundles = []
            for number, interval in enumerate(((1000, 2000), (3000, 4000),
                                               (5000, 6000)), start=1):
                audio = root / f"clip-{number}.wav"
                audio.write_bytes(b"synthetic audio")
                bundle_path = root / f"bundle-{number}.json"
                bundle_path.write_text(json.dumps({
                    "start_ms": interval[0], "end_ms": interval[1],
                    "video_sha256": f"video-{number}",
                    "clips": [{"video_start_ms": interval[0],
                               "video_end_ms": interval[1],
                               "audio_clip": str(audio),
                               "audio_sha256": TRIAL["digest"](audio)}]}))
                bundles.append({"id": f"case-{number}", "path": str(bundle_path),
                                "start_ms": interval[0], "end_ms": interval[1],
                                "video_sha256": f"video-{number}"})
            plan = root / "plan.json"
            data = {"model": "scribe_v2", "max_calls": 3,
                    "max_audio_seconds": 90, "max_cost_usd": 5,
                    "bundles": bundles}
            plan.write_text(json.dumps(data))
            output = root / "receipts"
            self.assertEqual(TRIAL["run"](plan, output)["audio_seconds"], 3)
            self.assertFalse(output.exists())

            key_file = root / "key.env"
            key_file.write_text("ELEVENLABS_API_KEY=private-test-key\n")
            os.chmod(key_file, 0o600)
            calls = []

            def recognize(audio, key):
                calls.append((audio.name, key))
                return {"text": "test", "words": [],
                        "transcription_id": audio.stem}

            deleted = []

            def delete_transcript(transcription_id, key):
                deleted.append((transcription_id, key))
                return {"status": "deleted"}

            with patch.dict(TRIAL["run"].__globals__,
                            {"recognize": recognize,
                             "delete_transcript": delete_transcript}):
                TRIAL["run"](plan, output, key_file)
                TRIAL["run"](plan, output, key_file)
            self.assertEqual(len(calls), 3)
            self.assertEqual(len(deleted), 3)
            self.assertEqual(len(list(output.glob("*.json"))), 3)
            self.assertNotIn("private-test-key", (output / "case-1.json").read_text())
            self.assertEqual((output / "case-1.json").stat().st_mode & 0o777, 0o600)
            self.assertEqual(json.loads((output / "case-1.json").read_text())[
                "remote_cleanup"]["status"], "deleted")

            data["bundles"][2]["end_ms"] = 100_000
            plan.write_text(json.dumps(data))
            with self.assertRaises(ValueError):
                TRIAL["run"](plan, output)


if __name__ == "__main__":
    unittest.main()
