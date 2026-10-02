#!/usr/bin/env python3
"""Offline regression for dynamic episode-wide Gemini review limits."""

import json
import runpy
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


SCRIPT = runpy.run_path(str(Path(__file__).with_name("gemini-audio-review.py")))
FULL = runpy.run_path(str(Path(__file__).with_name("gemini-full-audio.py")))


def write_json(path, value):
    path.write_text(json.dumps(value) + "\n", encoding="utf-8")


class FakeInteractions:
    def __init__(self):
        self.calls = []
        self.statuses = []

    def create(self, **request):
        self.calls.append(request)
        return SimpleNamespace(
            id=f"response-{len(self.calls)}",
            status=self.statuses.pop(0) if self.statuses else "completed",
            output_text='{"outcome":"relevant_speech"}',
            usage={"total_input_tokens": 600, "total_output_tokens": 80,
                   "total_thought_tokens": 120},
        )


class FakeFiles:
    def __init__(self):
        self.uploads = []
        self.deletions = []

    def upload(self, file):
        self.uploads.append(file)
        return SimpleNamespace(name=f"file-{len(self.uploads)}", uri="fake://audio",
                               mime_type="audio/wav")

    def delete(self, name):
        self.deletions.append(name)


class GeminiEpisodeBudgetTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.video = self.root / "episode.webm"
        self.video.write_bytes(b"episode")
        self.video_sha = SCRIPT["file_hash"](self.video)
        self.auth_path = self.root / "authorization.json"
        self.auth = {
            "status": "approved", "approval_source": "test human approval",
            "scope": {"provider": "google-gemini", "model": "gemini-3.8-flash",
                      "video": str(self.video), "video_sha256": self.video_sha},
            "aggregate_hard_limits": {
                "attempted_model_calls": 2, "audio_uploads": 1,
                "uploaded_audio_seconds_including_repeats": 20,
                "processed_audio_seconds_including_repeats": 40,
                "input_prompt_bytes": 10000,
                "max_clip_seconds": 20,
                "max_output_tokens_per_call": 4096,
                "estimated_charge_usd": 0.1,
            },
            "pricing": {"source": "https://ai.google.dev/gemini-api/docs/pricing",
                        "input_usd_per_million_tokens": 0.75,
                        "output_usd_per_million_tokens": 3.75},
        }
        write_json(self.auth_path, self.auth)
        self.client = SimpleNamespace(files=FakeFiles(), interactions=FakeInteractions())

    def plan(self, label):
        directory = self.root / label
        directory.mkdir()
        audio = directory / "clip.wav"
        audio.write_bytes(b"original audio " + label.encode())
        bundle_path = directory / "bundle.json"
        bundle = {
            "start_ms": 1000, "end_ms": 11000,
            "video_sha256": self.video_sha,
            "source_sha256": "a" * 64, "target_sha256": None,
            "timeline": [],
            "clips": [{"video_start_ms": 1000, "video_end_ms": 11000,
                       "audio_clip": str(audio),
                       "audio_sha256": SCRIPT["file_hash"](audio)}],
        }
        write_json(bundle_path, bundle)
        plan_path = directory / "plan.json"
        plan = {"kind": "two_stage_audio_review", "model": "gemini-3.8-flash",
                "max_audio_seconds": 10, "max_calls": 2,
                "max_output_tokens": 4096, "authorization": str(self.auth_path),
                "bundles": [{"id": label, "path": str(bundle_path),
                             "start_ms": 1000, "end_ms": 11000,
                             "video_sha256": self.video_sha,
                             "source_sha256": "a" * 64, "target_sha256": None}]}
        write_json(plan_path, plan)
        selected, _ = SCRIPT["two_stage_plan"](plan)
        return plan_path, plan, selected

    def run_plan(self, label):
        path, plan, selected = self.plan(label)
        budget = SCRIPT["EpisodeBudget"](self.auth_path, plan, selected)
        SCRIPT["two_stage_review"](self.client, path, plan, selected, budget)
        return path, plan, selected, budget

    def test_two_pass_review_counts_usage_and_blocks_new_scene(self):
        path, plan, selected, budget = self.run_plan("first")
        receipt = json.loads((path.parent / "gemini-two-stage/first.json").read_text())
        ledger = json.loads(budget.ledger_path.read_text())
        self.assertEqual("complete", receipt["status"])
        self.assertTrue(receipt["provider_file_deleted"])
        self.assertEqual(1, len(self.client.files.uploads))
        self.assertEqual(1, len(self.client.files.deletions))
        self.assertEqual(2, len(self.client.interactions.calls))
        self.assertEqual(["upload", "model_call", "model_call"],
                         [event["kind"] for event in ledger["events"]])
        self.assertTrue(all("usage" in event for event in ledger["events"][1:]))

        SCRIPT["two_stage_review"](self.client, path, plan, selected, budget)
        self.assertEqual(1, len(self.client.files.uploads))
        second_path, second_plan, second_selected = self.plan("second")
        second_budget = SCRIPT["EpisodeBudget"](
            self.auth_path, second_plan, second_selected)
        with self.assertRaisesRegex(ValueError, "aggregate limit reached"):
            SCRIPT["two_stage_review"](
                self.client, second_path, second_plan, second_selected, second_budget)
        self.assertEqual(1, len(self.client.files.uploads))

    def test_stops_before_a_second_call_and_deletes_the_uploaded_file(self):
        self.auth["aggregate_hard_limits"]["attempted_model_calls"] = 1
        write_json(self.auth_path, self.auth)
        path, plan, selected = self.plan("partial")
        budget = SCRIPT["EpisodeBudget"](self.auth_path, plan, selected)
        with self.assertRaisesRegex(ValueError, "aggregate limit reached"):
            SCRIPT["two_stage_review"](self.client, path, plan, selected, budget)
        receipt = json.loads((path.parent / "gemini-two-stage/partial.json").read_text())
        self.assertEqual("independent_complete", receipt["status"])
        self.assertTrue(receipt["provider_file_deleted"])
        self.assertEqual(1, len(self.client.interactions.calls))
        self.assertEqual(1, len(self.client.files.deletions))

    def test_changed_acoustic_question_cannot_reuse_completed_review(self):
        path, plan, selected, budget = self.run_plan("focus")
        plan["independent_focus"] = "Distinguish vocal articulation from instrumental melody."
        with self.assertRaisesRegex(ValueError, "Independent question changed"):
            SCRIPT["two_stage_review"](self.client, path, plan, selected, budget)
        self.assertEqual(1, len(self.client.files.uploads))
        self.assertEqual(2, len(self.client.interactions.calls))

    def test_cost_cap_stops_before_the_model_call(self):
        self.auth["aggregate_hard_limits"]["estimated_charge_usd"] = 0.0001
        write_json(self.auth_path, self.auth)
        path, plan, selected = self.plan("cost")
        budget = SCRIPT["EpisodeBudget"](self.auth_path, plan, selected)
        with self.assertRaisesRegex(ValueError, "aggregate limit reached"):
            SCRIPT["two_stage_review"](self.client, path, plan, selected, budget)
        self.assertEqual(1, len(self.client.files.uploads))
        self.assertEqual(1, len(self.client.files.deletions))
        self.assertEqual(0, len(self.client.interactions.calls))
        ledger = json.loads(budget.ledger_path.read_text())
        self.assertEqual(["upload"], [event["kind"] for event in ledger["events"]])

    def test_incomplete_scene_response_is_saved_but_not_accepted(self):
        self.client.interactions.statuses = ["incomplete"]
        path, plan, selected = self.plan("incomplete-scene")
        budget = SCRIPT["EpisodeBudget"](self.auth_path, plan, selected)
        with self.assertRaisesRegex(ValueError, "provider did not complete"):
            SCRIPT["two_stage_review"](
                self.client, path, plan, selected, budget)
        receipt = json.loads(
            (path.parent / "gemini-two-stage/incomplete-scene.json").read_text())
        self.assertEqual("independent_provider_incomplete", receipt["status"])
        self.assertEqual("incomplete", receipt["independent_provider_status"])
        self.assertTrue(receipt["provider_file_deleted"])
        self.assertEqual(1, len(self.client.interactions.calls))
        self.assertEqual(1, len(self.client.files.deletions))

    def test_incomplete_full_response_is_saved_but_not_accepted(self):
        self.auth["aggregate_hard_limits"]["full_episode_audio_seconds"] = 20
        write_json(self.auth_path, self.auth)
        audio = self.root / "full.mp3"
        audio.write_bytes(b"original full audio")
        plan_path = self.root / "full-plan.json"
        plan = {"kind": "full_episode_audio_observation",
                "model": "gemini-3.8-flash", "video": str(self.video),
                "video_sha256": self.video_sha, "duration_ms": 10000,
                "max_output_tokens": 4096, "authorization": str(self.auth_path)}
        write_json(plan_path, plan)
        selected = [("full-episode", plan_path,
                     {"video_sha256": self.video_sha,
                      "start_ms": 0, "end_ms": 10000}, audio)]
        budget = SCRIPT["EpisodeBudget"](
            self.auth_path, plan, selected, full_episode=True)
        self.client.interactions.statuses = ["incomplete"]
        with self.assertRaisesRegex(ValueError, "provider did not complete"):
            FULL["observe"](
                self.client, plan_path, plan, audio,
                {"audio_duration_ms": 10000}, budget)
        receipt = json.loads(
            (self.root / "full-episode-observation.json").read_text())
        self.assertEqual("provider_incomplete", receipt["status"])
        self.assertEqual("incomplete", receipt["provider_status"])
        self.assertTrue(receipt["provider_file_deleted"])
        self.assertEqual(1, len(self.client.interactions.calls))
        self.assertEqual(1, len(self.client.files.deletions))

    def test_rejects_another_video_and_unapproved_authorization(self):
        path, plan, selected = self.plan("scope")
        self.auth["status"] = "proposed"
        write_json(self.auth_path, self.auth)
        with self.assertRaisesRegex(ValueError, "does not cover"):
            SCRIPT["EpisodeBudget"](self.auth_path, plan, selected)
        self.auth["status"] = "approved"
        self.auth["scope"]["video_sha256"] = "b" * 64
        write_json(self.auth_path, self.auth)
        with self.assertRaisesRegex(ValueError, "does not cover"):
            SCRIPT["EpisodeBudget"](self.auth_path, plan, selected)


