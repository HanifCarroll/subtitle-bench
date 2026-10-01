#!/usr/bin/env python3
"""Offline checks for source-linked translation drafts."""

import json
import runpy
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


SCRIPTS = Path(__file__).resolve().parent
TRANSLATE = runpy.run_path(str(SCRIPTS / "translate-subtitles.py"))
SEMANTIC = runpy.run_path(str(SCRIPTS / "semantic-review.py"))


class TranslationUnitTests(unittest.TestCase):
    def test_independent_english_layout_produces_linked_draft(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.srt"
            english = root / "english.srt"
            mapping = root / "utterances.json"
            output = root / "draft.json"
            source.write_text(
                "1\n00:00:01,000 --> 00:00:02,000\nMerhaba.\n\n"
                "2\n00:00:02,000 --> 00:00:03,000\nNasılsın?\n",
                encoding="utf-8")
            english.write_text(
                "1\n00:00:01,000 --> 00:00:03,000\nHello. How are you?\n",
                encoding="utf-8")
            manifest = SEMANTIC["prepare"](source, english, mapping)
            args = SimpleNamespace(source=source, output=output, utterance_map=mapping,
                                   source_language="tr", batch_size=15)
            calls = []

            def answer(prompt, context, max_tokens):
                calls.append(context)
                return json.dumps({"cues": [
                    {"id": 1, "text": "Hello."},
                    {"id": 2, "text": "How are you?"},
                ]}), {"test_tokens": 2}, {"choices": [{"finish_reason": "stop"}]}

            with patch.dict(TRANSLATE["translate"].__globals__,
                            {"request_translation": answer}):
                TRANSLATE["translate"](args)
            result = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(len(calls), 1)
            self.assertEqual(result["translations"], [
                {"source_ids": [manifest["utterances"][0]["id"]], "text": "Hello."},
                {"source_ids": [manifest["utterances"][1]["id"]],
                 "text": "How are you?"},
            ])
            self.assertEqual(english.read_text(encoding="utf-8").count("-->"), 1)
            self.assertTrue(output.with_suffix(".translation.json").is_file())

    def test_batch_coverage_context_and_byte_bound(self):
        cues = [{"id": n, "text": "Şekerim! " * 10} for n in range(1, 31)]
        jobs = list(TRANSLATE["batches"](cues, 20, 2000, "prompt"))
        self.assertEqual([row["id"] for _, _, context in jobs for row in context["target"]],
                         list(range(1, 31)))
        self.assertTrue(all(len(("prompt" + json.dumps(context, ensure_ascii=False)).encode()) <= 2000
                            for _, _, context in jobs))
        target = jobs[0][2]["target"]
        for rows in ([{"id": row["id"], "text": "Hi"} for row in target[:-1]],
                     [{"id": target[0]["id"], "text": "Hi"}] * len(target)):
            with self.assertRaises(ValueError):
                TRANSLATE["validate_translation"](rows, target)

    def test_concurrent_success_survives_invalid_batch_and_resumes_from_raw(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, output = root / "tr.srt", root / "en.srt"
            TRANSLATE["WRITE_SRT"](source, [{"start_ms": n * 2000, "end_ms": n * 2000 + 1000,
                                            "text": f"Turkish {n}"} for n in range(8)])
            args = SimpleNamespace(source=source, output=output, source_language="tr",
                                   batch_size=2, concurrency=4)
            active, peak, calls = 0, 0, []
            lock = threading.Lock()
            def answer(prompt, context, max_tokens):
                nonlocal active, peak
                with lock:
                    active += 1
                    peak = max(peak, active)
                    calls.append(context["target"][0]["id"])
                time.sleep(0.02)
                with lock:
                    active -= 1
                rows = [{"id": row["id"], "text": f"English {row['id']}"} for row in context["target"]]
                return json.dumps({"cues": rows}), {"total_tokens": 10}, {"choices": [{"finish_reason": "stop"}]}
            original = TRANSLATE["generate_batch"]
            def interrupted(*values):
                result = original(*values)
                if values[3]["target"][0]["id"] == 3:
                    raise RuntimeError("coordinator interrupted after raw response saved")
                return result
            with patch.dict(TRANSLATE["translate"].__globals__,
                            {"request_translation": answer, "generate_batch": interrupted}):
                with self.assertRaisesRegex(ValueError, "successful batches retained"):
                    TRANSLATE["translate"](args)
            self.assertGreater(peak, 1)
            saved = json.loads(output.with_suffix(".progress.json").read_text())
            self.assertEqual(len(saved["texts"]), 6)
            self.assertFalse(output.exists())
            # A stale later checkpoint must be rejected before an earlier pending call.
            key = max(saved["completed_batches"], key=int)
            valid_identity = saved["completed_batches"][key]
            saved["completed_batches"][key] = "stale"
            progress_path = output.with_suffix(".progress.json")
            progress_path.write_text(json.dumps(saved))
            with patch.dict(TRANSLATE["translate"].__globals__,
                            {"request_translation": lambda *_: self.fail("called provider before validating progress")}):
                with self.assertRaisesRegex(ValueError, "batch identity changed"):
                    TRANSLATE["translate"](args)
            saved["completed_batches"][key] = valid_identity
            progress_path.write_text(json.dumps(saved))
            # Resume the intact saved provider response; no response editing or new call.
            with patch.dict(TRANSLATE["translate"].__globals__,
                            {"request_translation": lambda *_: self.fail("called provider on resume")}):
                TRANSLATE["translate"](args)
            self.assertEqual(len(TRANSLATE["READ_CUES"](output)), 8)
            report = json.loads(output.with_suffix(".translation.json").read_text())
            self.assertFalse(report["semantic_approved"])
            self.assertEqual(report["status"], "provider_draft")
            self.assertEqual(len(calls), 4)

    def test_changed_source_and_prompt_cannot_reuse_progress(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, output = root / "tr.srt", root / "en.srt"
            source.write_text("1\n00:00:00,000 --> 00:00:01,000\nMerhaba.\n")
            args = SimpleNamespace(source=source, output=output, source_language="tr", batch_size=2)
            with patch.dict(TRANSLATE["translate"].__globals__,
                            {"request_translation": lambda *_: (_ for _ in ()).throw(RuntimeError("interrupted"))}):
                with self.assertRaises(ValueError):
                    TRANSLATE["translate"](args)
            args.max_output_tokens = 4096
            with self.assertRaisesRegex(ValueError, "another source or model"):
                TRANSLATE["translate"](args)
            args.max_output_tokens = 8192
            source.write_text(source.read_text().replace("Merhaba.", "Hayır."))
            with self.assertRaisesRegex(ValueError, "another source or model"):
                TRANSLATE["translate"](args)

    def test_provider_import_and_english_only_correction_survive_export(self):
        agent = runpy.run_path(str(SCRIPTS / "agent-translate.py"))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, output, progress = root / "tr.srt", root / "en.srt", root / "agent.json"
            source.write_text("1\n00:00:00,000 --> 00:00:01,000\nŞekerim.\n")
            args = SimpleNamespace(source=source, output=output, source_language="tr", batch_size=2)
            with patch.dict(TRANSLATE["translate"].__globals__, {"request_translation": lambda *_:
                    ('{"cues":[{"id":1,"text":"My sugar."}]}', {}, {"choices": [{"finish_reason": "stop"}]})}):
                TRANSLATE["translate"](args)
            record = agent["import_provider"](source, progress, output.with_suffix(".translation.json"))
            self.assertEqual(record["provider_draft"]["provider"], "deepseek")
            self.assertEqual(record["batches"], {})
            source_hash = agent["digest"](source)
            response = root / "correction.json"
            response.write_text(json.dumps({"source_sha256": source_hash,
                "progress_sha256": agent["digest"](progress), "reviewer": "Codex agent",
                "reason": "Affectionate address in the current dialogue.",
                "translations": [{"cue_id": 1, "text": "Sweetie."}]}))
            agent["import_responses"](source, progress, response, correction=True)
            for name in ("reviewed.en.srt", "reexport.en.srt"):
                report = agent["export"](source, progress, root / name)
                self.assertEqual(agent["READ_CUES"](root / name)[0]["text"], "Sweetie.")
                self.assertFalse(report["semantic_approved"])
            self.assertEqual(source_hash, agent["digest"](source))
            with self.assertRaisesRegex(ValueError, "checkpoint hash"):
                agent["import_responses"](source, progress, response, correction=True)

    def test_source_only_alignment_and_ready_checkpoint_reject_stale_inputs(self):
        align = runpy.run_path(str(SCRIPTS / "align-turkish.py"))
        review = runpy.run_path(str(SCRIPTS / "source-review.py"))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, video = root / "tr.srt", root / "video"
            source.write_text("1\n00:00:00,000 --> 00:00:01,000\nMerhaba.\n")
            video.write_bytes(b"video")
            with patch.dict(align["align"].__globals__, {"duration_ms": lambda _: 2000}):
                report = align["align"](video, source, root / "alignment", dry_run=True)
            self.assertEqual(report["windows"], 1)
            decision, checkpoint = root / "decision.json", root / "ready.json"
            values = {"source_sha256": review["FILE_HASH"](source), "reviewer": "Codex",
                      "reason": "Small source interval review complete", "evidence": [str(video)],
                      "remaining_source_work": [], "coverage_assessed": True,
                      "material_defects_repaired": True, "speech_timing_usable": True,
                      "ordinary_dialogue_review_complete": False}
            decision.write_text(json.dumps(values))
            with self.assertRaisesRegex(ValueError, "incomplete"):
                review["ready_checkpoint"](source, decision, checkpoint)
            values["ordinary_dialogue_review_complete"] = True
            decision.write_text(json.dumps(values))
            review["ready_checkpoint"](source, decision, checkpoint)
            review["check_ready"](source, checkpoint)
            source.write_text(source.read_text().replace("Merhaba.", "Hayır."))
            with self.assertRaisesRegex(ValueError, "stale"):
                review["check_ready"](source, checkpoint)


if __name__ == "__main__":
    unittest.main()
