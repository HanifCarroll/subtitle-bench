#!/usr/bin/env python3
"""Exercise the workbench's review and safe-install loop on copied fixtures."""

import hashlib
import json
import os
import runpy
import subprocess
import tempfile
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch


TOOL = Path(__file__).with_name("subtitle-workbench.py")
SEMANTIC = runpy.run_path(str(Path(__file__).with_name("semantic-review.py")))
ALIGNER = runpy.run_path(str(Path(__file__).with_name("align-turkish.py")))
LAYOUT_AUDIT = runpy.run_path(str(Path(__file__).with_name("layout-audit.py")))
PLAYBACK = runpy.run_path(str(Path(__file__).with_name("playback-check.py")))


def run(*arguments):
    result = subprocess.run(["python3", str(TOOL), *map(str, arguments)],
                            check=True, capture_output=True, text=True)
    return json.loads(result.stdout.splitlines()[-1])


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def synthetic_audio_review(root, video, source, start_ms, end_ms, name):
    """Create traceable synthetic responses for a gate test, never real evidence."""
    raw = root / f"{name}-raw.txt"
    raw.write_text("Synthetic audio review response.\n", encoding="utf-8")
    result = root / f"{name}-review.json"
    source_review = runpy.run_path(str(Path(__file__).with_name("source-review.py")))
    interval_hash = source_review["source_interval_sha256"](
        source_review["READ_CUES"](source), start_ms, end_ms
    )
    result.write_text(json.dumps({
        "video_sha256": digest(video), "source_sha256": digest(source),
        "source_interval_sha256": interval_hash,
        "start_ms": start_ms, "end_ms": end_ms, "status": "supported",
        "stages": [
            {"stage": stage, "method": "audio_capable_model",
             "model": "synthetic-test-only", "prompt_version": "test-v1",
             "assessment": "Synthetic test response", "raw_response": str(raw),
             "raw_response_sha256": digest(raw)}
            for stage in ("independent", "comparison")
        ],
    }), encoding="utf-8")
    return str(result)


def synthetic_semantic_review(source, target, root):
    """Use synthetic complete assessments to exercise only the release gate."""
    manifest_path = root / "utterances.json"
    manifest = SEMANTIC["prepare"](source, target, manifest_path)
    reviews = root / "semantic-reviews"
    reviews.mkdir()
    for number, selected, related, context in SEMANTIC["groups"](manifest, 12):
        inputs = SEMANTIC["review_input"](selected, related, context, [])
        identity = SEMANTIC["fingerprint"]({
            "model": "synthetic-test", "prompt": SEMANTIC["PROMPT"], "input": inputs,
        })
        assessments = [{"source_id": item["id"], "verdict": "correct"}
                       for item in selected]
        response = {"message": {"content": json.dumps({
            "assessments": assessments})}}
        (reviews / f"batch-{number:04d}.json").write_text(json.dumps({
            "status": "complete", "model": "synthetic-test", "input_sha256": identity,
            "prompt_version": "semantic-v1", "response": response,
            "response_sha256": SEMANTIC["fingerprint"](response),
            "input": inputs, "assessments": assessments,
        }), encoding="utf-8")
    return manifest_path, reviews


