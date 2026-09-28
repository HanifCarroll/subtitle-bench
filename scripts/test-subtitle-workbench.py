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


def run(*arguments):
    result = subprocess.run(["python3", str(TOOL), *map(str, arguments)],
                            check=True, capture_output=True, text=True)
    return json.loads(result.stdout.splitlines()[-1])


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
        audio_decisions.write_text(json.dumps({
            "audio_report_sha256": digest(checked_audio),
            "source_sha256": digest(case / "working.tr.srt"),
            "decisions": [{"start_ms": 0, "end_ms": 12000,
                           "disposition": "model_artifact",
                           "reason": "Synthetic comparison fixture",
                           "reviewer": "synthetic self-check",
                           "evidence": [str(checked_audio)]}],
        }), encoding="utf-8")
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
        evidence = next((case / "clips").glob("*.wav"))
        decision = case / "reviewed.json"
        decision.write_text(json.dumps({
            "issue_id": "long_cue:1", "status": "reviewed",
            "reason": "Synthetic no-change review test",
            "evidence": [str(evidence.relative_to(case))],
            "expected_working_sha256": digest(case / "working.tr.srt"),
            "reviewer": "synthetic self-check",
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
        }), encoding="utf-8")
        run("record", case, decision)
        assert run("review", case)["pending"] == 0
        episode_summary = run(
            "episode-check", case, target,
            "--source-language", "tr", "--target-language", "en",
            "--model", "synthetic-model", "--output", episode_output,
        )
        assert episode_summary["installation_checks_passed"]

        translation = root / "translation.json"
        summary = run("translation-audit", case / "working.tr.srt", target,
                      "--output", translation)
        assert summary["flags"] == 0 and summary["source_cues"] == 1
        assert summary["target_cues"] == 2

        # 2. A current, structurally valid pair can be installed without a release label.

        report = root / "release.json"
        checked = run("release", video, case / "working.tr.srt", target,
                      "--source-language", "tr", "--target-language", "en",
                      "--case", case, "--translation-report", translation,
                      "--audio-report", checked_audio,
                      "--audio-decisions", audio_decisions,
                      "--output", report)
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
                        "--output", report,
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
