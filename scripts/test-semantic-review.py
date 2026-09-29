#!/usr/bin/env python3
"""Offline semantic binding, adjudication, and cache regressions."""

import json
import runpy
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SEMANTIC = runpy.run_path(str(ROOT / "semantic-review.py"))
LAYOUT = runpy.run_path(str(ROOT / "layout-cues.py"))


def srt(path, texts):
    blocks = []
    for number, text in enumerate(texts, 1):
        blocks.append(f"{number}\n00:00:{number:02d},000 --> "
                      f"00:00:{number + 1:02d},000\n{text}")
    path.write_text("\n\n".join(blocks) + "\n", encoding="utf-8")


def batch(manifest, output, verdicts, model="synthetic-test", size=12):
    output.mkdir(exist_ok=True)
    for number, selected, related, context in SEMANTIC["groups"](manifest, size):
        inputs = SEMANTIC["review_input"](selected, related, context, [])
        identity = SEMANTIC["fingerprint"]({
            "model": model, "prompt": SEMANTIC["PROMPT"], "input": inputs,
        })
        assessments = []
        for item in selected:
            verdict = verdicts.get(item["id"], "correct")
            assessment = {"source_id": item["id"], "verdict": verdict}
            if verdict != "correct":
                assessment["audio_needed"] = False
            assessments.append(assessment)
        response = {"message": {"content": json.dumps({
            "assessments": assessments
        })}}
        normalized = SEMANTIC["normalize_assessments"](assessments, inputs)
        path = output / f"batch-{number:04d}.json"
        SEMANTIC["save_json"](path, {
            "status": "complete", "model": model,
            "prompt_version": "semantic-v1", "input_sha256": identity,
            "input": inputs, "response": response,
            "response_sha256": SEMANTIC["fingerprint"](response),
            "assessments": normalized,
        })


def decision(path, source_id, disposition, evidence, prior=None):
    payload = {"source_id": source_id, "disposition": disposition,
               "question_type": "translation_semantics",
               "reviewer": "agent test reviewer",
               "reason": "The linked Turkish text and scene context support this English.",
               "evidence": [{"kind": "source_text", "path": str(evidence),
                             "sha256": SEMANTIC["digest"](evidence)}]}
    if prior:
        payload["prior_review"] = str(prior)
    SEMANTIC["save_json"](path, payload)


