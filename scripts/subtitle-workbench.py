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
SEMANTIC = runpy.run_path(str(SCRIPTS / "semantic-review.py"))
LAYOUT_AUDIT = runpy.run_path(str(SCRIPTS / "layout-audit.py"))
PLAYBACK = runpy.run_path(str(SCRIPTS / "playback-check.py"))
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


def source_snapshots(case_directory, needed_hashes):
    """Find saved source versions for interval-safe reuse of old decisions."""
    found = {}
    candidates = list((case_directory / "decisions").rglob("*.srt"))
    candidates += list(case_directory.glob("original*.srt"))
    for path in candidates:
        value = file_hash(path)
        if value in needed_hashes and value not in found:
            found[value] = read_cues(path)
            if len(found) == len(needed_hashes):
                break
    return found


def decision_matches_interval(decision, issue, current_cues, snapshots):
    """Keep a decision current when the reviewed local subtitle span is unchanged."""
    local_hash = SOURCE_REVIEW["source_interval_sha256"](
        current_cues, issue["start_ms"], issue["end_ms"]
    )
    if decision.get("source_interval_sha256"):
        return decision["source_interval_sha256"] == local_hash

    recorded_hash = decision.get("working_after_sha256") or decision.get(
        "working_before_sha256"
    )
    prior = snapshots.get(recorded_hash)
    return bool(prior) and SOURCE_REVIEW["source_interval_sha256"](
        prior, issue["start_ms"], issue["end_ms"]
    ) == local_hash


