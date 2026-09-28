#!/usr/bin/env python3
"""Run the source, audio, translation, and installation checks for one video."""

import argparse
from collections import Counter
from difflib import SequenceMatcher
import json
import os
import re
import runpy
import shutil
import subprocess
import tempfile
from argparse import Namespace
from datetime import datetime, timezone
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parent
SOURCE_REVIEW = runpy.run_path(str(SCRIPTS / "source-review.py"))
TIMING = runpy.run_path(str(SCRIPTS / "subtitle-timing.py"))
COVERAGE = runpy.run_path(str(SCRIPTS / "audit-speech-coverage.py"))
read_cues = TIMING["read_cues"]
file_hash = SOURCE_REVIEW["FILE_HASH"]


def save_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                     delete=False) as temporary:
        staged = Path(temporary.name)
        json.dump(value, temporary, ensure_ascii=False, indent=2)
        temporary.write("\n")
    try:
        os.replace(staged, path)
    finally:
        staged.unlink(missing_ok=True)


def cue_record(cue):
    return {
        "id": cue["id"], "start_ms": cue["start"], "end_ms": cue["end"],
        "text": cue["text"],
    }


def current_queue(case_directory):
    """Return issues still needing review against the current working SRT."""
    queue = SOURCE_REVIEW["build_queue"](case_directory)
    _, working = SOURCE_REVIEW["load_case"](case_directory)
    current_hash = file_hash(working)
    decisions = {}
    reviewed_intervals = {}
    for path in sorted((case_directory / "decisions").glob("*/decision.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        decisions[record["issue_id"]] = record
        interval = record.get("issue_interval")
        if interval:
            key = (interval["kind"], interval["start_ms"], interval["end_ms"])
            reviewed_intervals[key] = record["status"]

    pending = []
    for issue in queue["issues"]:
        decision = decisions.get(issue["id"])
        recorded_interval = decision.get("issue_interval") if decision else None
        same_interval = not recorded_interval or all(
            issue[key] == recorded_interval[key]
            for key in ("kind", "start_ms", "end_ms")
        )
        reviewed_current_version = decision and (
            same_interval and decision["status"] in ("reviewed", "resolved")
            and (decision.get("working_after_sha256") or decision["working_before_sha256"])
            == current_hash
        )
        interval_key = (issue["kind"], issue["start_ms"], issue["end_ms"])
        reviewed_current_version = reviewed_current_version or (
            issue["kind"] in ("subtitle_gap", "possible_speech_gap")
            and reviewed_intervals.get(interval_key) == "reviewed"
        )
        if not reviewed_current_version:
            pending.append(issue)

    return queue, pending


def issue_priority(issue):
    """Put a large corrupt span ahead of the many symptoms inside it."""
    if issue["kind"] == "repetition" and issue["end_ms"] - issue["start_ms"] >= 30_000:
        return (0, issue["start_ms"])
    if issue["kind"] == "subtitle_gap" and issue["end_ms"] - issue["start_ms"] >= 30_000:
        return (1, issue["start_ms"])

    order = {
        "overlap": 2, "possible_subtitle_without_speech": 3,
        "reference_only": 4, "subtitle_gap": 5,
        "possible_speech_gap": 6, "unresolved_seam": 7,
        "reference_disagreement": 8, "repetition": 9, "long_cue": 10,
    }
    return (order.get(issue["kind"], 10), issue["start_ms"])


def urgent_source_issues(pending):
    """Keep known severe source defects out of installed subtitles."""
    thresholds = {
        "long_cue": 20_000,
        "repetition": 30_000,
        "subtitle_gap": 30_000,
        "possible_subtitle_without_speech": 10_000,
    }
    return [item for item in pending
            if item["kind"] in thresholds
            and item["end_ms"] - item["start_ms"] >= thresholds[item["kind"]]]


def unresolved_source_issues(case_directory, queue):
    """A known speech question cannot disappear behind a duration threshold."""
    decisions = {}
    for path in sorted((case_directory / "decisions").glob("*/decision.json")):
        decision = json.loads(path.read_text(encoding="utf-8"))
        interval = decision.get("issue_interval")
        key = ((interval["kind"], interval["start_ms"], interval["end_ms"])
               if interval else decision["issue_id"])
        decisions[key] = decision["status"]

    return [issue["id"] for issue in queue["issues"]
            if decisions.get((issue["kind"], issue["start_ms"], issue["end_ms"]))
            == "unresolved" or decisions.get(issue["id"]) == "unresolved"]


def audio_decision_blockers(audio_path, decisions_path, source, video):
    """Require an explicit agent decision for each independent ASR question."""
    audio = json.loads(audio_path.read_text(encoding="utf-8"))
    if (audio.get("source_sha256") != file_hash(source)
            or audio.get("video_sha256") != file_hash(video)):
        return ["Audio comparison is stale"]
    if not decisions_path.is_file():
        return ["Audio decisions are missing"] if audio["issues"] else []

    decisions = json.loads(decisions_path.read_text(encoding="utf-8"))
    if (decisions.get("audio_report_sha256") != file_hash(audio_path)
            or decisions.get("source_sha256") != file_hash(source)):
        return ["Audio decisions do not match the current comparison"]
    entries = decisions.get("decisions")
    if not isinstance(entries, list):
        return ["Audio decisions must be a list"]
    expected = {(item["start_ms"], item["end_ms"]) for item in audio["issues"]}
    recorded = set()
    for entry in entries:
        if not isinstance(entry, dict):
            return ["Audio decision is malformed"]
        key = (entry.get("start_ms"), entry.get("end_ms"))
        evidence = entry.get("evidence")
        if (key not in expected or key in recorded
                or entry.get("disposition") not in ("source_supported", "model_artifact", "repaired")
                or not isinstance(entry.get("reason"), str) or not entry["reason"].strip()
                or not isinstance(entry.get("reviewer"), str) or not entry["reviewer"].strip()
                or not isinstance(evidence, list) or not evidence
                or any(not isinstance(path, str) or not Path(path).is_file()
                       for path in evidence)):
            return ["Audio decision is incomplete or has invalid evidence"]
        recorded.add(key)

    missing = expected - recorded
    return [f"{len(missing)} audio questions need decisions"] if missing else []


def normalize_input(path, encoding, output_directory, label):
    """Copy an explicitly encoded SRT to UTF-8 without changing the original."""
    original = path.resolve(strict=True)
    if not encoding:
        return original, None

    text = original.read_bytes().decode(encoding)
    output_directory.mkdir(parents=True, exist_ok=True)
    normalized = output_directory / f"{label}.utf8.srt"
    encoded = text.encode("utf-8")
    if normalized.exists() and normalized.read_bytes() != encoded:
        raise ValueError(f"Existing normalized {label} differs; use a new case name")

    normalized.write_bytes(encoded)
    read_cues(normalized)
    return normalized, {
        "original": str(original), "original_sha256": file_hash(original),
        "encoding": encoding, "normalized": str(normalized),
        "normalized_sha256": file_hash(normalized),
    }


def audit(args):
    # 1. Reuse the existing one-video case, speech scan, and content queue.

    if args.reference_encoding and not args.reference:
        raise ValueError("--reference-encoding needs --reference")

    input_directory = args.output.parent / f"{args.output.name}.inputs"
    args.draft, draft_provenance = normalize_input(
        args.draft, args.draft_encoding, input_directory, "draft"
    )
    reference_provenance = None
    if args.reference:
        args.reference, reference_provenance = normalize_input(
            args.reference, args.reference_encoding, input_directory, "reference"
        )

    SOURCE_REVIEW["prepare"](args)
    case_directory = args.output.resolve(strict=True)
    if draft_provenance or reference_provenance:
        save_json(case_directory / "input-normalization.json", {
            "draft": draft_provenance, "reference": reference_provenance,
        })
    if args.coverage:
        SOURCE_REVIEW["scan_coverage"](case_directory)

    queue, pending = current_queue(case_directory)
    print(json.dumps({
        "case": str(case_directory), "queue": str(case_directory / "review-queue.json"),
        "issue_counts": queue["counts"], "pending": len(pending),
        "next_issue_ids": [item["id"] for item in sorted(pending, key=issue_priority)[:5]],
        "warnings": queue["warnings"],
    }, ensure_ascii=False))


def transcribe(args):
    runpy.run_path(str(SCRIPTS / "transcribe-video.py"))["transcribe"](args)


def translate_draft(args):
    if not args.run:
        cues = read_cues(args.source.resolve(strict=True))
        print(json.dumps({"source_cues": len(cues),
                          "source_characters": sum(len(cue["text"]) for cue in cues),
                          "billable_run": False}))
        return

    runpy.run_path(str(SCRIPTS / "translate-subtitles.py"))["translate"](args)


def translation_second_opinion(args):
    runpy.run_path(str(SCRIPTS / "google-second-opinion.py"))["run"](args)


def record(args):
    SOURCE_REVIEW["record_decision"](args.case.resolve(strict=True),
                                      args.decision.resolve(strict=True))


def save_pair_revision(case_directory, case, source, target, updated, decision, issue=None):
    """Validate and install two staged SRTs, keeping copies for recovery."""

    # 1. Save both originals and validate both replacements before changing either file.

    revision = case_directory / "decisions" / datetime.now(timezone.utc).strftime(
        "%Y%m%dT%H%M%S%f"
    )
    revision.mkdir(parents=True)
    try:
        for language, path, cues in zip(("source", "target"), (source, target), updated):
            shutil.copy2(path, revision / f"{language}-before.srt")
            SOURCE_REVIEW["WRITE_SRT"](revision / f"{language}-after.srt", cues)
            _, errors = validate_cues(revision / f"{language}-after.srt",
                                      case["duration_ms"])
            if errors:
                raise ValueError("Invalid paired cue timing: " + "; ".join(errors))
    except Exception:
        shutil.rmtree(revision)
        raise

    # 2. Apply the pair and record it; restore both originals on any failure.

    try:
        shutil.copy2(revision / "source-after.srt", source)
        shutil.copy2(revision / "target-after.srt", target)

        record = {
            **decision, "status": "resolved",
            "issue_id": decision.get("issue_id") or (
                f"paired_edit:{decision['start_ms']}-{decision['end_ms']}"
            ),
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "working_before_sha256": file_hash(revision / "source-before.srt"),
            "working_after_sha256": file_hash(source),
            "source_after_sha256": file_hash(source),
            "target_after_sha256": file_hash(target),
        }
        if issue:
            record["issue_interval"] = {
                key: issue[key] for key in ("kind", "start_ms", "end_ms")
            }
        save_json(revision / "decision.json", record)
    except BaseException as error:
        restore_errors = []
        for language, path in (("source", source), ("target", target)):
            try:
                shutil.copy2(revision / f"{language}-before.srt", path)
            except Exception as restore_error:
                restore_errors.append(f"{language}: {restore_error}")
        if restore_errors:
            raise RuntimeError(
                f"Paired edit failed; restore from {revision}: {'; '.join(restore_errors)}"
            ) from error
        raise

    print(json.dumps({"decision": str(revision / "decision.json"),
                      "source_sha256": file_hash(source),
                      "target_sha256": file_hash(target)}))


def insert_pair(args):
    """Fill one confirmed speech gap in both working tracks from one decision."""
    # 1. Bind the decision to the current files and reviewed gap.

    case_directory = args.case.resolve(strict=True)
    case, source = SOURCE_REVIEW["load_case"](case_directory)
    target = args.target.resolve(strict=True)
    decision = json.loads(args.decision.read_text(encoding="utf-8"))
    queue, _ = current_queue(case_directory)
    issue = next((item for item in queue["issues"]
                  if item["id"] == decision.get("issue_id")), None)
    if issue is None or issue["kind"] != "subtitle_gap":
        raise ValueError("Decision must name a current subtitle gap")
    if (source == target or target == Path(case["video"]).with_suffix(".en.srt").resolve()
            or decision.get("source_sha256") != file_hash(source)
            or decision.get("target_sha256") != file_hash(target)):
        raise ValueError("Pair decision has stale or invalid subtitle hashes")
    evidence = decision.get("evidence", [])
    if (not decision.get("reason") or not isinstance(evidence, list) or not evidence
            or any(not isinstance(item, str) or not (case_directory / item).is_file()
                   for item in evidence)):
        raise ValueError("Pair decision needs a reason and local evidence files")
    additions = decision.get("cues", [])
    if not isinstance(additions, list) or not additions:
        raise ValueError("Pair decision needs timed cues")

    # 2. Reject blank text, overlap, and any uncovered part of confirmed speech.

    source_cues = read_cues(source)
    target_cues = read_cues(target)
    for cue in additions:
        if (not isinstance(cue, dict)
                or any(type(cue.get(key)) is not int for key in ("start_ms", "end_ms"))
                or not isinstance(cue.get("source_text"), str)
                or not cue["source_text"].strip()
                or not isinstance(cue.get("target_text"), str)
                or not cue["target_text"].strip()
                or not issue["start_ms"] <= cue["start_ms"] < cue["end_ms"] <= issue["end_ms"]):
            raise ValueError("Pair cues need nonempty text inside the named gap")
    additions.sort(key=lambda cue: cue["start_ms"])
    speech_start = decision.get("speech_start_ms")
    speech_end = decision.get("speech_end_ms")
    if (type(speech_start) is not int or type(speech_end) is not int
            or not issue["start_ms"] <= speech_start < speech_end <= issue["end_ms"]
            or additions[0]["start_ms"] > speech_start + 500
            or additions[-1]["end_ms"] < speech_end - 500
            or any(right["start_ms"] - left["end_ms"] > 1000
                   for left, right in zip(additions, additions[1:]))):
        raise ValueError("Timed cues must cover the confirmed speech interval")

    updated = []
    for existing, text_key in ((source_cues, "source_text"),
                               (target_cues, "target_text")):
        merged = [{"start_ms": cue["start"], "end_ms": cue["end"],
                   "text": cue["text"]} for cue in existing]
        merged.extend({"start_ms": cue["start_ms"], "end_ms": cue["end_ms"],
                       "text": cue[text_key].strip()} for cue in additions)
        merged.sort(key=lambda cue: cue["start_ms"])
        if any(left["end_ms"] > right["start_ms"]
               for left, right in zip(merged, merged[1:])):
            raise ValueError("Pair insertion would overlap existing cues")
        updated.append(merged)

    # 3. Stage and apply both tracks with recoverable before/after copies.

    save_pair_revision(case_directory, case, source, target, updated, decision, issue)


def replace_pair(args):
    """Replace existing cue ranges in both languages on one shared timeline."""

    # 1. Bind the edit to the current video, files, evidence, and cue ranges.

    case_directory = args.case.resolve(strict=True)
    case, source = SOURCE_REVIEW["load_case"](case_directory)
    target = args.target.resolve(strict=True)
    decision = json.loads(args.decision.read_text(encoding="utf-8"))
    if file_hash(Path(case["video"])) != case["video_sha256"]:
        raise ValueError("Video differs from the review case")
    if (source == target or target == Path(case["video"]).with_suffix(".en.srt").resolve()
            or decision.get("source_sha256") != file_hash(source)
            or decision.get("target_sha256") != file_hash(target)):
        raise ValueError("Pair decision has stale or invalid subtitle hashes")
    start, end = decision.get("start_ms"), decision.get("end_ms")
    if (type(start) is not int or type(end) is not int
            or not 0 <= start < end <= case["duration_ms"]):
        raise ValueError("Pair decision needs a valid video-relative interval")
    evidence = decision.get("evidence")
    if (not isinstance(decision.get("reason"), str) or not decision["reason"].strip()
            or not isinstance(decision.get("reviewer"), str) or not decision["reviewer"].strip()
            or not isinstance(evidence, list) or not evidence
            or any(not isinstance(item, str) or not (case_directory / item).is_file()
                   for item in evidence)):
        raise ValueError("Pair decision needs a reviewer, reason, and local evidence")
    additions = decision.get("cues")
    if not isinstance(additions, list) or not additions:
        raise ValueError("Pair decision needs timed bilingual cues")

    issue = None
    if decision.get("issue_id"):
        queue, _ = current_queue(case_directory)
        issue = next((item for item in queue["issues"]
                      if item["id"] == decision["issue_id"]), None)
        if issue is None or issue["start_ms"] >= end or issue["end_ms"] <= start:
            raise ValueError("Named issue is not current in the edit interval")

    # 2. Validate paired replacements against the selected existing cue spans.

    for cue in additions:
        if (not isinstance(cue, dict)
                or any(type(cue.get(key)) is not int for key in ("start_ms", "end_ms"))
                or not start <= cue["start_ms"] < cue["end_ms"] <= end
                or any(not isinstance(cue.get(key), str) or not cue[key].strip()
                       for key in ("source_text", "target_text"))):
            raise ValueError("Pair cues need timed, nonempty text inside the edit interval")
    if any(left["end_ms"] > right["start_ms"]
           for left, right in zip(additions, additions[1:])):
        raise ValueError("Replacement cues must be ordered and nonoverlapping")

    updated = []
    for path, ids_key, text_key in (
        (source, "replace_source_ids", "source_text"),
        (target, "replace_target_ids", "target_text"),
    ):
        existing = read_cues(path)
        ids = decision.get(ids_key)
        if (not isinstance(ids, list) or not ids
                or any(type(cue_id) is not int for cue_id in ids)
                or ids != list(range(ids[0], ids[-1] + 1))
                or not 1 <= ids[0] <= ids[-1] <= len(existing)):
            raise ValueError(f"{ids_key} must name a contiguous existing cue range")
        selected = existing[ids[0] - 1:ids[-1]]
        if any(cue["start"] < start or cue["end"] > end for cue in selected):
            raise ValueError("Selected cues extend beyond the edit interval")
        replacement = [{"start_ms": cue["start_ms"], "end_ms": cue["end_ms"],
                        "text": cue[text_key]} for cue in additions]
        updated.append(SOURCE_REVIEW["splice_cues"](
            existing, {"replace_ids": ids, "replacement": replacement},
            case["duration_ms"],
        ))

    # 3. Stage and apply both tracks with recoverable before/after copies.

    save_pair_revision(case_directory, case, source, target, updated, decision, issue)


def gap_review_windows(issue, duration_ms, context_seconds):
    """Cover a long subtitle-free span with overlapping review clips."""
    if context_seconds < 0:
        raise ValueError("Review context must be nonnegative")

    context_ms = round(context_seconds * 1000)
    start = max(0, issue["start_ms"] - context_ms)
    end = min(duration_ms, issue["end_ms"] + context_ms)
    windows = []
    cursor = start
    while cursor < end:
        window_end = min(cursor + 50_000, end)
        windows.append((cursor, window_end))
        if window_end == end:
            break

        cursor = window_end - 2_000

    return windows


def bundle(args):
    """Collect one interval's playable clips and subtitle/ASR evidence."""

    # 1. Check inputs and extract bounded clips from the original video.

    case_directory = args.case.resolve(strict=True)
    case, source = SOURCE_REVIEW["load_case"](case_directory)
    target = args.target.resolve(strict=True)
    if file_hash(Path(case["video"])) != case["video_sha256"]:
        raise ValueError("Video differs from the review case")
    if source == target or not 0 <= args.start_ms < args.end_ms <= case["duration_ms"]:
        raise ValueError("Choose separate tracks and a valid video-relative interval")
    output = args.output or case_directory / "bundles" / f"{args.start_ms}-{args.end_ms}.json"
    protected = {source, target, Path(case["video"]).resolve(),
                 case_directory / "case.json", case_directory / "review-queue.json"}
    protected.update(path.resolve() for path in args.asr_manifest)
    if args.audio_report:
        protected.add(args.audio_report.resolve())
    if output.suffix.lower() != ".json" or output.resolve() in protected:
        raise ValueError("Bundle output must be a separate .json file")
    windows = gap_review_windows({"start_ms": args.start_ms, "end_ms": args.end_ms},
                                 case["duration_ms"], args.context)
    timeline_start, timeline_end = windows[0][0], windows[-1][1]
    clips = []
    reference = {}
    issues = {}
    decisions = {}
    for start, end in windows:
        SOURCE_REVIEW["inspect"](case_directory, (start + end) / 2000,
                                 (end - start) / 2000, (end - start) / 2000)
        inspection = case_directory / "clips" / f"{start}-{end}.json"
        report = json.loads(inspection.read_text(encoding="utf-8"))
        clips.append({key: report[key] for key in
                      ("video_start_ms", "video_end_ms", "audio_clip", "video_clip",
                       "audio_sha256")})
        for cue in report["reference_cues"]:
            reference[cue["id"]] = cue
        for issue in report["issues"]:
            issues[issue["id"]] = issue
        for decision in report["recorded_decisions"]:
            decisions[decision["path"]] = decision

    # 2. Put Turkish, English, reference, and saved ASR on the video clock.

    timeline = []
    for kind, path in (("turkish", source), ("english", target)):
        for cue in read_cues(path):
            if cue["start"] < timeline_end and cue["end"] > timeline_start:
                timeline.append({"kind": kind, "start_ms": cue["start"],
                                 "end_ms": cue["end"], "text": cue["text"],
                                 "cue_id": cue["id"], "origin": str(path),
                                 "granularity": "cue"})
    for cue in reference.values():
        if cue["video_start_ms"] < timeline_end and cue["video_end_ms"] > timeline_start:
            timeline.append({"kind": "reference", "start_ms": cue["video_start_ms"],
                             "end_ms": cue["video_end_ms"], "text": cue["text"],
                             "cue_id": cue["id"], "origin": case["reference"],
                             "granularity": "cue"})

    asr_inputs = []
    if args.audio_report:
        path = args.audio_report.resolve(strict=True)
        report = json.loads(path.read_text(encoding="utf-8"))
        if report.get("video_sha256") != case["video_sha256"]:
            raise ValueError("Audio report belongs to a different video")
        asr_inputs.append({"path": str(path), "sha256": file_hash(path),
                           "source_stale": report.get("source_sha256") != file_hash(source)})
        for window in report["windows"]:
            if window["start_ms"] < timeline_end and window["end_ms"] > timeline_start:
                timeline.append({"kind": "asr", "start_ms": window["start_ms"],
                                 "end_ms": window["end_ms"], "text": window["text"],
                                 "origin": str(path), "model": report.get("model"),
                                 "granularity": "window"})
    for manifest_path in args.asr_manifest:
        path = manifest_path.resolve(strict=True)
        manifest = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(manifest, dict):
            if (manifest.get("video_sha256")
                    and manifest["video_sha256"] != case["video_sha256"]):
                raise ValueError("ASR manifest belongs to a different video")
            entries = manifest["windows"]
        else:
            entries = manifest
        if not isinstance(entries, list):
            raise ValueError("ASR manifest needs a list of windows")
        source_hash = manifest.get("source_sha256") if isinstance(manifest, dict) else None
        asr_inputs.append({"path": str(path), "sha256": file_hash(path),
                           "source_stale": (source_hash != file_hash(source)
                                            if source_hash else None)})
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("whisper_srt"), str):
                raise ValueError("ASR windows need a subtitle path")
            clip_start = entry.get("clip_start_ms", entry.get("start_ms"))
            srt_path = Path(entry["whisper_srt"])
            if not srt_path.is_absolute():
                srt_path = path.parent / srt_path
            srt_path = srt_path.resolve(strict=True)
            if type(clip_start) is not int:
                raise ValueError("ASR window needs an original-video start time")
            for cue in read_cues(srt_path):
                start, end = clip_start + cue["start"], clip_start + cue["end"]
                if start < timeline_end and end > timeline_start:
                    timeline.append({"kind": "asr", "start_ms": start,
                                     "end_ms": end, "text": cue["text"],
                                     "origin": str(srt_path), "model": "Whisper",
                                     "granularity": "cue"})

    # 3. Save the evidence with hashes; model results remain review questions.

    timeline.sort(key=lambda item: (item["start_ms"], item["end_ms"], item["kind"]))
    report = {
        "case": str(case_directory), "start_ms": args.start_ms, "end_ms": args.end_ms,
        "video_sha256": case["video_sha256"], "source_sha256": file_hash(source),
        "target_sha256": file_hash(target), "reference_alignment": case["reference_alignment"],
        "clips": clips, "issues": sorted(issues.values(), key=lambda item: item["start_ms"]),
        "recorded_decisions": list(decisions.values()),
        "asr_inputs": asr_inputs, "timeline": timeline,
        "note": "ASR windows have coarse timing. Compare disputed words with the original clips.",
    }
    save_json(output, report)
    print(json.dumps({"bundle": str(output), "clips": len(clips),
                      "timeline_entries": len(timeline)}, ensure_ascii=False))


def review(args):
    # 1. Select a pending issue, then reuse the original-audio clip extractor.

    case_directory = args.case.resolve(strict=True)
    _, pending = current_queue(case_directory)
    if args.issue_id:
        chosen = next((item for item in pending if item["id"] == args.issue_id), None)
        if chosen is None:
            raise ValueError("Issue is not pending in this case")
    else:
        chosen = min(pending, key=issue_priority) if pending else None

    if chosen is None:
        print(json.dumps({"case": str(case_directory), "pending": 0}))
        return

    review_windows = []
    if chosen["kind"] == "subtitle_gap":
        case, _ = SOURCE_REVIEW["load_case"](case_directory)
        review_windows = gap_review_windows(chosen, case["duration_ms"], args.context)
        for start, end in review_windows:
            center = (start + end) / 2000
            half_duration = (end - start) / 2000
            SOURCE_REVIEW["inspect"](case_directory, center, half_duration, half_duration)
    else:
        center_ms = (chosen["start_ms"] + min(chosen["end_ms"], chosen["start_ms"] + 20_000)) / 2
        center = max(0, center_ms / 1000)
        SOURCE_REVIEW["inspect"](case_directory, center, args.context, args.context)
    cue_ids = chosen.get("cue_ids", [])
    summary = {key: value for key, value in chosen.items() if key != "cue_ids"}
    if cue_ids:
        summary["cue_range"] = [cue_ids[0], cue_ids[-1]]
    print(json.dumps({"issue": summary, "pending": len(pending),
                      "review_windows": [{"start_ms": start, "end_ms": end}
                                         for start, end in review_windows]}, ensure_ascii=False))


def translation_audit(args):
    # 1. Match tracks by time, allowing each language its own cue boundaries.

    source = args.source.resolve(strict=True)
    target = args.target.resolve(strict=True)
    if (source == target or args.output.resolve() in (source, target) or
            args.output.suffix.lower() != ".json"):
        raise ValueError("Source, target, and report must be separate files")

    source_cues = read_cues(source)
    target_cues = read_cues(target)
    last_end = max((cue["end"] for cue in source_cues + target_cues), default=0)
    window_count = (last_end + 59_999) // 60_000
    windows = []
    for index in range(window_count):
        start, end = index * 60_000, (index + 1) * 60_000
        windows.append({
            "id": index + 1, "start_ms": start, "end_ms": end,
            "source": [cue_record(cue) for cue in source_cues
                       if cue["start"] < end and cue["end"] > start],
            "target": [cue_record(cue) for cue in target_cues
                       if cue["start"] < end and cue["end"] > start],
        })

    # 2. Flag mechanical gaps and suspicious target repetition for review.

    flags = []
    # ponytail: pairwise scans suit a few thousand cues; index times for much larger files.
    for label, cues, counterparts in (
        ("source_without_target", source_cues, target_cues),
        ("target_without_source", target_cues, source_cues),
    ):
        for cue in cues:
            if not any(other["start"] < cue["end"] and other["end"] > cue["start"]
                       for other in counterparts):
                flags.append({"id": f"{label}:{cue['id']}", "kind": label,
                              "start_ms": cue["start"], "end_ms": cue["end"],
                              "cue": cue_record(cue)})

    run_start = 0
    for index in range(1, len(target_cues) + 1):
        same = (index < len(target_cues) and
                SOURCE_REVIEW["normalized"](target_cues[index]["text"]) ==
                SOURCE_REVIEW["normalized"](target_cues[run_start]["text"]))
        if same:
            continue

        run = target_cues[run_start:index]
        if len(run) >= 3 and len(SOURCE_REVIEW["normalized"](run[0]["text"])) >= 8:
            flags.append({"id": f"repeated_target:{run[0]['id']}-{run[-1]['id']}",
                          "kind": "repeated_target", "start_ms": run[0]["start"],
                          "end_ms": run[-1]["end"], "cue_ids": [cue["id"] for cue in run]})
        run_start = index

    report = {
        "source": str(source), "source_sha256": file_hash(source),
        "target": str(target), "target_sha256": file_hash(target),
        "source_cues": len(source_cues), "target_cues": len(target_cues),
        "flags": sorted(flags, key=lambda item: (item["start_ms"], item["id"])),
        "windows": windows,
        "note": "Mechanical flags do not establish translation meaning. Review every window against the source.",
    }
    save_json(args.output, report)
    print(json.dumps({"report": str(args.output), "windows": len(windows),
                      "flags": len(flags), "source_cues": len(source_cues),
                      "target_cues": len(target_cues)}))


def words(text):
    return re.findall(r"[^\W\d_]+", text.casefold().replace("i\u0307", "i"))


def repeated_phrase(tokens):
    for width in range(1, 5):
        for start in range(len(tokens) - width * 4 + 1):
            phrase = tokens[start:start + width]
            if all(tokens[start + width * repeat:start + width * (repeat + 1)] == phrase
                   for repeat in range(1, 4)):
                return True

    return False


def compare_audio_window(transcript, cue_text):
    """Raise a question when independently heard words are absent from the SRT."""
    heard = words(transcript)
    written = words(cue_text)
    counts = Counter(heard)
    looped = (any(len(word) > 40 for word in heard)
              or repeated_phrase(heard)
              or (len(heard) >= 8 and max(counts.values()) / len(heard) > 0.45))
    shared = sum((counts & Counter(written)).values())
    agreement = round(shared / len(heard), 3) if heard else None
    unmatched = []
    for tag, left, right, _, _ in SequenceMatcher(
        None, heard, written, autojunk=False
    ).get_opcodes():
        if tag in ("delete", "replace"):
            unmatched.append(heard[left:right])

    longest_unmatched = max(unmatched, key=len, default=[])
    if looped:
        issue = "repeated_asr_output"
    elif len(heard) >= 6 and (agreement < 0.25 or len(longest_unmatched) >= 8):
        issue = "possible_missing_or_wrong_subtitle"
    else:
        issue = None

    return {"heard_words": len(heard), "written_words": len(written),
            "word_agreement": agreement,
            "longest_unmatched_words": len(longest_unmatched),
            "unmatched_example": " ".join(longest_unmatched[:20]), "issue": issue}


def audio_check(args):
    """Compare local Qwen recognition with every video window, retaining raw evidence."""
    # 1. Bind resumable transcripts to the video and pinned model.

    case_directory = args.case.resolve(strict=True)
    case, working = SOURCE_REVIEW["load_case"](case_directory)
    video = Path(case["video"])
    if file_hash(video) != case["video_sha256"]:
        raise ValueError("Video differs from the review case")
    protected = {video, working, case_directory / "case.json",
                 case_directory / "review-queue.json",
                 case_directory / "speech-coverage.json"}
    if (args.output.suffix.lower() != ".json" or args.cache.suffix.lower() != ".json"
            or args.output.resolve() == args.cache.resolve()
            or args.output.resolve() in protected or args.cache.resolve() in protected):
        raise ValueError("Use separate .json audio report and cache files outside case inputs")

    duration_ms = case["duration_ms"]
    window_ms = round(args.window_seconds * 1000)
    if window_ms < 10_000 or window_ms > 60_000:
        raise ValueError("Window duration must be between 10 and 60 seconds")
    if args.max_tokens < 1:
        raise ValueError("Max tokens must be positive")
    if args.start_seconds < 0 or (args.end_seconds is not None
                                  and args.end_seconds > duration_ms / 1000):
        raise ValueError("Requested scan is outside the video")
    start_ms = round(args.start_seconds * 1000)
    end_ms = round(args.end_seconds * 1000) if args.end_seconds else duration_ms
    if start_ms >= end_ms:
        raise ValueError("Scan end must follow its start")

    identity = {"video_sha256": case["video_sha256"], "model": args.model,
                "language": args.language, "window_ms": window_ms,
                "max_tokens": args.max_tokens}
    if args.cache.exists():
        cache = json.loads(args.cache.read_text(encoding="utf-8"))
        if any(cache.get(key) != value for key, value in identity.items()):
            raise ValueError("Audio transcript cache belongs to different inputs or settings")
    else:
        cache = {**identity, "windows": {}}

    # 2. Transcribe only uncached windows of original audio, with one model load.

    starts = range(start_ms, end_ms, window_ms)
    missing = [
        start for start in starts
        if (str(start) not in cache["windows"]
            or cache["windows"][str(start)]["end_ms"] != min(start + window_ms, end_ms))
    ]
    if missing:
        try:
            from mlx_audio.stt.utils import load_model
        except ImportError as error:
            raise RuntimeError(
                "Run audio-check with a Python environment containing mlx-audio"
            ) from error

        model = load_model(args.model)
        with tempfile.TemporaryDirectory(prefix="subtitle-audio-check-") as directory:
            clip = Path(directory) / "window.wav"
            for start in missing:
                end = min(start + window_ms, end_ms)
                subprocess.run([
                    "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-ss", f"{start / 1000:.3f}", "-t", f"{(end - start) / 1000:.3f}",
                    "-i", str(video), "-vn", "-ac", "1", "-ar", "16000",
                    "-c:a", "pcm_s16le", str(clip),
                ], check=True, capture_output=True)
                result = model.generate(str(clip), language=args.language,
                                        max_tokens=args.max_tokens)
                cache["windows"][str(start)] = {
                    "start_ms": start, "end_ms": end, "text": result.text.strip(),
                }
                save_json(args.cache, cache)
                clip.unlink()

    # 3. Compare against the current source draft without reusing old judgments.

    cues = read_cues(working)
    windows = []
    for start in starts:
        transcript = cache["windows"][str(start)]
        source_text = " ".join(cue["text"] for cue in cues
                               if cue["start"] < transcript["end_ms"]
                               and cue["end"] > start)
        windows.append({**transcript, **compare_audio_window(transcript["text"], source_text)})

    report = {"video": str(video), "video_sha256": case["video_sha256"],
              "source": str(working), "source_sha256": file_hash(working),
              "model": args.model, "language": args.language,
              "start_ms": start_ms, "end_ms": end_ms, "window_ms": window_ms,
              "transcript_cache": str(args.cache), "windows": windows,
              "issues": [item for item in windows if item["issue"]],
              "note": "ASR disagreement raises review questions; silence or agreement does not clear audio."}
    save_json(args.output, report)
    print(json.dumps({"report": str(args.output), "windows": len(windows),
                      "issues": len(report["issues"])}))


def episode_check(args):
    """Refresh every automated check for the current pair in one command."""
    # 1. Refresh the source audit after edits.

    case_directory = args.case.resolve(strict=True)
    case, source = SOURCE_REVIEW["load_case"](case_directory)
    args.output.mkdir(parents=True, exist_ok=True)
    coverage_hash = case_directory / "speech-coverage.sha256"
    if (not coverage_hash.is_file()
            or coverage_hash.read_text().strip() != file_hash(source)):
        SOURCE_REVIEW["scan_coverage"](case_directory)
    queue, pending = current_queue(case_directory)

    # 2. Recompare local audio and English against this source version.

    audio_report = args.output / "audio-check.json"
    audio_check(Namespace(
        case=case_directory, output=audio_report,
        cache=args.output / "audio-transcripts.json", model=args.model,
        language=args.audio_language, window_seconds=30,
        start_seconds=0, end_seconds=None, max_tokens=256,
    ))
    translation_report = args.output / "translation-audit.json"
    translation_audit(Namespace(source=source, target=args.target,
                                output=translation_report))

    # 3. Produce one install check and an issue summary for the agent.

    release_report = args.output / "release-check.json"
    release(Namespace(
        video=Path(case["video"]), source=source, target=args.target,
        source_language=args.source_language, target_language=args.target_language,
        case=case_directory, translation_report=translation_report,
        audio_report=audio_report, audio_decisions=args.output / "audio-decisions.json",
        output=release_report, apply=False, backup_dir=None,
    ))
    audio = json.loads(audio_report.read_text(encoding="utf-8"))
    translation = json.loads(translation_report.read_text(encoding="utf-8"))
    installation = json.loads(release_report.read_text(encoding="utf-8"))
    summary = {
        "case": str(case_directory), "source_sha256": file_hash(source),
        "target_sha256": file_hash(args.target),
        "source_issues": len(pending), "source_issue_counts": queue["counts"],
        "audio_questions": len(audio["issues"]),
        "translation_flags": len(translation["flags"]),
        "installation_checks_passed": installation["installation_checks_passed"],
        "blockers": installation["blockers"],
        "reports": {"audio": str(audio_report), "translation": str(translation_report),
                    "release": str(release_report)},
    }
    save_json(args.output / "episode-check.json", summary)
    print(json.dumps(summary, ensure_ascii=False))


def validate_cues(path, video_duration_ms):
    cues = read_cues(path)
    errors = []
    for cue in cues:
        if cue["end"] > video_duration_ms:
            errors.append(f"cue {cue['id']} ends after video")
    for previous, following in zip(cues, cues[1:]):
        if previous["start"] > following["start"]:
            errors.append(f"cue {following['id']} is out of order")
        if previous["end"] > following["start"]:
            errors.append(f"cues {previous['id']} and {following['id']} overlap")

    return cues, errors


def playback_samples(source_cues, target_cues):
    """Choose early, middle, and late speech cues for native player checks."""
    if not source_cues:
        return []

    samples = []
    chosen_ids = set()
    for fraction in (0.1, 0.5, 0.9):
        source = source_cues[round((len(source_cues) - 1) * fraction)]
        if source["id"] in chosen_ids:
            continue

        chosen_ids.add(source["id"])
        at_ms = (source["start"] + source["end"]) // 2
        target = next((cue for cue in target_cues
                       if cue["start"] <= at_ms < cue["end"]), None)
        samples.append({"at_ms": at_ms, "source": cue_record(source),
                        "target": cue_record(target) if target else None})

    return samples


def release(args):
    # 1. Check candidate files, current audit evidence, and the original video.

    language_tag = r"[A-Za-z]{2,8}(?:-[A-Za-z0-9]{2,8})*"
    if (not re.fullmatch(language_tag, args.source_language) or
            not re.fullmatch(language_tag, args.target_language) or
            args.output.suffix.lower() != ".json"):
        raise ValueError("Use valid language tags and a .json output report")

    video = args.video.resolve(strict=True)
    source = args.source.resolve(strict=True)
    target = args.target.resolve(strict=True)
    case_directory = args.case.resolve(strict=True)
    translation_path = args.translation_report.resolve(strict=True)
    audio_path = args.audio_report.resolve(strict=True)
    decisions_path = args.audio_decisions.resolve()
    review_paths = {translation_path, audio_path, decisions_path}
    destinations = [video.with_suffix(f".{args.source_language}.srt"),
                    video.with_suffix(f".{args.target_language}.srt")]
    protected_paths = {video, source, target}
    protected_paths.update(destinations)
    protected_paths.update(review_paths)
    protected_paths.update(case_directory / name for name in (
        "case.json", "review-queue.json", "speech-coverage.json", "speech-coverage.sha256"
    ))
    if (source == target or destinations[0] == destinations[1] or
            args.output.resolve() in protected_paths):
        raise ValueError("Output report must differ from media, subtitles, and review files")

    case, working = SOURCE_REVIEW["load_case"](case_directory)
    translation = json.loads(translation_path.read_text(encoding="utf-8"))
    blockers = []
    if case["video"] != str(video) or case["video_sha256"] != file_hash(video):
        blockers.append("Review case does not match this video")
    if file_hash(source) != file_hash(working):
        blockers.append("Source candidate differs from the reviewed working copy")
    if (translation["source_sha256"] != file_hash(source) or
            translation["target_sha256"] != file_hash(target)):
        blockers.append("Translation report is stale")
    blockers.extend(audio_decision_blockers(audio_path, decisions_path, source, video))

    duration_ms = round(COVERAGE["duration_seconds"](video) * 1000)
    source_cues, source_errors = validate_cues(source, duration_ms)
    target_cues, target_errors = validate_cues(target, duration_ms)
    blockers.extend(source_errors + target_errors)
    queue, pending = current_queue(case_directory)
    if pending:
        blockers.append(f"{len(pending)} source questions need decisions")
    urgent = urgent_source_issues(pending)
    if urgent:
        blockers.append(f"{len(urgent)} severe source issues need review before installation")
    open_coverage = [item["id"] for item in pending
                     if item["kind"] in ("subtitle_gap", "possible_speech_gap")]
    if open_coverage:
        blockers.append(f"{len(open_coverage)} speech coverage questions need decisions")
    unresolved = unresolved_source_issues(case_directory, queue)
    if unresolved:
        blockers.append(f"{len(unresolved)} known speech questions need a subtitle decision")
    if translation["flags"]:
        blockers.append(f"{len(translation['flags'])} English timing questions need repair")
    coverage_hash = case_directory / "speech-coverage.sha256"
    if not coverage_hash.is_file() or coverage_hash.read_text().strip() != file_hash(working):
        blockers.append("Speech coverage scan is missing or stale")

    installation_checks_passed = not blockers

    report = {
        "video": str(video), "source": str(source), "target": str(target),
        "destinations": [str(path) for path in destinations],
        "source_cues": len(source_cues), "target_cues": len(target_cues),
        "playback_samples": playback_samples(source_cues, target_cues),
        "pending_source_issues": len(pending), "translation_flags": len(translation["flags"]),
        "urgent_source_issue_ids": [item["id"] for item in urgent],
        "open_coverage_issue_ids": open_coverage,
        "unresolved_source_issue_ids": unresolved,
        "blockers": blockers,
        "installation_checks_passed": installation_checks_passed,
        "installed": False,
    }
    save_json(args.output, report)
    if not args.apply:
        print(json.dumps({"report": str(args.output),
                          "installation_checks_passed": installation_checks_passed,
                          "blockers": report["blockers"]}, ensure_ascii=False))
        return

    if not installation_checks_passed:
        raise ValueError("Release blocked: " + "; ".join(report["blockers"]))
    if not args.backup_dir or args.backup_dir.exists():
        raise ValueError("Apply needs a new --backup-dir")

    # 2. Back up both destinations, then replace them with verified candidates.

    args.backup_dir.mkdir(parents=True)
    backup_manifest = {}
    for destination in destinations:
        backup_manifest[destination.name] = (
            {"sha256": file_hash(destination)} if destination.exists() else None
        )
        if destination.exists():
            shutil.copy2(destination, args.backup_dir / destination.name)
            if file_hash(args.backup_dir / destination.name) != file_hash(destination):
                raise OSError("Backup verification failed")

    save_json(args.backup_dir / "manifest.json", backup_manifest)
    staged = []
    try:
        for candidate, destination in zip((source, target), destinations):
            with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as temporary:
                staged_path = Path(temporary.name)
            shutil.copy2(candidate, staged_path)
            if file_hash(candidate) != file_hash(staged_path):
                raise OSError("Staged subtitle checksum differs")
            staged.append((staged_path, destination))

        for staged_path, destination in staged:
            os.replace(staged_path, destination)
        if any(file_hash(candidate) != file_hash(destination)
               for candidate, destination in zip((source, target), destinations)):
            raise OSError("Installed subtitle checksum differs")
    except Exception:
        for destination in destinations:
            backup = args.backup_dir / destination.name
            if backup.exists():
                shutil.copy2(backup, destination)
            else:
                destination.unlink(missing_ok=True)
        raise
    finally:
        for staged_path, _ in staged:
            staged_path.unlink(missing_ok=True)

    report["installed"] = True
    report["backup_dir"] = str(args.backup_dir)
    save_json(args.output, report)
    print(json.dumps({"report": str(args.output), "installed": True,
                      "backup_dir": str(args.backup_dir)}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    auditing = commands.add_parser("audit", help="prepare and audit one video")
    auditing.add_argument("video", type=Path)
    auditing.add_argument("draft", type=Path)
    auditing.add_argument("output", type=Path, help="new case directory")
    auditing.add_argument("--language", required=True)
    auditing.add_argument("--reference", type=Path)
    auditing.add_argument("--draft-encoding")
    auditing.add_argument("--reference-encoding")
    auditing.add_argument("--reference-offset-ms", type=int)
    auditing.add_argument("--reference-timing-only", action="store_true")
    auditing.add_argument("--reference-url")
    auditing.add_argument("--seam-report", type=Path)
    auditing.add_argument("--coverage", action="store_true")

    transcribing = commands.add_parser("transcribe", help="make a source draft from video")
    transcribing.add_argument("video", type=Path)
    transcribing.add_argument("output", type=Path)
    transcribing.add_argument("--language", required=True)
    transcribing.add_argument("--model", type=Path, required=True)
    transcribing.add_argument("--vad-model", type=Path)
    transcribing.add_argument("--chunk-seconds", type=float, default=300)
    transcribing.add_argument("--overlap-seconds", type=float, default=2)

    drafting = commands.add_parser("translate", help="draft English from a corrected source")
    drafting.add_argument("source", type=Path)
    drafting.add_argument("output", type=Path)
    drafting.add_argument("--source-language", required=True)
    drafting.add_argument("--batch-size", type=int, default=15)
    drafting.add_argument("--run", action="store_true", help="make authorized billable calls")

    second_opinion = commands.add_parser(
        "translation-second-opinion", help="compare a draft with Google NMT"
    )
    second_opinion.add_argument("source", type=Path)
    second_opinion.add_argument("english_draft", type=Path)
    second_opinion.add_argument("output", type=Path)
    second_opinion.add_argument("--source-language", required=True)
    second_opinion.add_argument("--google-project")
    second_opinion.add_argument("--run", action="store_true",
                                help="make authorized billable calls")
    second_opinion.add_argument("--max-source-characters", type=int)

    recording = commands.add_parser("record", help="apply one hash-bound source decision")
    recording.add_argument("case", type=Path)
    recording.add_argument("decision", type=Path)

    pairing = commands.add_parser("insert-pair", help="fill confirmed speech in both tracks")
    pairing.add_argument("case", type=Path)
    pairing.add_argument("target", type=Path)
    pairing.add_argument("decision", type=Path)

    replacing = commands.add_parser("replace-pair", help="replace existing cues in both tracks")
    replacing.add_argument("case", type=Path)
    replacing.add_argument("target", type=Path)
    replacing.add_argument("decision", type=Path)

    bundling = commands.add_parser("bundle", help="gather interval clips and subtitle evidence")
    bundling.add_argument("case", type=Path)
    bundling.add_argument("target", type=Path)
    bundling.add_argument("start_ms", type=int)
    bundling.add_argument("end_ms", type=int)
    bundling.add_argument("--context", type=float, default=2)
    bundling.add_argument("--audio-report", type=Path)
    bundling.add_argument("--asr-manifest", type=Path, action="append", default=[])
    bundling.add_argument("--output", type=Path)

    reviewing = commands.add_parser("review", help="extract audio for the next pending issue")
    reviewing.add_argument("case", type=Path)
    reviewing.add_argument("--issue-id")
    reviewing.add_argument("--context", type=float, default=6)

    translating = commands.add_parser("translation-audit", help="compare two subtitle timelines")
    translating.add_argument("source", type=Path)
    translating.add_argument("target", type=Path)
    translating.add_argument("--output", type=Path, required=True)

    checking_audio = commands.add_parser(
        "audio-check", help="compare local independent ASR with the source SRT"
    )
    checking_audio.add_argument("case", type=Path)
    checking_audio.add_argument("--output", type=Path, required=True)
    checking_audio.add_argument("--cache", type=Path, required=True)
    checking_audio.add_argument("--model", default="mlx-community/Qwen3-ASR-1.7B-4bit")
    checking_audio.add_argument("--language", default="Turkish")
    checking_audio.add_argument("--window-seconds", type=float, default=30)
    checking_audio.add_argument("--start-seconds", type=float, default=0)
    checking_audio.add_argument("--end-seconds", type=float)
    checking_audio.add_argument("--max-tokens", type=int, default=256)

    checking_episode = commands.add_parser(
        "episode-check", help="refresh source, audio, translation, and install checks"
    )
    checking_episode.add_argument("case", type=Path)
    checking_episode.add_argument("target", type=Path)
    checking_episode.add_argument("--source-language", required=True)
    checking_episode.add_argument("--target-language", required=True)
    checking_episode.add_argument("--output", type=Path, required=True)
    checking_episode.add_argument("--model", default="mlx-community/Qwen3-ASR-1.7B-4bit")
    checking_episode.add_argument("--audio-language", default="Turkish")

    releasing = commands.add_parser("release", help="validate and optionally install one pair")
    releasing.add_argument("video", type=Path)
    releasing.add_argument("source", type=Path)
    releasing.add_argument("target", type=Path)
    releasing.add_argument("--source-language", required=True)
    releasing.add_argument("--target-language", required=True)
    releasing.add_argument("--case", type=Path, required=True)
    releasing.add_argument("--translation-report", type=Path, required=True)
    releasing.add_argument("--audio-report", type=Path, required=True)
    releasing.add_argument("--audio-decisions", type=Path, required=True)
    releasing.add_argument("--output", type=Path, required=True)
    releasing.add_argument("--apply", action="store_true")
    releasing.add_argument("--backup-dir", type=Path)

    args = parser.parse_args()
    {"audit": audit, "transcribe": transcribe, "translate": translate_draft,
     "translation-second-opinion": translation_second_opinion,
     "record": record, "insert-pair": insert_pair, "replace-pair": replace_pair,
     "review": review, "bundle": bundle, "audio-check": audio_check,
     "episode-check": episode_check, "translation-audit": translation_audit,
     "release": release}[args.action](args)


if __name__ == "__main__":
    main()