def synthetic_layout_render(video, manifest_path, case, root):
    """Make current timing and real libass evidence for the release fixture."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    alignment_dir = root / "alignment"
    alignment_dir.mkdir()
    units = manifest["utterances"]
    alignment = {
        "video_sha256": digest(video), "model": "synthetic-aligner",
        "audio_start_ms": 0, "audio_end_ms": 12_000,
        "input_sha256": ALIGNER["alignment_input"](
            units, 0, 12_000, digest(video), "synthetic-aligner"
        ),
        "utterances": [{"id": unit["id"], "text": unit["text"],
                        "source_cue_ids": unit["cue_ids"], "status": "aligned",
                        "word_timings": [{"text": "fixture", "start_ms": 1_000,
                                          "end_ms": 10_000}]}
                       for unit in units],
    }
    (alignment_dir / "000.json").write_text(json.dumps(alignment), encoding="utf-8")
    layout_report = root / "layout-audit.json"
    LAYOUT_AUDIT["run"](video, manifest_path, alignment_dir, layout_report, 700, 25)
    render_report, _ = PLAYBACK["check"](
        video, Path(manifest["source"]), Path(manifest["target"]),
        root / "candidate-render", []
    )
    return layout_report, render_report


def main():
    comparison = runpy.run_path(str(TOOL))["compare_audio_window"]
    assert comparison("Ne haber abi? Nasılsın bugün, nasıl gidiyor?", "Ayyy!")["issue"] == (
        "possible_missing_or_wrong_subtitle"
    )
    assert comparison("lalalalalalalalalalalalalalalalalalalalalalalalalalal", "Ayyy!")[
        "issue"
    ] == "repeated_asr_output"
    assert comparison("Ne oldu ne oldu ne oldu ne oldu?", "Ne oldu?")["issue"] == (
        "repeated_asr_output"
    )
    assert comparison("", "Ayyy!")["issue"] is None
    heard = ("Kapıyı aç içeride biri var sesini duydum hemen gel yardım et. "
             "Tamam anladım şimdi buraya gel birlikte gidelim sonra konuşuruz.")
    written = "Tamam anladım şimdi buraya gel birlikte gidelim sonra konuşuruz."
    assert comparison(heard, written)["issue"] == "possible_missing_or_wrong_subtitle"
    assert comparison("Evet, ben geldim.", "Hayır, ben geldim.")["issue"] == (
        "possible_missing_or_wrong_subtitle"
    )
    assert comparison("Gel buraya hemen.", "")["issue"] == (
        "possible_missing_or_wrong_subtitle"
    )
    assert comparison("Merhaba.", "Merhaba ama ben buradayım.")["issue"] == (
        "possible_unsupported_subtitle"
    )
    ordinary = "Bugün dışarı çıkıp arkadaşlarımızla buluştuk sonra eve dönüp yemek yaptık " \
               "ve uzun uzun sohbet ettik yarın da aynı yerde yeniden görüşmeyi planladık."
    assert comparison(ordinary.replace("yemek", "kahve"), ordinary)["issue"] is None
    units = [{"id": "u1", "text": "Gel.", "start_ms": 59_500,
              "end_ms": 60_500, "cue_ids": [1]}]
    alignment_jobs = list(ALIGNER["windows"](units, 120_000))
    assert len(alignment_jobs) == 1
    assert alignment_jobs[0][0:4] == (60_000, 120_000, 58_000, 120_000)
    uncertain_words = ALIGNER["summarize_words"](
        {"words": [{"word": "Gel"}]}, units[0], 57_500
    )
    assert uncertain_words["status"] == "partial"
    assert uncertain_words["unaligned_words"] == ["Gel"]

    with tempfile.TemporaryDirectory(prefix="subtitle-workbench-test-") as directory:
        root = Path(directory)
        video = root / "demo.mp4"
        subprocess.run([
            "ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=black:s=160x90:r=1:d=12",
            "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono", "-t", "12",
            "-c:v", "mpeg4", "-c:a", "aac", "-loglevel", "error", str(video),
        ], check=True, capture_output=True)

        # 1. Keep source and target cues independently segmented.

        source = root / "candidate.tr.srt"
        target = root / "candidate.en.srt"
        source.write_text("1\n00:00:01,000 --> 00:00:10,000\nMerhaba dünya.\n", encoding="utf-8")
        target.write_text(
            "1\n00:00:01,000 --> 00:00:05,000\nHello.\n\n"
            "2\n00:00:05,000 --> 00:00:10,000\nWorld.\n", encoding="utf-8"
        )
        rendered_path, rendered = PLAYBACK["check"](
            video, source, target, root / "rendered", [10_500]
        )
        assert rendered_path.is_file()
        assert rendered["render_checks_passed"]
        assert any(not item["expected_visible"] for item in rendered["samples"])
        draft_plan = run("translate", source, root / "new-draft.en.srt",
                         "--source-language", "tr")
        assert draft_plan["source_cues"] == 1 and not (root / "new-draft.en.srt").exists()
        aligned = root / "aligned.en.srt"
        aligned.write_text(
            "1\n00:00:01,000 --> 00:00:10,000\nHello world.\n", encoding="utf-8"
        )
        google_plan = run("translation-second-opinion", source, aligned,
                          root / "google.json", "--source-language", "tr")
        assert google_plan["status"] == "dry_run" and not (root / "google.json").exists()
        installed_source = video.with_suffix(".tr.srt")
        installed_target = video.with_suffix(".en.srt")
        installed_source.write_text("old source\n", encoding="utf-8")
        installed_target.write_text("old target\n", encoding="utf-8")
        case = root / "case"
        run("audit", video, source, case, "--language", "tr", "--coverage")
        cache = root / "audio-cache.json"
        cache.write_text(json.dumps({
            "video_sha256": digest(video),
            "model": "synthetic-model", "language": "Turkish",
            "window_ms": 30000, "max_tokens": 256,
            "windows": {"0": {"start_ms": 0, "end_ms": 12000,
                              "text": "Ne haber abi? Nasılsın bugün, nasıl gidiyor?"}},
        }), encoding="utf-8")
        audio_report = root / "audio-report.json"
        audio_summary = run("audio-check", case, "--output", audio_report,
                            "--cache", cache, "--model", "synthetic-model")
        assert audio_summary["issues"] == 1
        assert json.loads(audio_report.read_text())["source_sha256"] == digest(
            case / "working.tr.srt"
        )
        episode_output = root / "episode-check"
        episode_output.mkdir()
        (episode_output / "audio-transcripts.json").write_bytes(cache.read_bytes())
        episode_summary = run(
            "episode-check", case, target,
            "--source-language", "tr", "--target-language", "en",
            "--model", "synthetic-model", "--output", episode_output,
        )
        assert not episode_summary["installation_checks_passed"]
        assert episode_summary["audio_questions"] == 1
        checked_audio = episode_output / "audio-check.json"
        audio_decisions = episode_output / "audio-decisions.json"
        audio_bundle = run("bundle", case, target, 0, 12_000)["bundle"]
        audio_decisions.write_text(json.dumps({
            "audio_report_sha256": digest(checked_audio),
            "source_sha256": digest(case / "working.tr.srt"),
            "decisions": [{"start_ms": 0, "end_ms": 12000,
                           "disposition": "model_artifact",
                           "reason": "Synthetic comparison fixture",
                           "reviewer": "synthetic self-check",
                           "evidence": [audio_bundle],
                           "review_result": synthetic_audio_review(
                               root, video, case / "working.tr.srt", 0, 12_000,
                               "audio-question") }],
        }), encoding="utf-8")
        scan = runpy.run_path(str(TOOL))
        checked_data = json.loads(checked_audio.read_text())
        assert scan["audio_scan_blockers"](checked_data, 12_000) == []
        for status in (None, "unknown", "failed", "truncated"):
            changed = json.loads(checked_audio.read_text())
            if status is None:
                changed["windows"][0].pop("status")
            else:
                changed["windows"][0]["status"] = status
            changed["issues"] = list(changed["windows"])
            assert scan["audio_scan_blockers"](changed, 12_000)
        empty = json.loads(checked_audio.read_text())
        empty["windows"][0].update({"status": "empty", "text": "",
                                    "issue": "empty_asr_output"})
        empty["issues"] = list(empty["windows"])
        empty_path = root / "empty-audio-report.json"
        empty_path.write_text(json.dumps(empty), encoding="utf-8")
        assert scan["audio_scan_blockers"](empty, 12_000) == []
        assert scan["audio_decision_blockers"](
            empty_path, root / "missing-empty-decisions.json",
            case / "working.tr.srt", video
        )
        for issue_kind, status in (("empty_asr_output", "empty"),
                                   ("repeated_asr_output", "questionable")):
            current = json.loads(checked_audio.read_text())
            current["windows"][0]["status"] = status
            current["windows"][0]["issue"] = issue_kind
            if status == "empty":
                current["windows"][0]["text"] = ""
            current["issues"] = list(current["windows"])
            report_path = root / f"{status}-report.json"
            report_path.write_text(json.dumps(current), encoding="utf-8")
            decision_data = json.loads(audio_decisions.read_text())
            decision_data["audio_report_sha256"] = digest(report_path)
            decision_path = root / f"{status}-decisions.json"
            decision_path.write_text(json.dumps(decision_data), encoding="utf-8")
            assert scan["audio_scan_blockers"](current, 12_000) == []
            assert scan["audio_decision_blockers"](
                report_path, decision_path, case / "working.tr.srt", video
            ) == []
        interval_source = root / "interval-source.tr.srt"
        interval_source.write_text(
            "1\n00:00:01,000 --> 00:00:05,000\nMerhaba.\n\n"
            "2\n00:00:08,000 --> 00:00:10,000\nSonra.\n", encoding="utf-8")
        first = dict(checked_data["windows"][0])
        first["end_ms"] = 6_000
        second = {**first, "start_ms": 6_000, "end_ms": 12_000,
                  "text": "Sonra.", "source_text": "Sonra.", "issue": None,
                  "status": "complete"}
        local_report = {**checked_data, "source": str(interval_source),
                        "source_sha256": digest(interval_source),
                        "windows": [first, second], "issues": [first]}
        local_report_path = root / "interval-audio-report.json"
        local_report_path.write_text(json.dumps(local_report), encoding="utf-8")
        local_decisions = root / "interval-audio-decisions.json"
        local_entry = {
            "start_ms": 0, "end_ms": 6_000,
            "disposition": "model_artifact", "reason": "Synthetic local fixture",
            "reviewer": "synthetic self-check", "evidence": [audio_bundle],
            "review_result": synthetic_audio_review(
                root, video, interval_source, 0, 6_000, "interval-audio"
            ),
        }
        local_input = root / "interval-audio-input.json"
        local_input.write_text(json.dumps(local_entry), encoding="utf-8")
        assert run("audio-adjudicate", local_report_path,
                   local_decisions, local_input)["remaining"] == []
        assert scan["audio_decision_blockers"](
            local_report_path, local_decisions, interval_source, video
        ) == []
        interval_source.write_text(interval_source.read_text().replace(
            "Sonra.", "Daha sonra."), encoding="utf-8")
        local_report["source_sha256"] = digest(interval_source)
        local_report["windows"][1]["source_text"] = "Daha sonra."
        local_report_path.write_text(json.dumps(local_report), encoding="utf-8")
        assert scan["audio_decision_blockers"](
            local_report_path, local_decisions, interval_source, video
        ) == []
        interval_source.write_text(interval_source.read_text().replace(
            "Merhaba.", "Geldi."), encoding="utf-8")
        local_report["source_sha256"] = digest(interval_source)
        local_report_path.write_text(json.dumps(local_report), encoding="utf-8")
        assert scan["audio_decision_blockers"](
            local_report_path, local_decisions, interval_source, video
        )
        episode_summary = run(
            "episode-check", case, target,
            "--source-language", "tr", "--target-language", "en",
            "--model", "synthetic-model", "--output", episode_output,
        )
        assert not episode_summary["installation_checks_passed"]
        run("audit", video, source, root / "pt-case", "--language", "pt-BR")
        assert (root / "pt-case/working.pt-br.srt").is_file()
        reference = root / "reference.en.srt"
        reference.write_text(
            "1\n00:00:01,000 --> 00:00:02,000\nHello.\n\n"
            "2\n00:00:10,700 --> 00:00:11,500\nMissing line.\n",
            encoding="utf-8",
        )
        reference_case = root / "reference-case"
        run("audit", video, source, reference_case, "--language", "tr",
            "--reference", reference, "--reference-offset-ms", "0",
            "--reference-timing-only")
        reference_queue = json.loads((reference_case / "review-queue.json").read_text())
        assert reference_queue["counts"]["reference_only"] == 1
        assert "reference_disagreement" not in reference_queue["counts"]

        windows = runpy.run_path(str(TOOL))["gap_review_windows"](
            {"start_ms": 1_000, "end_ms": 95_000}, 100_000, 6
        )
        assert windows[0][0] == 0 and windows[-1][1] == 100_000
        assert all(left[1] >= right[0] for left, right in zip(windows, windows[1:]))
        inspected = run("review", case, "--issue-id", "long_cue:1")
        assert inspected["issue"]["id"] == "long_cue:1"
        evidence = next((case / "clips").glob("*.json"))
        decision = case / "reviewed.json"
        decision.write_text(json.dumps({
            "issue_id": "long_cue:1", "status": "reviewed",
            "reason": "Synthetic no-change review test",
            "evidence": [str(evidence.relative_to(case))],
            "expected_working_sha256": digest(case / "working.tr.srt"),
            "reviewer": "synthetic self-check",
            "review_result": synthetic_audio_review(
                root, video, case / "working.tr.srt", 1_000, 10_000,
                "source-long-cue"),
        }), encoding="utf-8")
        run("record", case, decision)
        nonspeech_issue = run("review", case)["issue"]["id"]
        assert nonspeech_issue.startswith("possible_subtitle_without_speech:1-")
        decision.write_text(json.dumps({
            "issue_id": nonspeech_issue, "status": "reviewed",
            "reason": "Synthetic silence is expected in this test fixture",
            "evidence": [str(evidence.relative_to(case))],
            "expected_working_sha256": digest(case / "working.tr.srt"),
            "reviewer": "synthetic self-check",
            "review_result": synthetic_audio_review(
                root, video, case / "working.tr.srt", 1_000, 10_000,
                "source-nonspeech"),
        }), encoding="utf-8")
        run("record", case, decision)
        assert run("review", case)["pending"] == 0
        semantic_manifest, semantic_reviews = synthetic_semantic_review(
            case / "working.tr.srt", target, root
        )
        layout_report, render_report = synthetic_layout_render(
            video, semantic_manifest, case, root
        )
        semantic_options = (
            "--semantic-manifest", semantic_manifest,
            "--semantic-reviews", semantic_reviews,
            "--semantic-model", "synthetic-test",
            "--layout-report", layout_report,
            "--render-report", render_report,
        )
        scene = run("bundle", case, target, 0, 12_000,
                    "--audio-report", checked_audio,
                    "--layout-report", layout_report)["bundle"]
        scene_issues = json.loads(Path(scene).read_text())["issues"]
        assert any(item["id"].startswith("audio:") for item in scene_issues)
        episode_summary = run(
            "episode-check", case, target,
            "--source-language", "tr", "--target-language", "en",
            "--model", "synthetic-model", "--output", episode_output,
            *semantic_options,
        )
        assert episode_summary["installation_checks_passed"]

        translation = root / "translation.json"
        summary = run("translation-audit", case / "working.tr.srt", target,
                      "--output", translation)
        assert summary["flags"] == 0 and summary["source_cues"] == 1
        assert summary["target_cues"] == 2

        several_source = root / "several.tr.srt"
        several_source.write_text(
            "1\n00:00:01,000 --> 00:00:02,000\nBir.\n\n"
            "2\n00:00:02,000 --> 00:00:03,000\nİki.\n\n"
            "3\n00:00:03,000 --> 00:00:04,000\nÜç.\n", encoding="utf-8"
        )
        one_target = root / "one.en.srt"
        one_target.write_text(
            "1\n00:00:01,000 --> 00:00:04,000\nOne.\n", encoding="utf-8"
        )
        many_report = root / "many.json"
        run("translation-audit", several_source, one_target, "--output", many_report)
        assert "many_source_cues_one_target" in {
            flag["kind"] for flag in json.loads(many_report.read_text())["flags"]
        }
        long_target = root / "long.en.srt"
        long_target.write_text(
            "1\n00:00:01,000 --> 00:00:10,000\nOne two three.\n",
            encoding="utf-8",
        )
        long_report = root / "long-target.json"
        run("translation-audit", source, long_target, "--output", long_report)
        assert "long_target_cue" in {
            flag["kind"] for flag in json.loads(long_report.read_text())["presentation_flags"]
        }
        assert not json.loads(long_report.read_text())["flags"]
        fast_target = root / "fast.en.srt"
        fast_target.write_text(
            "1\n00:00:01,000 --> 00:00:02,000\nThis sentence is far too fast.\n",
            encoding="utf-8",
        )
        fast_report = root / "fast-target.json"
        run("translation-audit", source, fast_target, "--output", fast_report)
        assert any(item["language"] == "target" for item in
                   json.loads(fast_report.read_text())["presentation_flags"])
        map_path = root / "many-utterances.json"
        mapping = SEMANTIC["prepare"](several_source, one_target, map_path)
        assert len(mapping["utterances"]) == 3
        assert mapping["translations"][0]["source_ids"] == [
            item["id"] for item in mapping["utterances"]
        ]
        assert SEMANTIC["blockers"](map_path, root / "missing-reviews",
                                    "synthetic-test", 12) == [
            "3 source utterances need current English semantic review"
        ]
        missing_link_map = root / "missing-link-utterances.json"
        missing_link = json.loads(map_path.read_text(encoding="utf-8"))
        missing_link["translations"][0]["source_ids"] = [
            mapping["utterances"][0]["id"]]
        missing_link_map.write_text(json.dumps(missing_link), encoding="utf-8")
        assert "2 source utterances lack English links" in SEMANTIC["blockers"](
            missing_link_map, root / "missing-reviews", "synthetic-test", 12)
        changed_source = root / "changed.tr.srt"
        changed_source.write_text(several_source.read_text().replace("Bir.", "Evet."),
                                  encoding="utf-8")
        changed_map = root / "changed-utterances.json"
        updated = SEMANTIC["prepare"](changed_source, one_target, changed_map, map_path)
        assert updated["utterances"][0]["id"] == mapping["utterances"][0]["id"]
        assert SEMANTIC["review_input"](
            updated["utterances"][:1], updated["translations"], [], []
        ) != SEMANTIC["review_input"](
            mapping["utterances"][:1], mapping["translations"], [], []
        )
        semantic_scene = root / "semantic-scene"
        semantic_scene.mkdir()
        scene_map, scene_reviews = synthetic_semantic_review(
            several_source, one_target, semantic_scene
        )
        tampered = root / "tampered-semantic-reviews"
        tampered.mkdir()
        saved_batch = json.loads((scene_reviews / "batch-0001.json").read_text())
        saved_batch["assessments"][0]["verdict"] = "material_error"
        (tampered / "batch-0001.json").write_text(json.dumps(saved_batch))
        assert SEMANTIC["blockers"](scene_map, tampered,
                                    "synthetic-test", 12) == [
            "3 source utterances need current English semantic review"
        ]
        assert SEMANTIC["blockers"](changed_map, scene_reviews,
                                    "synthetic-test", 12) == [
            "3 source utterances need current English semantic review"
        ]
        layout_source = root / "layout-only.tr.srt"
        layout_source.write_text(several_source.read_text().replace(
            "00:00:02,000 --> 00:00:03,000",
            "00:00:02,100 --> 00:00:03,000",
        ), encoding="utf-8")
        layout_map = root / "layout-only-utterances.json"
        SEMANTIC["prepare"](layout_source, one_target, layout_map, map_path)
        assert SEMANTIC["blockers"](layout_map, scene_reviews,
                                    "synthetic-test", 12) == []

        # 2. A known provider disagreement blocks release until audio review.

        disagreement_evidence = case / "provider-response.json"
        disagreement_evidence.write_text('{"text":"synthetic conflict"}\n', encoding="utf-8")
        disagreement = case / "evidence-disagreements.json"
        disagreement.write_text(json.dumps({
            "version": 1,
            "video_sha256": digest(video),
            "disagreements": [{
                "id": "synthetic-word-conflict", "start_ms": 1_000,
                "end_ms": 2_000, "summary": "Two synthetic models disagree.",
                "evidence": [{"path": str(disagreement_evidence),
                              "sha256": digest(disagreement_evidence)}],
            }],
        }), encoding="utf-8")
        disputed = run("release", video, case / "working.tr.srt", target,
                       "--source-language", "tr", "--target-language", "en",
                       "--case", case, "--translation-report", translation,
                       "--audio-report", checked_audio,
                       "--audio-decisions", audio_decisions,
                       "--output", root / "disputed-release.json", *semantic_options)
        assert not disputed["installation_checks_passed"]
        assert any("source questions need decisions" in blocker
                   for blocker in disputed["blockers"])
        disagreement_evidence.write_text('{"text":"changed conflict"}\n', encoding="utf-8")
        try:
            run("release", video, case / "working.tr.srt", target,
                "--source-language", "tr", "--target-language", "en",
                "--case", case, "--translation-report", translation,
                "--audio-report", checked_audio,
                "--audio-decisions", audio_decisions,
                "--output", root / "tampered-dispute-release.json",
                *semantic_options)
        except subprocess.CalledProcessError as error:
            assert "missing or changed evidence" in error.stderr
        else:
            raise AssertionError("Changed dispute evidence should stop release")
        disagreement.unlink()

        # 3. A current, structurally valid pair can be installed without a release label.

        report = root / "release.json"
        checked = run("release", video, case / "working.tr.srt", target,
                      "--source-language", "tr", "--target-language", "en",
                      "--case", case, "--translation-report", translation,
                      "--audio-report", checked_audio,
                      "--audio-decisions", audio_decisions,
                      "--output", report, *semantic_options)
        assert checked["installation_checks_passed"]
        assert "ready" not in json.loads(report.read_text())
        assert "provisional" not in json.loads(report.read_text())

        release_function = runpy.run_path(str(TOOL))["release"]
        urgent_issue = {"id": "long_cue:1", "kind": "long_cue",
                        "start_ms": 1_000, "end_ms": 43_000}
        urgent_args = Namespace(
            video=video, source=case / "working.tr.srt", target=target,
            source_language="tr", target_language="en", case=case,
            translation_report=translation, audio_report=checked_audio,
            audio_decisions=audio_decisions, output=root / "urgent-release.json",
            semantic_manifest=semantic_manifest, semantic_reviews=semantic_reviews,
            semantic_model="synthetic-test", semantic_batch_size=12, glossary=None,
            layout_report=layout_report, timing_decisions=None,
            render_report=render_report,
            apply=False, backup_dir=None,
        )
        with patch.dict(release_function.__globals__, {
            "current_queue": lambda _: ({"issues": [urgent_issue]}, [urgent_issue]),
        }):
            release_function(urgent_args)
        urgent_report = json.loads(urgent_args.output.read_text())
        assert not urgent_report["installation_checks_passed"]
        assert urgent_report["urgent_source_issue_ids"] == ["long_cue:1"]
        coverage_issue = {"id": "possible_speech_gap:1", "kind": "possible_speech_gap",
                          "start_ms": 2_000, "end_ms": 3_000}
        with patch.dict(release_function.__globals__, {
            "current_queue": lambda _: ({"issues": [coverage_issue]}, [coverage_issue]),
        }):
            release_function(urgent_args)
        coverage_report = json.loads(urgent_args.output.read_text())
        assert not coverage_report["installation_checks_passed"]
        assert coverage_report["open_coverage_issue_ids"] == ["possible_speech_gap:1"]
        ordinary_issue = {"id": "long_cue:2", "kind": "long_cue",
                          "start_ms": 1_000, "end_ms": 10_000}
        with patch.dict(release_function.__globals__, {
            "current_queue": lambda _: ({"issues": [ordinary_issue]}, [ordinary_issue]),
        }):
            release_function(urgent_args)
        ordinary_report = json.loads(urgent_args.output.read_text())
        assert not ordinary_report["installation_checks_passed"]
        assert ordinary_report["pending_source_issues"] == 1
        original_translation = translation.read_text(encoding="utf-8")
        flagged_translation = json.loads(original_translation)
        flagged_translation["flags"] = [{"kind": "synthetic_timing_flag"}]
        translation.write_text(json.dumps(flagged_translation), encoding="utf-8")
        release_function(urgent_args)
        translation.write_text(original_translation, encoding="utf-8")
        assert not json.loads(urgent_args.output.read_text())["installation_checks_passed"]

        partial_audio = root / "partial-audio.json"
        partial_report = json.loads(checked_audio.read_text())
        partial_report["end_ms"] = 6_000
        partial_report["windows"][0]["end_ms"] = 6_000
        partial_report["issues"] = []
        partial_audio.write_text(json.dumps(partial_report), encoding="utf-8")
        partial_args = Namespace(**{**vars(urgent_args), "audio_report": partial_audio,
                                    "output": root / "partial-release.json"})
        release_function(partial_args)
        assert any("audio scan" in blocker.lower() for blocker in
                   json.loads(partial_args.output.read_text())["blockers"])

        assert len(json.loads(report.read_text())["playback_samples"]) == 1
        assert installed_source.read_text() == "old source\n"
        assert installed_target.read_text() == "old target\n"

        # 3. A failed second replacement restores both old sidecars.

        original_replace = os.replace

        replaced_destinations = []

        def fail_second_replace(source_path, destination_path):
            replaced_destinations.append(str(destination_path))
            if Path(destination_path).name == installed_target.name:
                raise OSError("synthetic second-install failure")

            return original_replace(source_path, destination_path)

        failed_args = Namespace(
            video=video, source=case / "working.tr.srt", target=target,
            source_language="tr", target_language="en", case=case,
            translation_report=translation, audio_report=checked_audio,
            audio_decisions=audio_decisions, output=root / "failed-release.json",
            semantic_manifest=semantic_manifest, semantic_reviews=semantic_reviews,
            semantic_model="synthetic-test", semantic_batch_size=12, glossary=None,
            layout_report=layout_report, timing_decisions=None,
            render_report=render_report,
            apply=True, backup_dir=root / "failed-backup",
        )
        with patch("os.replace", side_effect=fail_second_replace):
            try:
                release_function(failed_args)
            except OSError as error:
                assert "synthetic second-install failure" in str(error)
            else:
                raise AssertionError(f"Second install should have failed: {replaced_destinations}")
        assert installed_source.read_text() == "old source\n"
        assert installed_target.read_text() == "old target\n"

        # 4. A current pair installs with verified backups.

        backup = root / "backup"
        installed = run("release", video, case / "working.tr.srt", target,
                        "--source-language", "tr", "--target-language", "en",
                        "--case", case, "--translation-report", translation,
                        "--audio-report", checked_audio,
                        "--audio-decisions", audio_decisions,
                        "--output", report, *semantic_options,
                        "--apply", "--backup-dir", backup)
        assert installed["installed"]
        assert installed_source.read_bytes() == (case / "working.tr.srt").read_bytes()
        assert installed_target.read_bytes() == target.read_bytes()
        assert (backup / installed_source.name).read_text() == "old source\n"
        assert (backup / installed_target.name).read_text() == "old target\n"

        # 5. One interval bundles playable clips and aligned subtitle/ASR evidence.

        focused = root / "focused.srt"
        focused.write_text(
            "1\n00:00:01,000 --> 00:00:03,000\nMerhaba.\n", encoding="utf-8"
        )
        manifest = root / "focused-manifest.json"
        manifest.write_text(json.dumps({
            "video_sha256": digest(video), "windows": [
                {"start_ms": 0, "end_ms": 12000, "whisper_srt": str(focused)}
            ],
        }), encoding="utf-8")
        bundled = run("bundle", reference_case, target, 1000, 10000,
                      "--audio-report", audio_report,
                      "--asr-manifest", manifest)
        bundle_report = json.loads(Path(bundled["bundle"]).read_text())
        assert Path(bundle_report["clips"][0]["audio_clip"]).is_file()
        assert Path(bundle_report["clips"][0]["video_clip"]).is_file()
        assert {item["kind"] for item in bundle_report["timeline"]} == {
            "turkish", "english", "reference", "asr"
        }
        assert any(item["kind"] == "asr" and item["start_ms"] == 1000
                   and item["granularity"] == "cue"
                   for item in bundle_report["timeline"])
        assert bundle_report["asr_inputs"][0]["source_stale"] is False

        visual_output = root / "visual-bundle.json"
        visual = run("bundle", reference_case, target, 1000, 10000,
                     "--visual-cue-id", 1, "--output", visual_output)
        frames = json.loads(Path(visual["bundle"]).read_text())["visual_context"]
        assert frames["status"] == "frames_only"
        assert Path(frames["overview_frame"]["path"]).is_file()
        assert {frame["position"] for frame in frames["cues"][0]["frames"]} == {
            "before", "during", "after"
        }
        for frame in frames["cues"][0]["frames"]:
            assert digest(Path(frame["path"])) == frame["sha256"]
        observed_at = frames["cues"][0]["frames"][1]["timestamp_ms"]
        visual_notes = root / "visual-notes.json"
        visual_notes.write_text(json.dumps({
            "reviewer": "synthetic visual reviewer",
            "scene_overview": "Black synthetic test scene.",
            "observations": [{"cue_id": 1, "timestamp_ms": observed_at,
                              "category": "setting",
                              "observation": "The sampled frame is black."}],
        }), encoding="utf-8")
        run("bundle", reference_case, target, 1000, 10000,
            "--visual-cue-id", 1, "--visual-notes", visual_notes,
            "--output", visual_output)
        observed = json.loads(visual_output.read_text())["visual_context"]
        assert observed["status"] == "observed"
        assert observed["authored_sha256"] == digest(visual_notes)
        assert observed["observations"][0]["cue_id"] == 1
        invalid = json.loads(visual_notes.read_text())
        invalid["observations"][0]["timestamp_ms"] += 1
        visual_notes.write_text(json.dumps(invalid), encoding="utf-8")
        rejected = subprocess.run([
            "python3", str(TOOL), "bundle", str(reference_case), str(target),
            "1000", "10000", "--visual-cue-id", "1", "--visual-notes",
            str(visual_notes), "--output", str(visual_output),
        ], capture_output=True, text=True)
        assert rejected.returncode != 0

        # 6. A paired split is hash-bound and restores both files on write failure.

        working_pair = reference_case / "working.tr.srt"
        original_source = working_pair.read_bytes()
        original_target = target.read_bytes()
        replacement = {
            "start_ms": 1000, "end_ms": 10000,
            "source_sha256": digest(working_pair), "target_sha256": digest(target),
            "replace_source_ids": [1], "replace_target_ids": [1, 2],
            "reviewer": "synthetic self-check", "reason": "Split a held cue",
            "evidence": [bundled["bundle"]],
            "review_result": synthetic_audio_review(
                root, video, working_pair, 1_000, 10_000, "paired-replacement"),
            "cues": [
                {"start_ms": 1000, "end_ms": 5000,
                 "source_text": "Merhaba.", "target_text": "Hello."},
                {"start_ms": 5000, "end_ms": 10000,
                 "source_text": "Dünya.", "target_text": "World."},
            ],
        }
        replacement_path = root / "replacement.json"
        replacement_path.write_text(json.dumps(replacement), encoding="utf-8")
        replace_function = runpy.run_path(str(TOOL))["replace_pair"]
        replace_args = Namespace(case=reference_case, target=target,
                                 decision=replacement_path)
        original_copy = __import__("shutil").copy2
        failed_once = False

        def fail_target_once(source_path, destination_path):
            nonlocal failed_once
            if Path(destination_path).resolve() == target.resolve() and not failed_once:
                failed_once = True
                raise OSError("synthetic target write failure")

            return original_copy(source_path, destination_path)

        with patch("shutil.copy2", side_effect=fail_target_once):
            try:
                replace_function(replace_args)
            except OSError as error:
                assert "synthetic target write failure" in str(error)
            else:
                raise AssertionError("Paired replacement should have failed")
        assert working_pair.read_bytes() == original_source
        assert target.read_bytes() == original_target

        invalid = {**replacement, "target_sha256": "stale"}
        replacement_path.write_text(json.dumps(invalid), encoding="utf-8")
        rejected = subprocess.run(
            ["python3", str(TOOL), "replace-pair", str(reference_case),
             str(target), str(replacement_path)], capture_output=True, text=True,
        )
        assert rejected.returncode != 0 and "stale" in rejected.stderr
        assert working_pair.read_bytes() == original_source
        assert target.read_bytes() == original_target

        replacement_path.write_text(json.dumps(replacement), encoding="utf-8")
        replaced = run("replace-pair", reference_case, target, replacement_path)
        assert replaced["source_sha256"] == digest(working_pair)
        assert replaced["target_sha256"] == digest(target)
        assert "Dünya." in working_pair.read_text()
        assert "World." in target.read_text()
        revision = Path(replaced["decision"]).parent
        assert (revision / "source-before.srt").read_bytes() == original_source
        assert (revision / "target-before.srt").read_bytes() == original_target

        # An alignment-informed repair retimes both languages independently.
        layout_map = root / "repair-utterances.json"
        layout_manifest = SEMANTIC["prepare"](working_pair, target, layout_map)
        layout_alignment = root / "repair-alignment"
        layout_alignment.mkdir()
        alignment_units = layout_manifest["utterances"]
        accepted_words = [
            {"source_id": alignment_units[0]["id"], "text": "Merhaba.",
             "start_ms": 1200, "end_ms": 3800},
            {"source_id": alignment_units[1]["id"], "text": "Dünya.",
             "start_ms": 4300, "end_ms": 7800},
        ]
        alignment_result = {
            "video_sha256": digest(video), "model": "synthetic-aligner",
            "audio_start_ms": 0, "audio_end_ms": 12_000,
            "input_sha256": ALIGNER["alignment_input"](
                alignment_units, 0, 12_000, digest(video), "synthetic-aligner"
            ),
            "utterances": [
                {"id": unit["id"], "text": unit["text"],
                 "source_cue_ids": unit["cue_ids"], "status": "aligned",
                 "word_timings": [{"text": word["text"],
                                   "start_ms": word["start_ms"],
                                   "end_ms": word["end_ms"]}]}
                for unit, word in zip(alignment_units, accepted_words)
            ],
        }
        (layout_alignment / "000.json").write_text(
            json.dumps(alignment_result), encoding="utf-8"
        )
        repair_layout_report = root / "repair-layout-audit.json"
        LAYOUT_AUDIT["run"](video, layout_map, layout_alignment,
                            repair_layout_report, 700, 25)
        new_bundle = run("bundle", reference_case, target, 1000, 10000)["bundle"]
        repair_decision = {
            "start_ms": 1000, "end_ms": 10000,
            "source_sha256": digest(working_pair), "target_sha256": digest(target),
            "replace_source_ids": [1, 2], "replace_target_ids": [1, 2],
            "reviewer": "synthetic self-check",
            "reason": "Retimed separate language layouts with accepted word spans.",
            "evidence": [new_bundle],
            "review_result": synthetic_audio_review(
                root, video, working_pair, 1000, 10000, "layout-repair"
            ),
            "semantic_manifest": str(layout_map),
            "layout_report": str(repair_layout_report),
            "alignment_source_ids": [unit["id"] for unit in alignment_units],
            "alignment_reason": "The synthetic word spans anchor both display intervals.",
            "accepted_words": accepted_words,
            "source_cues": [
                {"start_ms": 1000, "end_ms": 4200, "text": "Merhaba."},
                {"start_ms": 4200, "end_ms": 8000, "text": "Dünya."},
            ],
            "target_cues": [
                {"start_ms": 1000, "end_ms": 8000,
                 "text": "Hello. World."},
            ],
        }
        layout_decision_path = root / "layout-repair-decision.json"
        layout_decision_path.write_text(json.dumps(repair_decision), encoding="utf-8")
        retimed = run("layout-repair", reference_case, target, layout_decision_path)
        assert retimed["source_sha256"] == digest(working_pair)
        assert len(runpy.run_path(str(Path(__file__).with_name(
            "subtitle-timing.py")))["read_cues"](target)) == 1
        assert "Dünya." in working_pair.read_text()
        assert "Hello. World." in target.read_text()
        assert LAYOUT_AUDIT["layout_blockers"](
            repair_layout_report, layout_map, video
        )[0].startswith("Layout report is invalid")

        # A direct text correction can repair English without an audio-model call.
        semantic_source = root / "meaning.tr.srt"
        semantic_target = root / "meaning.en.srt"
        semantic_source.write_text(
            "1\n00:00:01,000 --> 00:00:03,000\nGeldi.\n", encoding="utf-8"
        )
        semantic_target.write_text(
            "1\n00:00:01,000 --> 00:00:03,000\nHe did not come.\n",
            encoding="utf-8",
        )
        semantic_case = root / "meaning-case"
        run("audit", video, semantic_source, semantic_case, "--language", "tr")
        semantic_working = semantic_case / "working.tr.srt"
        semantic_map = root / "meaning-map.json"
        SEMANTIC["prepare"](semantic_working, semantic_target, semantic_map)
        text_decision = {
            "question_type": "translation_semantics",
            "start_ms": 1000, "end_ms": 3000,
            "source_sha256": digest(semantic_working),
            "target_sha256": digest(semantic_target),
            "replace_source_ids": [1], "replace_target_ids": [1],
            "reviewer": "synthetic agent test", "reason": "Geldi is affirmative.",
            "evidence": [str(semantic_map)],
            "text_evidence": [{"kind": "source_text", "path": str(semantic_working),
                               "sha256": digest(semantic_working)},
                              {"kind": "scene_context", "path": str(semantic_map),
                               "sha256": digest(semantic_map)}],
            "cues": [{"start_ms": 1000, "end_ms": 3000,
                      "source_text": "Geldi.", "target_text": "He came."}],
        }
        text_path = root / "meaning-decision.json"
        text_path.write_text(json.dumps(text_decision), encoding="utf-8")
        original_meaning_source = semantic_working.read_bytes()
        repaired_meaning = run("replace-pair", semantic_case,
                               semantic_target, text_path)
        assert semantic_working.read_bytes() == original_meaning_source
        assert semantic_target.read_text().endswith("He came.\n")
        assert Path(repaired_meaning["decision"]).is_file()
        text_decision["source_sha256"] = digest(semantic_working)
        text_decision["target_sha256"] = digest(semantic_target)
        text_decision["cues"][0]["source_text"] = "Gitmedi."
        text_path.write_text(json.dumps(text_decision), encoding="utf-8")
        rejected_text = subprocess.run(
            ["python3", str(TOOL), "replace-pair", str(semantic_case),
             str(semantic_target), str(text_path)], capture_output=True, text=True,
        )
        assert rejected_text.returncode != 0
        assert "change English text only" in rejected_text.stderr

        # 7. A long silent-looking gap remains reviewable from start to end.

        long_video = root / "long-demo.mp4"
        subprocess.run([
            "ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=black:s=160x90:r=1:d=100",
            "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono", "-t", "100",
            "-c:v", "mpeg4", "-c:a", "aac", "-loglevel", "error", str(long_video),
        ], check=True, capture_output=True)
        long_source = root / "long-demo.tr.srt"
        long_source.write_text(
            "1\n00:00:01,000 --> 00:00:02,000\nFirst.\n\n"
            "2\n00:01:35,000 --> 00:01:36,000\nLast.\n",
            encoding="utf-8",
        )
        long_case = root / "long-case"
        run("audit", long_video, long_source, long_case, "--language", "tr")
        long_queue = json.loads((long_case / "review-queue.json").read_text())
        assert "subtitle_gap:1-2" in {item["id"] for item in long_queue["issues"]}
        long_review = run("review", long_case, "--issue-id", "subtitle_gap:1-2")
        spans = long_review["review_windows"]
        assert len(spans) >= 2 and spans[0]["start_ms"] <= 2_000
        assert spans[-1]["end_ms"] >= 95_000
        assert all(left["end_ms"] >= right["start_ms"]
                   for left, right in zip(spans, spans[1:]))
        first_clip = str(next((long_case / "clips").glob("*.json")).relative_to(long_case))
        assert runpy.run_path(str(TOOL))["SOURCE_REVIEW"]["evidence_blockers"](
            long_case, [first_clip], 2_000, 95_000, digest(long_video)
        )

        held_source = root / "held.tr.srt"
        held_source.write_text(
            "1\n00:00:20,000 --> 00:01:01,000\nAyyy!\n", encoding="utf-8"
        )
        held_case = root / "held-case"
        run("audit", long_video, held_source, held_case, "--language", "tr")
        held_review = run("review", held_case, "--issue-id", "long_cue:1")
        held_spans = held_review["review_windows"]
        assert held_spans[0]["start_ms"] <= 20_000
        assert held_spans[-1]["end_ms"] >= 61_000

        # 8. A confirmed speech gap receives valid, hash-bound cues in both tracks.

        long_target = root / "long-candidate.en.srt"
        long_target.write_text(
            "1\n00:00:01,000 --> 00:00:02,000\nFirst.\n\n"
            "2\n00:01:35,000 --> 00:01:36,000\nLast.\n", encoding="utf-8"
        )
        pair = root / "pair.json"
        pair_decision = {
            "issue_id": "subtitle_gap:1-2",
            "source_sha256": digest(long_case / "working.tr.srt"),
            "target_sha256": digest(long_target),
            "speech_start_ms": 10_000, "speech_end_ms": 12_000,
            "reason": "Synthetic confirmed speech", "evidence": [
                str(next((long_case / "clips").glob("*.wav")).relative_to(long_case))
            ],
            "review_result": synthetic_audio_review(
                root, long_video, long_case / "working.tr.srt", 10_000, 12_000,
                "paired-insertion"),
            "cues": [{"start_ms": 10_000, "end_ms": 12_000,
                      "source_text": "Konuşma.", "target_text": "Speech."}],
        }
        pair.write_text(json.dumps(pair_decision), encoding="utf-8")
        edited = run("insert-pair", long_case, long_target, pair)
        assert edited["source_sha256"] == digest(long_case / "working.tr.srt")
        assert edited["target_sha256"] == digest(long_target)
        assert "Konuşma." in (long_case / "working.tr.srt").read_text()
        assert "Speech." in long_target.read_text()
        assert not runpy.run_path(str(TOOL))["unresolved_source_issues"](
            long_case, {"issues": [{"id": "subtitle_gap:1-2", "kind": "subtitle_gap",
                                     "start_ms": 2_000, "end_ms": 95_000}]}
        )
        workbench = runpy.run_path(str(TOOL))
        remaining_gap = next(issue for issue in workbench["current_queue"](long_case)[0]["issues"]
                             if issue["kind"] == "subtitle_gap" and issue["start_ms"] == 12_000)
        review_decision = {
            "issue_id": remaining_gap["id"], "status": "unresolved",
            "reason": "Synthetic speech question", "evidence": pair_decision["evidence"],
        }
        pair.write_text(json.dumps(review_decision), encoding="utf-8")
        run("record", long_case, pair)
        assert workbench["unresolved_source_issues"](
            long_case, {"issues": [remaining_gap]}
        ) == [remaining_gap["id"]]
        review_decision.update({
            "status": "reviewed", "reviewer": "synthetic self-check",
            "expected_working_sha256": digest(long_case / "working.tr.srt"),
            "evidence": [str(path.relative_to(long_case))
                         for path in (long_case / "clips").glob("*.json")],
            "review_result": synthetic_audio_review(
                root, long_video, long_case / "working.tr.srt", 12_000, 95_000,
                "remaining-gap"),
        })
        pair.write_text(json.dumps(review_decision), encoding="utf-8")
        run("record", long_case, pair)
        assert not workbench["unresolved_source_issues"](
            long_case, {"issues": [remaining_gap]}
        )
        working = long_case / "working.tr.srt"
        working.write_text(working.read_text().replace("First.", "First line."),
                           encoding="utf-8")
        assert remaining_gap["id"] not in {
            issue["id"] for issue in workbench["current_queue"](long_case)[1]
        }

    print("check ok")


if __name__ == "__main__":
    main()