def current_queue(case_directory):
    """Return issues still needing review against the current working SRT."""
    queue = SOURCE_REVIEW["build_queue"](case_directory)
    case, working = SOURCE_REVIEW["load_case"](case_directory)
    current_hash = file_hash(working)
    working_cues = read_cues(working)
    decisions = {}
    reviewed_intervals = {}
    for path in sorted((case_directory / "decisions").glob("*/decision.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        decisions[record["issue_id"]] = record
        interval = record.get("issue_interval")
        if interval:
            key = (interval["kind"], interval["start_ms"], interval["end_ms"])
            reviewed_intervals[key] = record

    snapshot_hashes = {record.get("working_after_sha256") or record.get(
        "working_before_sha256") for record in decisions.values()
        if not record.get("source_interval_sha256")}
    snapshots = source_snapshots(case_directory, snapshot_hashes - {None})

    pending = []
    for issue in queue["issues"]:
        decision = decisions.get(issue["id"])
        recorded_interval = decision.get("issue_interval") if decision else None
        same_interval = not recorded_interval or all(
            issue[key] == recorded_interval[key]
            for key in ("kind", "start_ms", "end_ms")
        )
        matching_content = bool(decision) and (
            (decision.get("working_after_sha256") or decision.get("working_before_sha256"))
            == current_hash or decision_matches_interval(
                decision, issue, working_cues, snapshots
            )
        )
        reviewed_current_version = decision and (
            same_interval and decision["status"] in ("reviewed", "resolved")
            and matching_content
        )
        if issue.get("evidence"):
            # New contradictory evidence reopens an unchanged, previously approved line.
            reviewed_current_version = reviewed_current_version and (
                decision.get("issue_sha256") == SEMANTIC["fingerprint"](issue))
        interval_key = (issue["kind"], issue["start_ms"], issue["end_ms"])
        interval_record = reviewed_intervals.get(interval_key)
        reviewed_current_version = reviewed_current_version or (
            issue["kind"] in ("subtitle_gap", "possible_speech_gap")
            and not issue.get("evidence")
            and interval_record is not None and interval_record["status"] == "reviewed"
        )
        record = decision or interval_record
        if reviewed_current_version and record and record["status"] == "reviewed":
            evidence_errors = SOURCE_REVIEW["evidence_blockers"](
                case_directory, record.get("evidence", []),
                issue["start_ms"], issue["end_ms"],
                case["video_sha256"],
            )
            evidence_errors.extend(SOURCE_REVIEW["review_result_blockers"](
                case_directory, record.get("review_result"),
                issue["start_ms"], issue["end_ms"],
                case["video_sha256"],
                current_hash,
                SOURCE_REVIEW["source_interval_sha256"](
                    working_cues, issue["start_ms"], issue["end_ms"]
                ),
            ))
            if evidence_errors:
                reviewed_current_version = False
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


def source_decision_blockers(case_directory, queue, pending, source, video_sha256):
    """Check evidence for source questions that a decision claims to close."""
    open_ids = {item["id"] for item in pending}
    records = [json.loads(path.read_text(encoding="utf-8"))
               for path in sorted((case_directory / "decisions").glob("*/decision.json"))]
    source_cues = read_cues(source)
    source_hash = file_hash(source)
    snapshot_hashes = {value for record in records
                       for value in (record.get("working_before_sha256"),
                                     record.get("working_after_sha256")) if value}
    snapshots = source_snapshots(case_directory, snapshot_hashes - {None})
    for issue in queue["issues"]:
        if issue["id"] in open_ids:
            continue
        decision = next((record for record in reversed(records)
                         if record.get("issue_id") == issue["id"]
                         or record.get("issue_interval") == {
                             key: issue[key] for key in ("kind", "start_ms", "end_ms")
                         }), None)
        if decision is None:
            return [f"Source issue {issue['id']} lacks a review decision"]
        if not decision_matches_interval(decision, issue, source_cues, snapshots):
            return [f"Source issue {issue['id']} has stale local evidence"]
        blockers = SOURCE_REVIEW["evidence_blockers"](
            case_directory, decision.get("evidence", []), issue["start_ms"],
            issue["end_ms"], video_sha256,
        )
        reviewed_cues = snapshots.get(decision.get("working_before_sha256"), source_cues)
        blockers.extend(SOURCE_REVIEW["review_result_blockers"](
            case_directory, decision.get("review_result"), issue["start_ms"],
            issue["end_ms"], video_sha256,
            decision.get("working_before_sha256") or source_hash,
            SOURCE_REVIEW["source_interval_sha256"](
                reviewed_cues, issue["start_ms"], issue["end_ms"]
            ),
        ))
        if blockers:
            return [f"Source issue {issue['id']}: {'; '.join(blockers)}"]

    return []


def audio_entry_blockers(entry, issue, source_cues, source_sha256, video_sha256,
                         decisions_directory, interval_bound):
    """Validate one audio decision without consulting other questions."""
    if not isinstance(entry, dict):
        return ["Audio decision is malformed"]
    start, end = entry.get("start_ms"), entry.get("end_ms")
    if issue is None:
        return [f"Audio decision {start}-{end} names an obsolete question"]
    if interval_bound:
        interval_hash = SOURCE_REVIEW["source_interval_sha256"](
            source_cues, start, end
        )
        if (entry.get("issue_sha256") != SEMANTIC["fingerprint"](issue)
                or entry.get("source_interval_sha256") != interval_hash):
            return [f"Audio decision {start}-{end} is stale"]
    outcome = entry.get("audible_outcome")
    if (outcome is not None and outcome not in
            ("relevant_speech", "unintelligible_speech",
             "music_without_relevant_words", "nonverbal_sound", "silence")):
        return [f"Audio decision {start}-{end} has an invalid audible outcome"]
    if (entry.get("disposition") not in
            ("source_supported", "model_artifact", "repaired", "no_relevant_speech")
            or not isinstance(entry.get("reason"), str) or not entry["reason"].strip()
            or not isinstance(entry.get("reviewer"), str) or not entry["reviewer"].strip()
            or not isinstance(entry.get("evidence"), list) or not entry["evidence"]
            or any(not isinstance(path, str) or not (decisions_directory / path).is_file()
                   for path in entry["evidence"])):
        return [f"Audio decision {start}-{end} is incomplete or has invalid evidence"]
    if entry["disposition"] == "no_relevant_speech":
        if outcome not in ("music_without_relevant_words", "nonverbal_sound", "silence"):
            return [f"Audio decision {start}-{end} needs a specific non-speech outcome"]
        if any(cue["start"] < end and cue["end"] > start
               and not SOURCE_REVIEW["is_non_speech_label"](cue["text"])
               for cue in source_cues):
            return [f"Audio decision {start}-{end} still overlaps a spoken-text cue"]
        try:
            result = json.loads((decisions_directory / entry["review_result"]).read_text(
                encoding="utf-8"))
        except (OSError, TypeError, ValueError):
            return [f"Audio decision {start}-{end} needs audio-capable review"]
        if not isinstance(result, dict):
            return [f"Audio decision {start}-{end} needs audio-capable review"]
        if result.get("route") == "local_asr_agent":
            return [f"Audio decision {start}-{end} cannot infer no speech from local ASR"]
    interval_hash = SOURCE_REVIEW["source_interval_sha256"](
        source_cues, start, end
    )
    blockers = SOURCE_REVIEW["evidence_blockers"](
        decisions_directory, entry["evidence"], start, end, video_sha256,
    )
    blockers.extend(SOURCE_REVIEW["review_result_blockers"](
        decisions_directory, entry.get("review_result"), start, end,
        video_sha256, source_sha256, interval_hash,
    ))
    return [f"Audio decision {start}-{end}: {'; '.join(blockers)}"] if blockers else []


def audio_decision_blockers(audio_path, decisions_path, source, video):
    """Require a current valid decision for each independent ASR question."""
    audio = json.loads(audio_path.read_text(encoding="utf-8"))
    source_sha256, video_sha256 = file_hash(source), file_hash(video)
    if (audio.get("source_sha256") != source_sha256
            or audio.get("video_sha256") != video_sha256):
        return ["Audio comparison is stale"]
    if not decisions_path.is_file():
        return ["Audio decisions are missing"] if audio["issues"] else []

    decisions = json.loads(decisions_path.read_text(encoding="utf-8"))
    interval_bound = decisions.get("version") == 2
    if interval_bound:
        if decisions.get("video_sha256") != video_sha256:
            return ["Audio decisions belong to another video"]
    elif (decisions.get("audio_report_sha256") != file_hash(audio_path)
            or decisions.get("source_sha256") != source_sha256):
        return ["Audio decisions do not match the current comparison"]
    entries = decisions.get("decisions")
    if not isinstance(entries, list):
        return ["Audio decisions must be a list"]
    expected = {(item["start_ms"], item["end_ms"]): item
                for item in audio["issues"]}
    current_cues = read_cues(source)
    recorded = set()
    blockers = []
    for entry in entries:
        if not isinstance(entry, dict):
            blockers.append("Audio decision is malformed")
            continue
        key = (entry.get("start_ms"), entry.get("end_ms"))
        if key in recorded:
            blockers.append(f"Audio decision {key[0]}-{key[1]} is duplicated")
            continue
        if key in expected:
            recorded.add(key)
        blockers.extend(audio_entry_blockers(
            entry, expected.get(key), current_cues, source_sha256,
            video_sha256, decisions_path.parent, interval_bound,
        ))

    missing = set(expected) - recorded
    if missing:
        blockers.append(f"{len(missing)} audio questions need decisions")
    return blockers


def audio_scan_blockers(audio, duration_ms):
    """Reject skipped audio, unknown processing states, and hidden questions."""
    if audio.get("start_ms") != 0 or audio.get("end_ms") != duration_ms:
        return ["Audio scan does not cover the complete video"]

    windows = audio.get("windows")
    if not isinstance(windows, list) or not windows:
        return ["Audio scan has no windows"]

    cursor = 0
    expected_issues = []
    for window in windows:
        if (not isinstance(window, dict) or window.get("start_ms") != cursor
                or type(window.get("end_ms")) is not int
                or not cursor < window["end_ms"] <= duration_ms):
            return ["Audio scan has a missing or malformed interval"]
        status = window.get("status")
        if status not in ("complete", "questionable", "empty",
                          "failed", "truncated", "unusable"):
            return ["Audio scan contains a missing or unknown window status"]
        if status in ("failed", "truncated", "unusable"):
            return ["Audio scan contains an unusable interval"]
        transcription = window.get("text")
        issue = window.get("issue")
        if (not isinstance(transcription, str)
                or (status == "empty") != (not transcription.strip())
                or (status == "empty" and issue != "empty_asr_output")
                or (status == "questionable" and not issue)):
            return ["Audio scan window recognition or status is inconsistent"]
        if issue:
            expected_issues.append(window)
        cursor = window["end_ms"]
    if cursor != duration_ms:
        return ["Audio scan ends before the video"]
    if audio.get("issues") != expected_issues:
        return ["Audio scan questions do not match its windows"]
    return []


def audio_adjudicate(args):
    """Save one current audio-question decision with interval-only bindings."""
    audio_path = args.audio_report.resolve(strict=True)
    audio = json.loads(audio_path.read_text(encoding="utf-8"))
    source = Path(audio["source"]).resolve(strict=True)
    video = Path(audio["video"]).resolve(strict=True)
    if (args.output.suffix.lower() != ".json"
            or args.output.resolve() in
            {audio_path, source, video, args.decision.resolve()}):
        raise ValueError("Use a separate JSON audio-decisions path")
    if (audio.get("source_sha256") != file_hash(source)
            or audio.get("video_sha256") != file_hash(video)):
        raise ValueError("Audio comparison is stale")
    decision = json.loads(args.decision.read_text(encoding="utf-8"))
    start, end = decision.get("start_ms"), decision.get("end_ms")
    issue = next((item for item in audio["issues"]
                  if (item["start_ms"], item["end_ms"]) == (start, end)), None)
    if issue is None:
        raise ValueError("Audio decision does not name a current question")
    entry = {**decision,
             "issue_sha256": SEMANTIC["fingerprint"](issue),
             "source_interval_sha256": SOURCE_REVIEW["source_interval_sha256"](
                 read_cues(source), start, end
             )}
    if args.output.exists():
        data = json.loads(args.output.read_text(encoding="utf-8"))
        if data.get("version") != 2 or data.get("video_sha256") != file_hash(video):
            raise ValueError("Existing audio decisions use another format or video")
    else:
        data = {"version": 2, "video_sha256": file_hash(video), "decisions": []}
    if not isinstance(data.get("decisions"), list):
        raise ValueError("Audio decisions must be a list")
    if not isinstance(data.get("history", []), list):
        raise ValueError("Audio decision history must be a list")
    blockers = audio_entry_blockers(
        entry, issue, read_cues(source), file_hash(source), file_hash(video),
        args.output.parent, True,
    )
    if blockers:
        raise ValueError("Audio decision is invalid: " + "; ".join(blockers))
    current_keys = {(item["start_ms"], item["end_ms"])
                    for item in audio["issues"]}
    entries = []
    history = list(data.get("history", []))
    for prior in data["decisions"]:
        prior_key = ((prior.get("start_ms"), prior.get("end_ms"))
                     if isinstance(prior, dict) else None)
        if prior_key == (start, end):
            reason = "superseded"
        elif prior_key not in current_keys:
            reason = "question_disappeared"
        else:
            entries.append(prior)
            continue
        history.append({"reason": reason,
                        "archived_at": datetime.now(timezone.utc).isoformat(),
                        "entry": prior})
    data["decisions"] = entries + [entry]
    data["history"] = history
    save_json(args.output, data)
    blockers = audio_decision_blockers(audio_path, args.output, source, video)
    print(json.dumps({"decisions": str(args.output), "remaining": blockers}))


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
        script = runpy.run_path(str(SCRIPTS / "translate-subtitles.py"))
        cues, _ = script["translation_targets"](
            args.source.resolve(strict=True), args.utterance_map)
        count_label = "source_units" if args.utterance_map else "source_cues"
        print(json.dumps({count_label: len(cues),
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

    def replace_from_snapshot(snapshot, destination):
        """Replace a file even when the previous candidate is read-only."""
        with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as staged_file:
            staged = Path(staged_file.name)
        try:
            shutil.copy2(snapshot, staged)
            os.replace(staged, destination)
        finally:
            staged.unlink(missing_ok=True)

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
        if (decision.get("question_type") == "translation_semantics"
                and file_hash(revision / "source-after.srt") !=
                file_hash(revision / "source-before.srt")):
            raise ValueError("Translation-only repair changed the Turkish candidate")
    except Exception:
        shutil.rmtree(revision)
        raise

    # 2. Apply the pair and record it; restore both originals on any failure.

    try:
        replace_from_snapshot(revision / "source-after.srt", source)
        replace_from_snapshot(revision / "target-after.srt", target)

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
            record["source_interval_sha256"] = SOURCE_REVIEW["source_interval_sha256"](
                read_cues(source), issue["start_ms"], issue["end_ms"]
            )
        save_json(revision / "decision.json", record)
    except BaseException as error:
        restore_errors = []
        for language, path in (("source", source), ("target", target)):
            try:
                replace_from_snapshot(revision / f"{language}-before.srt", path)
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
    if (type(decision.get("speech_start_ms")) is not int
            or type(decision.get("speech_end_ms")) is not int):
        raise ValueError("Pair decision needs a confirmed speech interval")

    blockers = SOURCE_REVIEW["evidence_blockers"](
        case_directory, evidence, decision.get("speech_start_ms"),
        decision.get("speech_end_ms"), case["video_sha256"],
    )
    blockers.extend(SOURCE_REVIEW["review_result_blockers"](
        case_directory, decision.get("review_result"), decision.get("speech_start_ms"),
        decision.get("speech_end_ms"), case["video_sha256"], file_hash(source),
        SOURCE_REVIEW["source_interval_sha256"](
            read_cues(source), decision.get("speech_start_ms"),
            decision.get("speech_end_ms"),
        ),
    ))
    if blockers:
        raise ValueError("; ".join(blockers))

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
    """Replace existing cue ranges while keeping both tracks recoverable."""

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
    layout_mode = getattr(args, "action", None) == "layout-repair"
    semantic_only = decision.get("question_type") == "translation_semantics"
    if semantic_only and layout_mode:
        raise ValueError("Translation-only repair cannot change layout")
    additions = decision.get("cues")
    if layout_mode:
        if additions is not None:
            raise ValueError("Layout repair uses separate source_cues and target_cues")
        additions_by_language = (decision.get("source_cues"),
                                 decision.get("target_cues"))
        if any(not isinstance(items, list) or not items
               for items in additions_by_language):
            raise ValueError("Layout repair needs both language-specific cue lists")
    else:
        if not isinstance(additions, list) or not additions:
            raise ValueError("Pair decision needs timed bilingual cues")
        additions_by_language = (
            [{"start_ms": cue.get("start_ms"), "end_ms": cue.get("end_ms"),
              "text": cue.get("source_text")} for cue in additions],
            [{"start_ms": cue.get("start_ms"), "end_ms": cue.get("end_ms"),
              "text": cue.get("target_text")} for cue in additions],
        )

    if semantic_only:
        if not SEMANTIC["evidence_is_current"](
                decision.get("text_evidence"), "translation_semantics"):
            raise ValueError("Translation repair needs current hashed text evidence")
    else:
        blockers = SOURCE_REVIEW["evidence_blockers"](
            case_directory, evidence, start, end, case["video_sha256"],
        )
        # Accepted alignment can support a text-preserving layout repair.
        # Source wording changes still require the two-stage audio review.
        if not layout_mode or decision.get("review_result") is not None:
            blockers.extend(SOURCE_REVIEW["review_result_blockers"](
                case_directory, decision.get("review_result"), start, end,
                case["video_sha256"], file_hash(source),
                SOURCE_REVIEW["source_interval_sha256"](read_cues(source), start, end),
            ))
        if blockers:
            raise ValueError("; ".join(blockers))

    issue = None
    if decision.get("issue_id"):
        queue, _ = current_queue(case_directory)
        issue = next((item for item in queue["issues"]
                      if item["id"] == decision["issue_id"]), None)
        if issue is None or issue["start_ms"] >= end or issue["end_ms"] <= start:
            raise ValueError("Named issue is not current in the edit interval")

    # 2. Validate paired replacements against the selected existing cue spans.

    for language, items in zip(("Turkish", "English"), additions_by_language):
        for cue in items:
            if (not isinstance(cue, dict)
                    or any(type(cue.get(key)) is not int
                           for key in ("start_ms", "end_ms"))
                    or not start <= cue["start_ms"] < cue["end_ms"] <= end
                    or not isinstance(cue.get("text"), str)
                    or not cue["text"].strip()):
                raise ValueError(f"{language} repair needs timed text inside the interval")
        if any(left["end_ms"] > right["start_ms"]
               for left, right in zip(items, items[1:])):
            raise ValueError(f"{language} repair cues must be ordered and nonoverlapping")

    updated = []
    selected_by_language = []
    for path, ids_key, replacement in (
        (source, "replace_source_ids", additions_by_language[0]),
        (target, "replace_target_ids", additions_by_language[1]),
    ):
        existing = read_cues(path)
        ids = decision.get(ids_key)
        if (not isinstance(ids, list) or not ids
                or any(type(cue_id) is not int for cue_id in ids)
                or ids != list(range(ids[0], ids[-1] + 1))
                or not 1 <= ids[0] <= ids[-1] <= len(existing)):
            raise ValueError(f"{ids_key} must name a contiguous existing cue range")
        selected = existing[ids[0] - 1:ids[-1]]
        selected_by_language.append(selected)
        if any(cue["start"] < start or cue["end"] > end for cue in selected):
            raise ValueError("Selected cues extend beyond the edit interval")
        updated.append(SOURCE_REVIEW["splice_cues"](
            existing, {"replace_ids": ids, "replacement": replacement},
            case["duration_ms"],
        ))

    if semantic_only:
        old_source, old_target = selected_by_language
        new_source, new_target = additions_by_language
        if ([(cue["start"], cue["end"], cue["text"]) for cue in old_source] !=
                [(cue["start_ms"], cue["end_ms"], cue["text"])
                 for cue in new_source]
                or [(cue["start"], cue["end"]) for cue in old_target] !=
                [(cue["start_ms"], cue["end_ms"]) for cue in new_target]
                or [cue["text"] for cue in old_target] ==
                [cue["text"] for cue in new_target]):
            raise ValueError("Translation-only repair must change English text only")

    if layout_mode:
        # Preserve all words while changing only supported display boundaries.
        for old, new in zip(selected_by_language, additions_by_language):
            if " ".join(cue["text"] for cue in old).split() != " ".join(
                    cue["text"] for cue in new).split():
                raise ValueError("Layout repair may not add or remove subtitle words")
        manifest_path = Path(decision.get("semantic_manifest", ""))
        report_path = Path(decision.get("layout_report", ""))
        report, manifest, results, stale = LAYOUT_AUDIT["current_report"](
            report_path, manifest_path, Path(case["video"])
        )
        expected_ids = {unit["id"] for unit in manifest["utterances"]
                        if set(unit["cue_ids"]) & set(decision["replace_source_ids"])}
        if (Path(manifest["source"]).resolve() != source
                or Path(manifest["target"]).resolve() != target
                or set(decision.get("alignment_source_ids", [])) != expected_ids
                or expected_ids & stale
                or not isinstance(decision.get("alignment_reason"), str)
                or not decision["alignment_reason"].strip()):
            raise ValueError("Layout repair needs current accepted alignment units")
        available = {(identifier, word.get("text"), word.get("start_ms"),
                      word.get("end_ms"))
                     for identifier in expected_ids
                     for word in results.get(identifier, {}).get("word_timings", [])
                     if type(word.get("start_ms")) is int
                     and type(word.get("end_ms")) is int}
        accepted = decision.get("accepted_words")
        if (not isinstance(accepted, list) or not accepted
                or any((word.get("source_id"), word.get("text"),
                        word.get("start_ms"), word.get("end_ms")) not in available
                       for word in accepted)):
            raise ValueError("Accepted word timing is absent from current alignment")
        for language, cues in zip(("Turkish", "English"), additions_by_language):
            if any(not any(word["start_ms"] < cue["end_ms"]
                               and word["end_ms"] > cue["start_ms"]
                               for word in accepted) for cue in cues):
                raise ValueError(f"{language} repair cue has no accepted word timing")

    # 3. Stage and apply both tracks with recoverable before/after copies.

    save_pair_revision(case_directory, case, source, target, updated, decision, issue)


def gap_review_windows(issue, duration_ms, context_seconds):
    """Cover any disputed interval with overlapping review clips."""
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


def bundle_visual_context(video, source, output, start_ms, end_ms, duration_ms,
                          selected_ids, notes_path=None):
    """Save bounded stills around named cues; observations stay agent-authored."""
    if not selected_ids:
        if notes_path:
            raise ValueError("Visual notes need selected source cue IDs")
        return None
    if len(selected_ids) != len(set(selected_ids)) or len(selected_ids) > 6:
        raise ValueError("Choose one to six distinct source cue IDs per visual bundle")
    cues = {cue["id"]: cue for cue in read_cues(source)}
    selected = []
    for cue_id in selected_ids:
        cue = cues.get(cue_id)
        if cue is None or cue["start"] >= end_ms or cue["end"] <= start_ms:
            raise ValueError("Visual cue IDs must overlap the requested interval")
        selected.append(cue)

    frames_dir = output.parent / f"{output.stem}-visual"
    frames_dir.mkdir(parents=True, exist_ok=True)

    def still(label, timestamp_ms):
        path = frames_dir / f"{label}-{timestamp_ms}.png"
        subprocess.run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-ss", f"{timestamp_ms / 1000:.3f}", "-i", str(video),
            "-frames:v", "1", "-an", str(path),
        ], check=True, capture_output=True)
        return {"timestamp_ms": timestamp_ms, "path": str(path.resolve()),
                "sha256": file_hash(path)}

    scene = still("overview", (start_ms + end_ms) // 2)
    cue_frames = []
    for cue in selected:
        samples = []
        positions = (
            ("before", cue["start"] - 250),
            ("during", (cue["start"] + cue["end"]) // 2),
            ("after", cue["end"] + 250),
        )
        for position, timestamp in positions:
            if 0 <= timestamp < duration_ms:
                samples.append({"position": position,
                                **still(f"cue-{cue['id']}-{position}", timestamp)})
        cue_frames.append({"cue_id": cue["id"], "start_ms": cue["start"],
                           "end_ms": cue["end"], "frames": samples})

    visual = {"status": "frames_only", "scene_start_ms": start_ms,
              "scene_end_ms": end_ms, "overview_frame": scene,
              "cues": cue_frames, "scene_overview": None,
              "observations": []}
    if notes_path:
        path = notes_path.resolve(strict=True)
        authored = json.loads(path.read_text(encoding="utf-8"))
        reviewer = authored.get("reviewer")
        overview = authored.get("scene_overview")
        observations = authored.get("observations")
        allowed = {"speaker", "referent", "object_action", "setting",
                   "on_screen_text", "no_visual_clue"}
        timestamps = {item["cue_id"]: {frame["timestamp_ms"]
                      for frame in item["frames"]} for item in cue_frames}
        if (not isinstance(reviewer, str) or not reviewer.strip()
                or not isinstance(overview, str) or not overview.strip()
                or not isinstance(observations, list) or not observations):
            raise ValueError("Visual notes need reviewer, scene overview, and observations")
        covered = set()
        for observation in observations:
            if (not isinstance(observation, dict)
                    or observation.get("cue_id") not in timestamps
                    or observation.get("timestamp_ms") not in
                    timestamps[observation["cue_id"]]
                    or observation.get("category") not in allowed
                    or not isinstance(observation.get("observation"), str)
                    or not observation["observation"].strip()):
                raise ValueError("Visual observations must identify a sampled cue frame")
            covered.add(observation["cue_id"])
        if covered != set(timestamps):
            raise ValueError("Visual notes need an observation for each selected cue")
        visual.update({"status": "observed", "reviewer": reviewer,
                       "scene_overview": overview, "observations": observations,
                       "authored_path": str(path), "authored_sha256": file_hash(path)})
    return visual


def bundle(args):
    """Collect one interval's playable clips and subtitle/ASR evidence."""

    # 1. Check inputs and extract bounded clips from the original video.

    case_directory = args.case.resolve(strict=True)
    case, source = SOURCE_REVIEW["load_case"](case_directory)
    target = None if str(args.target) == "-" else args.target.resolve(strict=True)
    if file_hash(Path(case["video"])) != case["video_sha256"]:
        raise ValueError("Video differs from the review case")
    if source == target or not 0 <= args.start_ms < args.end_ms <= case["duration_ms"]:
        raise ValueError("Choose separate tracks and a valid video-relative interval")
    output = args.output or case_directory / "bundles" / f"{args.start_ms}-{args.end_ms}.json"
    protected = {source, Path(case["video"]).resolve(),
                 case_directory / "case.json", case_directory / "review-queue.json"}
    if target is not None:
        protected.add(target)
    protected.update(path.resolve() for path in args.asr_manifest)
    if args.visual_notes:
        protected.add(args.visual_notes.resolve())
    if args.audio_report:
        protected.add(args.audio_report.resolve())
    if getattr(args, "layout_report", None):
        protected.add(args.layout_report.resolve())
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
    timeline.extend(SOURCE_REVIEW["saved_scene_evidence"](
        case_directory, case, timeline_start, timeline_end))
    tracks = [("turkish", source)]
    if target is not None:
        tracks.append(("english", target))
    for kind, path in tracks:
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
        for window in report["issues"]:
            if window["start_ms"] < timeline_end and window["end_ms"] > timeline_start:
                identifier = f"audio:{window['start_ms']}-{window['end_ms']}"
                issues[identifier] = {"id": identifier, "kind": window["issue"],
                                      "start_ms": window["start_ms"],
                                      "end_ms": window["end_ms"],
                                      "status": window["status"]}
    if getattr(args, "layout_report", None):
        layout_path = args.layout_report.resolve(strict=True)
        layout = json.loads(layout_path.read_text(encoding="utf-8"))
        manifest_path = Path(layout["utterance_map"])
        _, mapping, _, _ = LAYOUT_AUDIT["current_report"](
            layout_path, manifest_path, Path(case["video"])
        )
        if (Path(mapping["source"]).resolve() != source
                or Path(mapping["target"]).resolve() != target):
            raise ValueError("Layout report belongs to another subtitle pair")
        for flag in layout["flags"]:
            if not LAYOUT_AUDIT["needs_resolution"](flag):
                continue
            items = (mapping["utterances"] if flag["language"] == "source"
                     else mapping["translations"])
            item = next(value for value in items if value["id"] == flag["id"])
            if item["start_ms"] < timeline_end and item["end_ms"] > timeline_start:
                identifier = "layout:" + LAYOUT_AUDIT["decision_key"](flag)
                issues[identifier] = {"id": identifier, "kind": flag["kind"],
                                      "language": flag["language"],
                                      "start_ms": item["start_ms"],
                                      "end_ms": item["end_ms"], "finding": flag}
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
    visual = bundle_visual_context(
        Path(case["video"]), source, output, args.start_ms, args.end_ms,
        case["duration_ms"], args.visual_cue_id, args.visual_notes,
    )
    report = {
        "case": str(case_directory), "start_ms": args.start_ms, "end_ms": args.end_ms,
        "video_sha256": case["video_sha256"], "source_sha256": file_hash(source),
        "target_sha256": file_hash(target) if target is not None else None,
        "reference_alignment": case["reference_alignment"],
        "clips": clips, "issues": sorted(issues.values(), key=lambda item: item["start_ms"]),
        "recorded_decisions": list(decisions.values()),
        "asr_inputs": asr_inputs, "timeline": timeline,
        "visual_context": visual,
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

    case, _ = SOURCE_REVIEW["load_case"](case_directory)
    review_windows = gap_review_windows(chosen, case["duration_ms"], args.context)
    for start, end in review_windows:
        center = (start + end) / 2000
        half_duration = (end - start) / 2000
        SOURCE_REVIEW["inspect"](case_directory, center, half_duration, half_duration)
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
    max_cps = getattr(args, "max_cps", 25)
    if max_cps <= 0:
        raise ValueError("Reading-speed threshold must be positive")
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
    presentation_flags = []
    for language, cues in (("source", source_cues), ("target", target_cues)):
        for cue in cues:
            characters_per_second = len(cue["text"].replace("\n", "")) * 1000 / (
                cue["end"] - cue["start"]
            )
            if characters_per_second > max_cps:
                presentation_flags.append({"kind": "fast_cue", "language": language,
                                           "cue_id": cue["id"],
                                           "characters_per_second": round(
                                               characters_per_second, 2
                                           )})
    # ponytail: pairwise scans suit a few thousand cues; index times for much larger files.
    for label, cues, counterparts in (
        ("source_without_target", source_cues, target_cues),
        ("target_without_source", target_cues, source_cues),
    ):
        for cue in cues:
            if not any(meaningful_overlap(cue, other) for other in counterparts):
                flags.append({"id": f"{label}:{cue['id']}", "kind": label,
                              "start_ms": cue["start"], "end_ms": cue["end"],
                              "cue": cue_record(cue)})

    for cue in target_cues:
        related = [other for other in source_cues if meaningful_overlap(cue, other)]
        if len(related) >= 3:
            flags.append({
                "id": f"many_source_cues_one_target:{cue['id']}",
                "kind": "many_source_cues_one_target",
                "start_ms": cue["start"], "end_ms": cue["end"],
                "source_ids": [other["id"] for other in related],
                "target_id": cue["id"],
            })
        if cue["end"] - cue["start"] > 8_000:
            presentation_flags.append({
                "kind": "long_target_cue", "language": "target",
                "cue_id": cue["id"], "duration_ms": cue["end"] - cue["start"],
            })

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
        "presentation_flags": presentation_flags, "max_cps": max_cps,
        "windows": windows,
        "note": "Mechanical flags do not establish translation meaning. Review every window against the source.",
    }
    save_json(args.output, report)
    print(json.dumps({"report": str(args.output), "windows": len(windows),
                      "flags": len(flags), "source_cues": len(source_cues),
                      "target_cues": len(target_cues),
                      "presentation_flags": len(presentation_flags)}))


def meaningful_overlap(left, right):
    overlap = min(left["end"], right["end"]) - max(left["start"], right["start"])
    shorter = min(left["end"] - left["start"], right["end"] - right["start"])
    return overlap >= min(shorter, max(100, min(500, shorter // 4)))


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
    """Raise focused questions in both directions without treating ASR as truth."""
    heard = words(transcript)
    written = words(cue_text)
    counts = Counter(heard)
    looped = (any(len(word) > 40 for word in heard)
              or repeated_phrase(heard)
              or (len(heard) >= 8 and max(counts.values()) / len(heard) > 0.45))
    shared = sum((counts & Counter(written)).values())
    agreement = round(shared / len(heard), 3) if heard else None
    unmatched = []
    unsupported = []
    meaning_changers = {"evet", "hayır", "değil", "yok", "var", "asla", "hiç", "no", "not", "never", "yes"}
    for tag, left, right, _, _ in SequenceMatcher(
        None, heard, written, autojunk=False
    ).get_opcodes():
        if tag in ("delete", "replace"):
            unmatched.append(heard[left:right])

    for tag, _, _, left, right in SequenceMatcher(
        None, heard, written, autojunk=False
    ).get_opcodes():
        if tag in ("insert", "replace"):
            unsupported.append(written[left:right])

    longest_unmatched = max(unmatched, key=len, default=[])
    longest_unsupported = max(unsupported, key=len, default=[])
    material_word = bool(meaning_changers.intersection(
        set(longest_unmatched + longest_unsupported)
    ))
    focused = max(len(heard), len(written)) <= 20
    if looped:
        issue = "repeated_asr_output"
    elif heard and focused and (len(longest_unmatched) >= 3 or material_word
                               or (len(heard) >= 6 and agreement < 0.25)):
        issue = "possible_missing_or_wrong_subtitle"
    elif heard and not focused and len(longest_unmatched) >= 6 and agreement < 0.65:
        issue = "possible_missing_or_wrong_subtitle"
    elif heard and focused and len(longest_unsupported) >= 3:
        issue = "possible_unsupported_subtitle"
    elif heard and not focused and len(longest_unsupported) >= 8 and agreement < 0.6:
        issue = "possible_unsupported_subtitle"
    else:
        issue = None

    return {"heard_words": len(heard), "written_words": len(written),
            "word_agreement": agreement,
            "longest_unmatched_words": len(longest_unmatched),
            "unmatched_example": " ".join(longest_unmatched[:20]),
            "longest_unsupported_words": len(longest_unsupported),
            "unsupported_example": " ".join(longest_unsupported[:20]),
            "issue": issue}


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
    # Qwen shares its token budget across chunks; a looping chunk can skip the tail.
    if window_ms < 10_000 or window_ms > 30_000:
        raise ValueError("Window duration must be between 10 and 30 seconds")
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
                "model_revision": args.model_revision,
                "language": args.language, "window_ms": window_ms,
                "max_tokens": args.max_tokens}
    if args.cache.exists():
        cache = json.loads(args.cache.read_text(encoding="utf-8"))
        legacy_revision = "model_revision" not in cache
        checked_keys = (key for key in identity if key != "model_revision" or not legacy_revision)
        if any(cache.get(key) != identity[key] for key in checked_keys):
            raise ValueError("Audio transcript cache belongs to different inputs or settings")
    else:
        legacy_revision = False
        cache = {**identity, "windows": {}}

    # 2. Transcribe only uncached windows of original audio, with one model load.

    starts = range(start_ms, end_ms, window_ms)
    missing = [
        start for start in starts
        if (str(start) not in cache["windows"]
            or cache["windows"][str(start)]["end_ms"] != min(start + window_ms, end_ms))
    ]
    if missing and legacy_revision:
        raise ValueError("Legacy audio cache has no recorded model revision; start a new pinned cache")
    if missing:
        try:
            from mlx_audio.stt.utils import load_model
        except ImportError as error:
            raise RuntimeError(
                "Run audio-check with a Python environment containing mlx-audio"
            ) from error

        model = load_model(args.model, revision=args.model_revision)
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
                finish_reason = getattr(result, "finish_reason", None)
                generation_tokens = getattr(result, "generation_tokens", None)
                cache["windows"][str(start)] = {
                    "start_ms": start, "end_ms": end, "text": result.text.strip(),
                    "finish_reason": (finish_reason if isinstance(finish_reason, str)
                                      else None),
                    "generation_tokens": (generation_tokens if type(generation_tokens) is int
                                          else None),
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
        comparison = compare_audio_window(transcript["text"], source_text)
        finish_reason = transcript.get("finish_reason")
        generation_tokens = transcript.get("generation_tokens")
        if (finish_reason in ("length", "max_tokens")
                or (type(generation_tokens) is int and generation_tokens >= args.max_tokens)):
            status = "truncated"
        elif not transcript["text"]:
            status = "empty"
        elif len(words(transcript["text"])) >= args.max_tokens - 8:
            status = "truncated"
        elif comparison["issue"] == "repeated_asr_output":
            status = "questionable"
        else:
            status = "complete"
        if status in ("empty", "truncated"):
            comparison["issue"] = f"{status}_asr_output"
        windows.append({**transcript, **comparison, "status": status})

    report = {"video": str(video), "video_sha256": case["video_sha256"],
              "source": str(working), "source_sha256": file_hash(working),
              "model": args.model,
              "model_revision": ("unrecorded_legacy" if legacy_revision
                                 else args.model_revision),
              "language": args.language,
              "start_ms": start_ms, "end_ms": end_ms, "window_ms": window_ms,
              "transcript_cache": str(args.cache),
              "windows": windows,
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
        model_revision=args.model_revision,
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
        semantic_manifest=args.semantic_manifest, semantic_reviews=args.semantic_reviews,
        semantic_model=args.semantic_model, semantic_batch_size=args.semantic_batch_size,
        glossary=args.glossary, layout_report=args.layout_report,
        timing_decisions=args.timing_decisions, render_report=args.render_report,
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
                    "layout": str(args.layout_report) if args.layout_report else None,
                    "render": str(args.render_report) if args.render_report else None,
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


def repair_boundary_samples(case_directory, duration_ms):
    """Require rendered frames near the boundaries of paired repairs."""
    times = set()
    for path in (case_directory / "decisions").glob("*/decision.json"):
        decision = json.loads(path.read_text(encoding="utf-8"))
        start, end = decision.get("start_ms"), decision.get("end_ms")
        if (decision.get("status") != "resolved"
                or type(start) is not int or type(end) is not int
                or not 0 <= start < end <= duration_ms):
            continue
        offset = min(100, (end - start) // 4)
        times.update((start + offset, end - offset))
    return sorted(times)


def rendering_blockers(report_path, video, source, target, case_directory,
                       source_cues, target_cues, duration_ms):
    """Accept only verified, current candidate frames at required samples."""
    if not report_path or not report_path.is_file():
        return ["Candidate rendering check is missing"]
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
        if (report.get("video_sha256") != file_hash(video)
                or report.get("source_sha256") != file_hash(source)
                or report.get("target_sha256") != file_hash(target)
                or not report.get("render_checks_passed")):
            return ["Candidate rendering check is stale or failed"]
        required = PLAYBACK["sample_times"](source_cues,
            repair_boundary_samples(case_directory, duration_ms))
        samples = report.get("samples")
        if not isinstance(samples, list):
            return ["Candidate rendering samples are missing"]
        by_label = {(item["label"], item["language"]): item for item in samples}
        for label, at_ms in required.items():
            for language, cues in (("tr", source_cues), ("en", target_cues)):
                sample = by_label.get((label, language))
                if not sample or sample.get("at_ms") != at_ms:
                    return [f"Candidate rendering is missing {label} {language}"]
                cue = PLAYBACK["active_cue"](cues, at_ms)
                if (sample.get("cue_id") != (cue["id"] if cue else None)
                        or sample.get("cue_text") != (cue["text"] if cue else None)
                        or sample.get("expected_visible") != (cue is not None)
                        or sample.get("visible_pixels_changed") != (cue is not None)):
                    return [f"Candidate rendering disagrees at {label} {language}"]
                for path_key, hash_key in (("rendered_frame", "rendered_frame_sha256"),
                                           ("baseline_frame", "baseline_frame_sha256")):
                    frame = Path(sample.get(path_key, ""))
                    if not frame.is_file() or file_hash(frame) != sample.get(hash_key):
                        return [f"Candidate rendering frame is missing or changed: {label}"]
    except (OSError, ValueError, KeyError, TypeError) as error:
        return [f"Candidate rendering check is invalid: {error}"]
    return []


def translation_decision_blockers(report, manifest, decisions_path):
    """Accept reviewed display grouping; preserve all other timing findings."""
    flags = report["flags"]
    if not flags:
        return []
    if not decisions_path or not decisions_path.is_file() or not manifest:
        return [f"{len(flags)} English timing questions need repair"]
    # 1. Bind authored judgments to the current pair and meaning map.
    try:
        decisions = json.loads(decisions_path.read_text(encoding="utf-8"))
        valid = (decisions["source_sha256"] == report["source_sha256"]
                 and decisions["target_sha256"] == report["target_sha256"]
                 and decisions["semantic_manifest_sha256"] == file_hash(manifest)
                 and isinstance(decisions["reviewer"], str)
                 and bool(decisions["reviewer"].strip()))
        reviews = {entry["id"]: entry for entry in decisions["findings"]}
        valid = valid and len(reviews) == len(decisions["findings"])
    except (OSError, ValueError, KeyError, TypeError):
        return ["English grouping decisions are malformed"]
    if not valid:
        return ["English grouping decisions are stale or incomplete"]
    # 2. Accept only specifically reviewed grouping; other findings stay open.
    pending = []
    for flag in flags:
        entry = reviews.get(flag["id"], {})
        if (flag["kind"] != "many_source_cues_one_target"
                or entry.get("finding_sha256") != SEMANTIC["fingerprint"](flag)
                or entry.get("disposition") != "independent_display_grouping"
                or not isinstance(entry.get("reason"), str)
                or not entry["reason"].strip()):
            pending.append(flag["id"])
    return [f"English timing questions need decisions: {', '.join(pending)}"] if pending else []


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
    semantic_manifest = getattr(args, "semantic_manifest", None)
    semantic_reviews = getattr(args, "semantic_reviews", None)
    layout_report = getattr(args, "layout_report", None)
    timing_decisions = getattr(args, "timing_decisions", None)
    render_report = getattr(args, "render_report", None)
    translation_decisions = getattr(args, "translation_decisions", None)
    destinations = [video.with_suffix(f".{args.source_language}.srt"),
                    video.with_suffix(f".{args.target_language}.srt")]
    protected_paths = {video, source, target}
    protected_paths.update(destinations)
    protected_paths.update(review_paths)
    protected_paths.update(case_directory / name for name in (
        "case.json", "review-queue.json", "speech-coverage.json", "speech-coverage.sha256"
    ))
    if semantic_manifest:
        protected_paths.add(semantic_manifest.resolve())
    for path in (layout_report, timing_decisions, render_report, translation_decisions):
        if path:
            protected_paths.add(path.resolve())
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
    if not semantic_manifest or not semantic_reviews:
        blockers.append("English semantic review is missing")
    else:
        semantic_manifest = semantic_manifest.resolve()
        if semantic_manifest.is_file():
            mapping = json.loads(semantic_manifest.read_text(encoding="utf-8"))
            if (Path(mapping.get("source", "")).resolve() != source
                    or Path(mapping.get("target", "")).resolve() != target):
                blockers.append("English semantic review belongs to another subtitle pair")
            else:
                blockers.extend(SEMANTIC["blockers"](
                    semantic_manifest, semantic_reviews,
                    getattr(args, "semantic_model", "agent"),
                    getattr(args, "semantic_batch_size", 12),
                    getattr(args, "glossary", None),
                ))
        else:
            blockers.append("Utterance map is missing")
    blockers.extend(audio_decision_blockers(audio_path, decisions_path, source, video))

    duration_ms = round(COVERAGE["duration_seconds"](video) * 1000)
    blockers.extend(audio_scan_blockers(
        json.loads(audio_path.read_text(encoding="utf-8")), duration_ms
    ))
    source_cues, source_errors = validate_cues(source, duration_ms)
    target_cues, target_errors = validate_cues(target, duration_ms)
    blockers.extend(source_errors + target_errors)
    if semantic_manifest and semantic_manifest.is_file():
        blockers.extend(LAYOUT_AUDIT["layout_blockers"](
            layout_report, semantic_manifest, video, timing_decisions
        ))
    else:
        blockers.append("Current layout report is missing")
    blockers.extend(rendering_blockers(
        render_report, video, source, target, case_directory,
        source_cues, target_cues, duration_ms
    ))
    queue, pending = current_queue(case_directory)
    blockers.extend(source_decision_blockers(
        case_directory, queue, pending, source, case["video_sha256"]
    ))
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
    grouping_blockers = translation_decision_blockers(
        translation, semantic_manifest, translation_decisions
    )
    blockers.extend(grouping_blockers)
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
        "translation_decision_blockers": grouping_blockers,
        "urgent_source_issue_ids": [item["id"] for item in urgent],
        "open_coverage_issue_ids": open_coverage,
        "unresolved_source_issue_ids": unresolved,
        "blockers": blockers,
        "installation_checks_passed": installation_checks_passed,
        "installed": False, "native_playback_verified": False,
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
    transcribing.add_argument("--language")
    transcribing.add_argument("--model", type=Path)
    transcribing.add_argument("--vad-model", type=Path)
    transcribing.add_argument("--chunk-seconds", type=float, default=300)
    transcribing.add_argument("--overlap-seconds", type=float, default=5)
    transcribing.add_argument("--profile", choices=("whisper-turbo", "gemini-five-minute"))
    transcribing.add_argument("--authorization", type=Path)
    transcribing.add_argument("--apply", action="store_true")

    drafting = commands.add_parser("translate", help="draft English from a corrected source")
    drafting.add_argument("source", type=Path)
    drafting.add_argument("output", type=Path)
    drafting.add_argument("--source-language", required=True)
    drafting.add_argument("--batch-size", type=int, default=80)
    drafting.add_argument("--concurrency", type=int, default=4)
    drafting.add_argument("--input-token-budget", type=int, default=6000)
    drafting.add_argument("--max-output-tokens", type=int, default=8192)
    drafting.add_argument("--input-usd-per-million", type=float, default=0.30)
    drafting.add_argument("--output-usd-per-million", type=float, default=1.20)
    drafting.add_argument("--max-estimated-usd", type=float)
    drafting.add_argument("--glossary", type=Path)
    drafting.add_argument("--ready", type=Path)
    drafting.add_argument("--utterance-map", type=Path,
                          help="write a source-linked JSON draft without fixed cue layout")
    drafting.add_argument("--run", action="store_true", help="make authorized billable calls")

    second_opinion = commands.add_parser(
        "translation-second-opinion", help="compare a draft with Google NMT"
    )
    second_opinion.add_argument("source", type=Path)
    second_opinion.add_argument("english_draft", type=Path)
    second_opinion.add_argument("output", type=Path)
    second_opinion.add_argument("--source-language", required=True)
    second_opinion.add_argument("--utterance-map", type=Path,
                                help="current explicit source-to-English links")
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

    layout_repair = commands.add_parser(
        "layout-repair", help="split or retime both tracks from accepted word timing"
    )
    layout_repair.add_argument("case", type=Path)
    layout_repair.add_argument("target", type=Path)
    layout_repair.add_argument("decision", type=Path)

    bundling = commands.add_parser("bundle", help="gather interval clips and subtitle evidence")
    bundling.add_argument("case", type=Path)
    bundling.add_argument("target", type=Path,
                          help="English SRT, or '-' while English is pending")
    bundling.add_argument("start_ms", type=int)
    bundling.add_argument("end_ms", type=int)
    bundling.add_argument("--context", type=float, default=2)
    bundling.add_argument("--audio-report", type=Path)
    bundling.add_argument("--layout-report", type=Path)
    bundling.add_argument("--asr-manifest", type=Path, action="append", default=[])
    bundling.add_argument("--visual-cue-id", type=int, action="append", default=[],
                          help="save overview and before/during/after frames for this source cue")
    bundling.add_argument("--visual-notes", type=Path,
                          help="attach agent-authored observations of the sampled frames")
    bundling.add_argument("--output", type=Path)

    reviewing = commands.add_parser("review", help="extract audio for the next pending issue")
    reviewing.add_argument("case", type=Path)
    reviewing.add_argument("--issue-id")
    reviewing.add_argument("--context", type=float, default=6)

    translating = commands.add_parser("translation-audit", help="compare two subtitle timelines")
    translating.add_argument("source", type=Path)
    translating.add_argument("target", type=Path)
    translating.add_argument("--output", type=Path, required=True)
    translating.add_argument("--max-cps", type=float, default=25)

    checking_audio = commands.add_parser(
        "audio-check", help="compare local independent ASR with the source SRT"
    )
    checking_audio.add_argument("case", type=Path)
    checking_audio.add_argument("--output", type=Path, required=True)
    checking_audio.add_argument("--cache", type=Path, required=True)
    checking_audio.add_argument("--model", default="mlx-community/Qwen3-ASR-1.7B-4bit")
    checking_audio.add_argument("--model-revision", default="78a389c776a5483b2d0d4ea5494e11012e0d6159")
    checking_audio.add_argument("--language", default="Turkish")
    checking_audio.add_argument("--window-seconds", type=float, default=30)
    checking_audio.add_argument("--start-seconds", type=float, default=0)
    checking_audio.add_argument("--end-seconds", type=float)
    checking_audio.add_argument("--max-tokens", type=int, default=256)

    adjudicating_audio = commands.add_parser(
        "audio-adjudicate", help="save one current audio-question decision"
    )
    adjudicating_audio.add_argument("audio_report", type=Path)
    adjudicating_audio.add_argument("output", type=Path)
    adjudicating_audio.add_argument("decision", type=Path)

    checking_episode = commands.add_parser(
        "episode-check", help="refresh source, audio, translation, and install checks"
    )
    checking_episode.add_argument("case", type=Path)
    checking_episode.add_argument("target", type=Path)
    checking_episode.add_argument("--source-language", required=True)
    checking_episode.add_argument("--target-language", required=True)
    checking_episode.add_argument("--output", type=Path, required=True)
    checking_episode.add_argument("--model", default="mlx-community/Qwen3-ASR-1.7B-4bit")
    checking_episode.add_argument("--model-revision", default="78a389c776a5483b2d0d4ea5494e11012e0d6159")
    checking_episode.add_argument("--audio-language", default="Turkish")
    checking_episode.add_argument("--semantic-manifest", type=Path)
    checking_episode.add_argument("--semantic-reviews", type=Path)
    checking_episode.add_argument("--semantic-model", default="agent")
    checking_episode.add_argument("--semantic-batch-size", type=int, default=12)
    checking_episode.add_argument("--glossary", type=Path)
    checking_episode.add_argument("--layout-report", type=Path)
    checking_episode.add_argument("--timing-decisions", type=Path)
    checking_episode.add_argument("--render-report", type=Path)

    releasing = commands.add_parser("release", help="validate and optionally install one pair")
    releasing.add_argument("video", type=Path)
    releasing.add_argument("source", type=Path)
    releasing.add_argument("target", type=Path)
    releasing.add_argument("--source-language", required=True)
    releasing.add_argument("--target-language", required=True)
    releasing.add_argument("--case", type=Path, required=True)
    releasing.add_argument("--translation-report", type=Path, required=True)
    releasing.add_argument("--translation-decisions", type=Path)
    releasing.add_argument("--audio-report", type=Path, required=True)
    releasing.add_argument("--audio-decisions", type=Path, required=True)
    releasing.add_argument("--semantic-manifest", type=Path)
    releasing.add_argument("--semantic-reviews", type=Path)
    releasing.add_argument("--semantic-model", default="agent")
    releasing.add_argument("--semantic-batch-size", type=int, default=12)
    releasing.add_argument("--glossary", type=Path)
    releasing.add_argument("--layout-report", type=Path)
    releasing.add_argument("--timing-decisions", type=Path)
    releasing.add_argument("--render-report", type=Path)
    releasing.add_argument("--output", type=Path, required=True)
    releasing.add_argument("--apply", action="store_true")
    releasing.add_argument("--backup-dir", type=Path)

    args = parser.parse_args()
    {"audit": audit, "transcribe": transcribe, "translate": translate_draft,
     "translation-second-opinion": translation_second_opinion,
     "record": record, "insert-pair": insert_pair, "replace-pair": replace_pair,
     "layout-repair": replace_pair,
     "review": review, "bundle": bundle, "audio-check": audio_check,
     "audio-adjudicate": audio_adjudicate,
     "episode-check": episode_check, "translation-audit": translation_audit,
     "release": release}[args.action](args)


if __name__ == "__main__":
    main()