class FullEpisodeObservationTest(unittest.TestCase):
    def test_one_full_audio_pass_is_saved_and_cannot_repeat(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            video = root / "episode.webm"
            subprocess.run([
                "ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                "sine=frequency=440:duration=1", "-c:a", "libopus", str(video),
            ], check=True)
            video_sha = SCRIPT["file_hash"](video)
            duration_ms = FULL["audio_duration_ms"](video)
            auth_path = root / "authorization.json"
            write_json(auth_path, {
                "status": "approved", "approval_source": "test human approval",
                "scope": {"provider": "google-gemini", "model": "gemini-3.8-flash",
                          "video": str(video), "video_sha256": video_sha},
                "aggregate_hard_limits": {
                    "attempted_model_calls": 1, "audio_uploads": 1,
                    "uploaded_audio_seconds_including_repeats": 2,
                    "processed_audio_seconds_including_repeats": 2,
                    "input_prompt_bytes": 10000,
                    "max_clip_seconds": 1, "full_episode_audio_seconds": 2,
                    "max_output_tokens_per_call": 65536,
                    "estimated_charge_usd": 1.0,
                },
                "pricing": {"source": "https://ai.google.dev/gemini-api/docs/pricing",
                            "input_usd_per_million_tokens": 0.75,
                            "output_usd_per_million_tokens": 3.75},
            })
            plan_path = root / "full-plan.json"
            plan = {"kind": "full_episode_audio_observation",
                    "model": "gemini-3.8-flash", "video": str(video),
                    "video_sha256": video_sha, "duration_ms": duration_ms,
                    "max_output_tokens": 65536, "authorization": str(auth_path)}
            write_json(plan_path, plan)
            audio, identity, budget = FULL["prepare"](plan_path, plan)
            self.assertTrue(audio.is_file())
            self.assertEqual(SCRIPT["file_hash"](audio), identity["audio_sha256"])
            client = SimpleNamespace(files=FakeFiles(), interactions=FakeInteractions())
            receipt = FULL["observe"](client, plan_path, plan, audio, identity, budget)
            self.assertEqual("complete", receipt["status"])
            self.assertTrue(receipt["provider_file_deleted"])
            self.assertEqual(1, len(client.files.uploads))
            self.assertEqual(1, len(client.files.deletions))
            self.assertEqual(1, len(client.interactions.calls))
            ledger = json.loads(budget.ledger_path.read_text())
            self.assertEqual(2, len(ledger["events"]))
            self.assertEqual(["upload", "model_call"],
                             [event["kind"] for event in ledger["events"]])
            FULL["observe"](client, plan_path, plan, audio, identity, budget)
            self.assertEqual(1, len(client.interactions.calls))


if __name__ == "__main__":
    unittest.main()