class SemanticReviewTests(unittest.TestCase):
    def test_authored_fingerprint_rejects_changed_english_and_context(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, target = root / "tr.srt", root / "en.srt"
            srt(source, ["Geldi.", "Burada.", "Bekle."])
            srt(target, ["He came.", "Here.", "Wait."])
            first_map = root / "first-map.json"
            first = SEMANTIC["prepare"](source, target, first_map)
            group = next(SEMANTIC["groups"](first, 2))
            old_input = SEMANTIC["review_input"](*group[1:], [])
            authored = root / "authored.json"
            SEMANTIC["save_json"](authored, {
                "batch_number": 1, "reviewer": "Codex agent test",
                "review_input_sha256": SEMANTIC["fingerprint"](old_input),
                "correct_ids": [item["id"] for item in group[1]],
                "findings": [],
            })
            reviews = root / "reviews"
            SEMANTIC["record_agent_review"](first_map, reviews, authored, 2)

            srt(target, ["He did not come.", "Here.", "Wait."])
            changed_english = root / "changed-english.json"
            second = SEMANTIC["prepare"](source, target, changed_english, first_map)
            self.assertEqual([item["id"] for item in first["utterances"]],
                             [item["id"] for item in second["utterances"]])
            with self.assertRaisesRegex(ValueError, "fingerprint"):
                SEMANTIC["record_agent_review"](
                    changed_english, reviews, authored, 2)

            srt(target, ["He came.", "Here.", "Wait."])
            srt(source, ["Geldi.", "Burada.", "Dur."])
            changed_context = root / "changed-context.json"
            third = SEMANTIC["prepare"](
                source, target, changed_context, first_map)
            self.assertEqual([item["id"] for item in first["utterances"][:2]],
                             [item["id"] for item in third["utterances"][:2]])
            with self.assertRaisesRegex(ValueError, "fingerprint"):
                SEMANTIC["record_agent_review"](
                    changed_context, reviews, authored, 2)

    def test_agent_review_requires_explicit_current_judgments(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, target = root / "tr.srt", root / "en.srt"
            srt(source, ["Geldi.", "Burada."])
            srt(target, ["He did not come.", "Here."])
            mapping = root / "map.json"
            manifest = SEMANTIC["prepare"](source, target, mapping)
            first, second = [item["id"] for item in manifest["utterances"]]
            reviews = root / "reviews"
            authored = root / "agent-input.json"
            SEMANTIC["save_json"](authored, {
                "batch_number": 1, "reviewer": "Codex agent test",
                "review_input_sha256": SEMANTIC["fingerprint"](
                    SEMANTIC["review_input"](*next(SEMANTIC["groups"](manifest, 12))[1:], [])
                ),
                "correct_ids": [second],
                "findings": [{"source_id": first, "verdict": "material_error",
                              "reason": "Turkish is affirmative; English adds negation."}],
            })
            SEMANTIC["record_agent_review"](mapping, reviews, authored, 12)
            self.assertEqual(SEMANTIC["blockers"](mapping, reviews, "agent", 12),
                             ["1 English meaning errors need repair and recheck"])
            srt(target, ["He came.", "Here."])
            current = root / "current.json"
            SEMANTIC["prepare"](source, target, current, mapping)
            self.assertTrue(SEMANTIC["blockers"](current, reviews, "agent", 12))
            SEMANTIC["save_json"](authored, {
                "batch_number": 1, "reviewer": "Codex agent test",
                "review_input_sha256": SEMANTIC["fingerprint"](
                    SEMANTIC["review_input"](*next(SEMANTIC["groups"](
                        json.loads(current.read_text()), 12))[1:], [])
                ),
                "correct_ids": [first, second], "findings": [],
            })
            SEMANTIC["record_agent_review"](current, reviews, authored, 12)
            self.assertEqual(SEMANTIC["blockers"](current, reviews, "agent", 12), [])
            authored.write_text(authored.read_text() + " ")
            self.assertTrue(SEMANTIC["blockers"](current, reviews, "agent", 12))

    def test_agent_review_preserves_distant_work(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, target = root / "tr.srt", root / "en.srt"
            srt(source, [f"Söz {number}." for number in range(1, 31)])
            srt(target, [f"Line {number}." for number in range(1, 31)])
            mapping = root / "map.json"
            manifest = SEMANTIC["prepare"](source, target, mapping)
            reviews = root / "reviews"
            for number, selected, relevant, context in SEMANTIC["groups"](manifest, 12):
                authored = root / f"agent-{number}.json"
                SEMANTIC["save_json"](authored, {
                    "batch_number": number, "reviewer": "Codex agent test",
                    "review_input_sha256": SEMANTIC["fingerprint"](
                        SEMANTIC["review_input"](selected, relevant, context, [])
                    ),
                    "correct_ids": [item["id"] for item in selected],
                    "findings": [],
                })
                SEMANTIC["record_agent_review"](mapping, reviews, authored, 12)
            self.assertEqual(SEMANTIC["blockers"](mapping, reviews, "agent", 12), [])
            srt(source, [f"Söz {number}." if number != 30 else "Yeni söz."
                         for number in range(1, 31)])
            current = root / "current.json"
            updated = SEMANTIC["prepare"](source, target, current, mapping)
            first_group = next(SEMANTIC["groups"](updated, 12))
            inputs = SEMANTIC["review_input"](*first_group[1:], [])
            self.assertIsNotNone(SEMANTIC["current_agent_batch"](
                reviews / "agent-batch-0001.json", 1, inputs, first_group[1]))
            self.assertEqual(SEMANTIC["blockers"](current, reviews, "agent", 12),
                             ["6 source utterances need current English semantic review"])

    def test_approved_manifest_cannot_disagree_with_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, target = root / "tr.srt", root / "en.srt"
            srt(source, ["Geldi."])
            srt(target, ["He did not come."])
            mapping = root / "map.json"
            manifest = SEMANTIC["prepare"](source, target, mapping)
            manifest["translations"][0]["text"] = "He came."
            SEMANTIC["save_json"](mapping, manifest)
            reviews = root / "reviews"
            batch(manifest, reviews, {})
            self.assertEqual(SEMANTIC["blockers"](
                mapping, reviews, "synthetic-test", 12),
                ["English utterance-map text differs from linked SRT"])

    def test_false_alarm_unresolved_and_context_invalidation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, target = root / "tr.srt", root / "en.srt"
            srt(source, ["Geldi.", "Burada."])
            srt(target, ["He came.", "Here."])
            mapping = root / "map.json"
            manifest = SEMANTIC["prepare"](source, target, mapping)
            source_id = manifest["utterances"][0]["id"]
            reviews = root / "reviews"
            batch(manifest, reviews, {source_id: "material_error"})
            self.assertIn("1 English meaning errors need repair and recheck",
                          SEMANTIC["blockers"](mapping, reviews,
                                               "synthetic-test", 12))
            evidence = root / "reference.txt"
            evidence.write_text("Geldi. = He came.\n", encoding="utf-8")
            input_decision = root / "decision.json"
            decision(input_decision, source_id, "unresolved", evidence)
            SEMANTIC["adjudicate"](mapping, reviews, input_decision,
                                    "synthetic-test", 12)
            self.assertTrue(SEMANTIC["blockers"](
                mapping, reviews, "synthetic-test", 12))
            decision(input_decision, source_id, "supported_as_written", evidence)
            SEMANTIC["adjudicate"](mapping, reviews, input_decision,
                                    "synthetic-test", 12)
            self.assertEqual(SEMANTIC["blockers"](
                mapping, reviews, "synthetic-test", 12), [])
            evidence.write_text("Changed evidence.\n", encoding="utf-8")
            self.assertTrue(SEMANTIC["blockers"](
                mapping, reviews, "synthetic-test", 12))
            evidence.write_text("Geldi. = He came.\n", encoding="utf-8")
            self.assertEqual(SEMANTIC["blockers"](
                mapping, reviews, "synthetic-test", 12), [])
            srt(source, ["Geldi.", "Şimdi."])
            changed = root / "changed.json"
            changed_manifest = SEMANTIC["prepare"](source, target, changed, mapping)
            batch(changed_manifest, reviews, {source_id: "material_error"})
            self.assertIn("1 English meaning errors need repair and recheck",
                          SEMANTIC["blockers"](changed, reviews,
                                               "synthetic-test", 12))

    def test_mistranslation_repaired_rechecked_and_exported(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, target = root / "tr.srt", root / "en.srt"
            srt(source, ["Geldi."])
            srt(target, ["He did not come."])
            mapping = root / "map.json"
            manifest = SEMANTIC["prepare"](source, target, mapping)
            source_id = manifest["utterances"][0]["id"]
            reviews = root / "reviews"
            batch(manifest, reviews, {source_id: "material_error"})
            prior = root / "old-finding.json"
            prior.write_bytes((reviews / "batch-0001.json").read_bytes())
            self.assertTrue(SEMANTIC["blockers"](
                mapping, reviews, "synthetic-test", 12))
            srt(target, ["He came."])
            current = root / "current.json"
            repaired = SEMANTIC["prepare"](source, target, current, mapping)
            batch(repaired, reviews, {})
            evidence = root / "repair.txt"
            evidence.write_text("Turkish past affirmative; English negation removed.\n",
                                encoding="utf-8")
            input_decision = root / "repair-decision.json"
            decision(input_decision, source_id, "repaired_rechecked", evidence, prior)
            SEMANTIC["adjudicate"](current, reviews, input_decision,
                                    "synthetic-test", 12)
            self.assertEqual(SEMANTIC["blockers"](
                current, reviews, "synthetic-test", 12), [])
            export = LAYOUT["render"](current, root / "export.tr.srt",
                                      root / "export.en.srt", root / "export.json")
            self.assertEqual(export["english_sha256"],
                             SEMANTIC["digest"](root / "export.en.srt"))
            self.assertIn("He came.", (root / "export.en.srt").read_text())
            self.assertNotIn("not", (root / "export.en.srt").read_text())

    def test_distant_edit_keeps_earlier_batch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, target = root / "tr.srt", root / "en.srt"
            srt(source, [f"Söz {number}." for number in range(1, 27)])
            srt(target, [f"Line {number}." for number in range(1, 27)])
            mapping = root / "map.json"
            manifest = SEMANTIC["prepare"](source, target, mapping)
            reviews = root / "reviews"
            batch(manifest, reviews, {})
            earlier = (reviews / "batch-0001.json").read_bytes()
            srt(source, [f"Söz {number}." if number != 26 else "Yeni söz."
                         for number in range(1, 27)])
            current = root / "current.json"
            updated = SEMANTIC["prepare"](source, target, current, mapping)
            SEMANTIC["current_finding"](updated, reviews, "synthetic-test", 12,
                                        [], updated["utterances"][0]["id"])
            self.assertEqual(earlier, (reviews / "batch-0001.json").read_bytes())
            self.assertTrue(any("current English semantic review" in blocker
                                for blocker in SEMANTIC["blockers"](
                                    current, reviews, "synthetic-test", 12)))

    def test_timing_repair_keeps_semantic_review_and_source_id(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, target = root / "tr.srt", root / "en.srt"
            srt(source, ["Kapıyı kapat."])
            srt(target, ["Close the door."])
            mapping = root / "map.json"
            before = SEMANTIC["prepare"](source, target, mapping)
            reviews = root / "reviews"
            batch(before, reviews, {})
            source.write_text("1\n00:00:05,000 --> 00:00:06,000\nKapıyı kapat.\n")
            target.write_text("1\n00:00:05,000 --> 00:00:06,000\nClose the door.\n")
            current = root / "retimed.json"
            after = SEMANTIC["prepare"](source, target, current, mapping)
            self.assertEqual(after["utterances"][0]["id"],
                             before["utterances"][0]["id"])
            self.assertEqual(after["translations"][0]["id"],
                             before["translations"][0]["id"])
            self.assertEqual(SEMANTIC["blockers"](
                current, reviews, "synthetic-test", 12), [])

    def test_omitted_assessment_becomes_review_question_without_model_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, target = root / "tr.srt", root / "en.srt"
            srt(source, ["Geldi.", "Burada."])
            srt(target, ["He came.", "Here."])
            mapping = root / "map.json"
            manifest = SEMANTIC["prepare"](source, target, mapping)
            reviews = root / "reviews"
            batch(manifest, reviews, {})
            path = reviews / "batch-0001.json"
            saved = json.loads(path.read_text())
            first = saved["assessments"][0]
            saved["response"]["message"]["content"] = json.dumps({
                "assessments": [first]
            })
            saved["response_sha256"] = SEMANTIC["fingerprint"](saved["response"])
            saved["status"] = "invalid"
            SEMANTIC["save_json"](path, saved)
            self.assertEqual(SEMANTIC["recover_saved"](path), 2)
            recovered = json.loads(path.read_text())
            self.assertEqual(recovered["assessments"][1]["verdict"], "uncertain")
            self.assertEqual(recovered["assessments"][1]["error_type"],
                             "missing_assessment")
            self.assertEqual(SEMANTIC["blockers"](
                mapping, reviews, "synthetic-test", 12),
                ["1 semantic review findings need adjudication"])
            evidence = root / "context.txt"
            evidence.write_text("Burada. = Here.\n")
            input_decision = root / "decision.json"
            decision(input_decision, manifest["utterances"][1]["id"],
                     "supported_as_written", evidence)
            SEMANTIC["adjudicate"](mapping, reviews, input_decision,
                                    "synthetic-test", 12)
            self.assertEqual(SEMANTIC["blockers"](
                mapping, reviews, "synthetic-test", 12), [])

    def test_token_truncated_response_preserves_complete_findings(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, target = root / "tr.srt", root / "en.srt"
            srt(source, ["Geldi.", "Burada."])
            srt(target, ["He came.", "Here."])
            mapping = root / "map.json"
            manifest = SEMANTIC["prepare"](source, target, mapping)
            reviews = root / "reviews"
            batch(manifest, reviews, {})
            path = reviews / "batch-0001.json"
            saved = json.loads(path.read_text())
            first = saved["assessments"][0]
            saved["response"]["message"]["content"] = (
                '{"assessments": [' + json.dumps(first) + ', {"source_id":'
            )
            saved["response"]["done_reason"] = "length"
            saved["response_sha256"] = SEMANTIC["fingerprint"](saved["response"])
            saved["status"] = "invalid"
            SEMANTIC["save_json"](path, saved)
            self.assertEqual(SEMANTIC["recover_saved"](path), 2)
            recovered = json.loads(path.read_text())
            self.assertEqual(recovered["assessments"][0]["verdict"], "correct")
            self.assertEqual(recovered["assessments"][1]["verdict"], "uncertain")
            self.assertEqual(SEMANTIC["blockers"](
                mapping, reviews, "synthetic-test", 12),
                ["1 semantic review findings need adjudication"])


if __name__ == "__main__":
    unittest.main()
