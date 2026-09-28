#!/usr/bin/env python3
"""Agent-operated review of one video's source-language subtitle draft."""

import argparse
import json
import os
import re
import runpy
import shutil
import statistics
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parent
TIMING = runpy.run_path(str(SCRIPTS / "subtitle-timing.py"))
JOINER = runpy.run_path(str(SCRIPTS / "join-clip-drafts.py"))
READ_CUES = TIMING["read_cues"]
WRITE_SRT = JOINER["write_srt"]
FILE_HASH = JOINER["file_hash"]


def normalized(text):
    return " ".join(re.findall(r"\w+", text.casefold()))


def is_non_speech_label(text):
    return re.fullmatch(r"\s*(?:\[[^\]]+\]\s*)+", text) is not None


def save_json(path, value):
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def load_case(directory):
    case = json.loads((directory / "case.json").read_text(encoding="utf-8"))
    working = directory / f"working.{case['language']}.srt"
    return case, working


def unique_text_cues(cues):
    matches = defaultdict(list)
    for cue in cues:
        text = normalized(cue["text"])
        if len(text) >= 20:
            matches[text].append(cue)

    return {text: items[0] for text, items in matches.items() if len(items) == 1}


def estimate_reference_offset(draft, reference):
    # 1. Match distinctive whole cues without assuming the two cuts have one clock.

    draft_text = unique_text_cues(draft)
    reference_text = unique_text_cues(reference)
    pairs = []
    for text, cue in draft_text.items():
        other = reference_text.get(text)
        if other is not None:
            delta = other["start"] - cue["start"]
            if abs(delta) <= 60_000:
                pairs.append((cue["start"], delta))

    if len(pairs) < 8:
        return {
            "offset_ms": None,
            "matched_cues": len(pairs),
            "anchors": [],
            "warning": "Too few unique text matches to propose a reference offset.",
        }

    # 2. Use the densest one-second offset cluster, then show its spread over the video.

    bucket = Counter(round(delta / 1000) for _, delta in pairs).most_common(1)[0][0]
    agreeing = [
        (start, delta) for start, delta in pairs if abs(delta - bucket * 1000) <= 1500
    ]
    offset = round(statistics.median(delta for _, delta in agreeing))
    anchors = defaultdict(list)
    for start, delta in agreeing:
        anchors[start // 1_200_000].append(delta)

    return {
        "offset_ms": offset,
        "matched_cues": len(pairs),
        "agreeing_cues": len(agreeing),
        "anchors": [
            {
                "video_start_ms": index * 1_200_000,
                "matches": len(values),
                "median_offset_ms": round(statistics.median(values)),
            }
            for index, values in sorted(anchors.items())
        ],
        "warning": "Text matches suggest timing only; check cut and words against video audio.",
    }


def prepare(args):
    # 1. Validate the real inputs before creating a separate working folder.

    video = args.video.resolve(strict=True)
    draft = args.draft.resolve(strict=True)
    reference = args.reference.resolve(strict=True) if args.reference else None
    seam_report = args.seam_report.resolve(strict=True) if args.seam_report else None
    output = args.output.resolve()
    sources = [video, draft] + ([reference] if reference else [])
    if output.exists() or not all(path.is_file() for path in sources):
        raise ValueError("Output must be new, and all supplied inputs must be files")
    if not re.fullmatch(r"[A-Za-z]{2,8}(?:-[A-Za-z0-9]{2,8})*", args.language):
        raise ValueError("Source language must be a language tag such as tr or pt-BR")
    if reference is None and (
        args.reference_offset_ms is not None or args.reference_url
        or args.reference_timing_only
    ):
        raise ValueError("Reference timing and URL need a reference subtitle file")
    if args.reference_timing_only and args.reference_offset_ms is None:
        raise ValueError("A timing-only reference needs a video-checked --reference-offset-ms")

    draft_cues = READ_CUES(draft)
    reference_cues = READ_CUES(reference) if reference else []
    alignment = (
        estimate_reference_offset(draft_cues, reference_cues)
        if reference
        else {
            "offset_ms": None,
            "matched_cues": 0,
            "anchors": [],
            "warning": "No existing subtitle reference was supplied.",
        }
    )
    if args.reference_offset_ms is not None:
        alignment["offset_ms"] = args.reference_offset_ms
        alignment["override"] = True
        if args.reference_timing_only:
            alignment["warning"] = "Check the supplied timing offset against the video audio."

    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        raise RuntimeError("ffprobe is required")
    duration = float(
        subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(video),
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    )

    # 2. Preserve input identities and copy only the working SRT.

    output.mkdir(parents=True)
    working = output / f"working.{args.language.lower()}.srt"
    shutil.copy2(draft, working)
    case = {
        "video": str(video),
        "video_sha256": FILE_HASH(video),
        "duration_ms": round(duration * 1000),
        "language": args.language.lower(),
        "draft_source": str(draft),
        "draft_source_sha256": FILE_HASH(draft),
        "reference": str(reference) if reference else None,
        "reference_sha256": FILE_HASH(reference) if reference else None,
        "reference_url": args.reference_url,
        "reference_timing_only": args.reference_timing_only,
        "reference_alignment": alignment,
        "seam_report": str(seam_report) if seam_report else None,
        "seam_report_sha256": FILE_HASH(seam_report) if seam_report else None,
        "note": "Working draft only. A reference match or model output does not verify spoken words.",
    }
    save_json(output / "case.json", case)
    print(
        json.dumps(
            {
                "case": str(output),
                "working": str(working),
                "draft_cues": len(draft_cues),
                "reference_cues": len(reference_cues),
                "reference_alignment": alignment,
            },
            ensure_ascii=False,
        )
    )


def scan_coverage(directory):
    case, working = load_case(directory)
    report = directory / "speech-coverage.json"
    working_hash = FILE_HASH(working)
    subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "audit-speech-coverage.py"),
            case["video"],
            str(working),
            "--output",
            str(report),
        ],
        check=True,
    )
    if FILE_HASH(working) != working_hash:
        raise RuntimeError("Working SRT changed during the speech scan; rerun coverage")

    (directory / "speech-coverage.sha256").write_text(
        working_hash + "\n", encoding="ascii"
    )


def issue(kind, start, end, key, **detail):
    return {
        "id": f"{kind}:{key}",
        "kind": kind,
        "start_ms": start,
        "end_ms": end,
        **detail,
    }


def long_subtitle_gaps(cues, duration_ms, minimum_ms=10_000):
    """Flag cue-free spans without depending on a voice detector."""
    gaps = []
    covered_until = 0
    previous_cue = None

    for cue in sorted(cues, key=lambda item: item["start"]):
        start = min(duration_ms, max(0, cue["start"]))
        end = min(duration_ms, cue["end"])
        if start - covered_until >= minimum_ms:
            gaps.append(issue(
                "subtitle_gap", covered_until, start,
                f"{previous_cue['id'] if previous_cue else 'start'}-{cue['id']}",
                previous_cue=previous_cue["id"] if previous_cue else None,
                next_cue=cue["id"],
                duration_seconds=round((start - covered_until) / 1000, 3),
            ))

        if end > covered_until:
            covered_until = end
            previous_cue = cue

    if duration_ms - covered_until >= minimum_ms:
        gaps.append(issue(
            "subtitle_gap", covered_until, duration_ms,
            f"{previous_cue['id'] if previous_cue else 'start'}-end",
            previous_cue=previous_cue["id"] if previous_cue else None,
            next_cue=None,
            duration_seconds=round((duration_ms - covered_until) / 1000, 3),
        ))

    return gaps


def build_queue(directory):
    case, working = load_case(directory)
    if (
        case["reference"]
        and FILE_HASH(Path(case["reference"])) != case["reference_sha256"]
    ):
        raise ValueError("Reference subtitle changed since case preparation")
    if (
        case["seam_report"]
        and FILE_HASH(Path(case["seam_report"])) != case["seam_report_sha256"]
    ):
        raise ValueError("Seam report changed since case preparation")

    cues = READ_CUES(working)
    reference = READ_CUES(Path(case["reference"])) if case["reference"] else []
    offset = case["reference_alignment"]["offset_ms"]
    items = []
    warnings = []
    ignored_reference_labels = 0

    # 1. Reuse duration and overlap checks on the current working copy.

    for flagged in TIMING["audit"]([working], 8.0)["items"]:
        cue = cues[flagged["cue"] - 1]
        items.append(
            issue(
                "long_cue",
                cue["start"],
                cue["end"],
                cue["id"],
                cue_ids=[cue["id"]],
                duration_seconds=flagged["duration_seconds"],
            )
        )
    for left, right in zip(cues, cues[1:]):
        if left["end"] > right["start"]:
            items.append(
                issue(
                    "overlap",
                    right["start"],
                    min(left["end"], right["end"]),
                    f"{left['id']}-{right['id']}",
                    cue_ids=[left["id"], right["id"]],
                )
            )

    items.extend(long_subtitle_gaps(cues, case["duration_ms"]))

    run_start = 0
    for index in range(1, len(cues) + 1):
        same = index < len(cues) and normalized(cues[index]["text"]) == normalized(
            cues[run_start]["text"]
        )
        if same:
            continue
        run = cues[run_start:index]
        if len(run) >= 3 and len(normalized(run[0]["text"])) >= 8:
            items.append(
                issue(
                    "repetition",
                    run[0]["start"],
                    run[-1]["end"],
                    f"{run[0]['id']}-{run[-1]['id']}",
                    cue_ids=[cue["id"] for cue in run],
                )
            )
        run_start = index

    # 2. Compare the reference at its proposed video offset, without adopting it.

    if offset is None:
        warnings.append(
            "No aligned reference is available; reference issues are omitted."
        )
    else:
        for ref in reference:
            if is_non_speech_label(ref["text"]):
                ignored_reference_labels += 1
                continue

            start, end = ref["start"] - offset, ref["end"] - offset
            if end <= 0 or start >= case["duration_ms"]:
                continue
            nearby = [
                cue
                for cue in cues
                if cue["start"] < end + 500 and cue["end"] > start - 500
            ]
            if not nearby:
                items.append(
                    issue(
                        "reference_only",
                        max(0, start),
                        end,
                        ref["id"],
                        reference_cue=ref["id"],
                    )
                )
            elif not case.get("reference_timing_only", False) and len(normalized(ref["text"])) >= 12:
                compared = normalized(" ".join(cue["text"] for cue in nearby))
                similarity = SequenceMatcher(
                    None, normalized(ref["text"]), compared
                ).ratio()
                if similarity < 0.4:
                    items.append(
                        issue(
                            "reference_disagreement",
                            max(0, start),
                            end,
                            ref["id"],
                            reference_cue=ref["id"],
                            cue_ids=[cue["id"] for cue in nearby],
                            text_similarity=round(similarity, 3),
                        )
                    )

    # 3. Add both directions of the speech scan while it matches this exact draft.

    coverage = directory / "speech-coverage.json"
    coverage_hash = directory / "speech-coverage.sha256"
    if (
        coverage.is_file()
        and coverage_hash.is_file()
        and coverage_hash.read_text().strip() == FILE_HASH(working)
    ):
        scan = json.loads(coverage.read_text(encoding="utf-8"))
        for index, gap in enumerate(scan["items"], 1):
            items.append(
                issue(
                    "possible_speech_gap",
                    round(gap["start_seconds"] * 1000),
                    round(gap["end_seconds"] * 1000),
                    index,
                )
            )
        for index, span in enumerate(scan.get("possible_subtitle_without_speech", []), 1):
            items.append(
                issue(
                    "possible_subtitle_without_speech",
                    round(span["start_seconds"] * 1000),
                    round(span["end_seconds"] * 1000),
                    f"{span['cue_id']}-{index}",
                    cue_ids=[span["cue_id"]],
                    duration_seconds=span["duration_seconds"],
                    position=span["position"],
                )
            )
    else:
        warnings.append(
            "Speech-gap scan is missing or stale; run coverage again after edits."
        )

    if case["seam_report"]:
        seams = json.loads(Path(case["seam_report"]).read_text(encoding="utf-8"))[
            "seams"
        ]
        for index, seam in enumerate(seams, 1):
            if seam["status"] == "unresolved":
                items.append(
                    issue(
                        "unresolved_seam",
                        seam["review_start_ms"],
                        seam["review_end_ms"],
                        index,
                        boundary_ms=seam["boundary_ms"],
                    )
                )

    items.sort(key=lambda item: (item["start_ms"], item["end_ms"], item["id"]))
    report = {
        "working": str(working),
        "working_sha256": FILE_HASH(working),
        "reference_offset_ms": offset,
        "ignored_reference_labels": ignored_reference_labels,
        "counts": dict(Counter(item["kind"] for item in items)),
        "warnings": warnings,
        "note": "Every flag is a question for review, not a proposed edit.",
        "issues": items,
    }
    save_json(directory / "review-queue.json", report)
    return report


def inspect(directory, at_seconds, before, after):
    case, working = load_case(directory)
    if (
        before < 0
        or after < 0
        or FILE_HASH(Path(case["video"])) != case["video_sha256"]
    ):
        raise ValueError(
            "Review interval must be nonnegative and the original video unchanged"
        )

    start = max(0, round((at_seconds - before) * 1000))
    end = min(case["duration_ms"], round((at_seconds + after) * 1000))
    if end <= start or end - start > 60_000:
        raise ValueError("Choose a nonempty review interval of at most 60 seconds")

    # 1. Extract a playable copy from the original video at exact video times.

    clips = directory / "clips"
    clips.mkdir(exist_ok=True)
    stem = f"{start}-{end}"
    audio = clips / f"{stem}.wav"
    video_clip = clips / f"{stem}.mp4"
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError("ffmpeg is required")
    if not audio.is_file():
        JOINER["extract_review_audio"](Path(case["video"]), start, end, audio)
    if not video_clip.is_file():
        subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-ss",
                f"{start / 1000:.3f}",
                "-i",
                case["video"],
                "-t",
                f"{(end - start) / 1000:.3f}",
                "-map",
                "0:v:0",
                "-map",
                "0:a:0?",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "24",
                "-c:a",
                "aac",
                "-movflags",
                "+faststart",
                "-y",
                str(video_clip),
            ],
            check=True,
        )

    # 2. Show only the words and flags near the selected original-video interval.

    offset = case["reference_alignment"]["offset_ms"]
    draft_cues = [
        cue for cue in READ_CUES(working) if cue["start"] < end and cue["end"] > start
    ]
    reference_cues = []
    if offset is not None and case["reference"]:
        for cue in READ_CUES(Path(case["reference"])):
            shifted = {
                **cue,
                "video_start_ms": cue["start"] - offset,
                "video_end_ms": cue["end"] - offset,
            }
            if shifted["video_start_ms"] < end and shifted["video_end_ms"] > start:
                reference_cues.append(shifted)
    seams = []
    if case["seam_report"]:
        seams = [
            seam
            for seam in json.loads(
                Path(case["seam_report"]).read_text(encoding="utf-8")
            )["seams"]
            if seam["review_start_ms"] < end and seam["review_end_ms"] > start
        ]

    current_issues = [
        item
        for item in build_queue(directory)["issues"]
        if item["start_ms"] < end and item["end_ms"] > start
    ]
    issue_ids = {item["id"] for item in current_issues}
    decisions = []
    for path in sorted((directory / "decisions").glob("*/decision.json")):
        decision = json.loads(path.read_text(encoding="utf-8"))
        if decision["issue_id"] in issue_ids:
            decisions.append({"path": str(path), **decision})
    report = {
        "video_start_ms": start,
        "video_end_ms": end,
        "original_video": case["video"],
        "audio_clip": str(audio),
        "video_clip": str(video_clip),
        "audio_sha256": FILE_HASH(audio),
        "working_sha256": FILE_HASH(working),
        "reference_offset_ms": offset,
        "reference_url": case.get("reference_url"),
        "working_cues": draft_cues,
        "reference_cues": reference_cues,
        "seams": seams,
        "issues": current_issues,
        "recorded_decisions": decisions,
        "note": "The tool does not verify words by hearing audio. An audio-capable reviewer must check the original clip.",
    }
    path = clips / f"{stem}.json"
    save_json(path, report)
    print(
        json.dumps(
            {
                "inspection": str(path),
                "audio": str(audio),
                "video": str(video_clip),
                "working_cues": len(draft_cues),
                "reference_cues": len(reference_cues),
                "issues": len(report["issues"]),
            },
            ensure_ascii=False,
        )
    )


def splice_cues(cues, decision, duration_ms):
    replacement = decision.get("replacement", [])
    if not isinstance(replacement, list) or any(
        not isinstance(cue, dict) for cue in replacement
    ):
        raise ValueError("replacement must be a list of cues")

    for cue in replacement:
        if (
            not isinstance(cue.get("start_ms"), int)
            or not isinstance(cue.get("end_ms"), int)
            or not isinstance(cue.get("text"), str)
            or not cue["text"].strip()
            or not 0 <= cue["start_ms"] < cue["end_ms"] <= duration_ms
        ):
            raise ValueError(
                "Replacement cues need valid video-relative times and nonempty text"
            )

    ids = decision.get("replace_ids", [])
    if not isinstance(ids, list) or any(type(cue_id) is not int for cue_id in ids):
        raise ValueError("replace_ids must be a list of cue numbers")

    if ids:
        if ids != list(range(ids[0], ids[-1] + 1)) or not 1 <= ids[0] <= ids[-1] <= len(
            cues
        ):
            raise ValueError("replace_ids must be a contiguous existing cue range")
        first, last = ids[0] - 1, ids[-1]
    else:
        after_id = decision.get("insert_after")
        if (
            not isinstance(after_id, int)
            or not 0 <= after_id <= len(cues)
            or not replacement
        ):
            raise ValueError("An insertion needs insert_after and replacement cues")
        first = last = after_id

    updated = (
        cues[:first]
        + [
            {
                "start_ms": cue["start_ms"],
                "end_ms": cue["end_ms"],
                "text": cue["text"].strip(),
            }
            for cue in replacement
        ]
        + cues[last:]
    )
    standardized = [
        {
            "start_ms": cue.get("start_ms", cue.get("start")),
            "end_ms": cue.get("end_ms", cue.get("end")),
            "text": cue["text"],
        }
        for cue in updated
    ]
    if any(
        standardized[index]["start_ms"] > standardized[index + 1]["start_ms"]
        for index in range(len(standardized) - 1)
    ):
        raise ValueError("Replacement would put cues out of start-time order")

    return standardized


def record_decision(directory, decision_path):
    case, working = load_case(directory)
    decision = json.loads(decision_path.read_text(encoding="utf-8"))
    if decision.get("status") not in ("unresolved", "resolved", "reviewed") or not decision.get(
        "issue_id"
    ):
        raise ValueError("Decision needs an issue_id and a valid review status")
    if not isinstance(decision.get("reason"), str) or not decision["reason"].strip():
        raise ValueError("Decision needs a reason")
    evidence = decision.get("evidence")
    if (
        not isinstance(evidence, list)
        or not evidence
        or any(
            not isinstance(path, str) or not (directory / path).is_file()
            for path in evidence
        )
    ):
        raise ValueError("Decision needs paths to existing evidence files")
    if decision["status"] in ("unresolved", "reviewed") and any(
        key in decision for key in ("replace_ids", "insert_after", "replacement")
    ):
        raise ValueError("Only a resolved decision can edit the working SRT")

    issue = next((item for item in build_queue(directory)["issues"]
                  if item["id"] == decision["issue_id"]), None)
    if issue is None:
        raise ValueError("Decision issue_id is absent from the current review queue")

    record = {
        **decision,
        "issue_interval": {key: issue[key] for key in ("kind", "start_ms", "end_ms")},
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "working_before_sha256": FILE_HASH(working),
    }
    if decision["status"] in ("resolved", "reviewed"):
        if (
            decision.get("expected_working_sha256") != record["working_before_sha256"]
            or not isinstance(decision.get("reviewer"), str)
            or not decision["reviewer"].strip()
        ):
            raise ValueError(
                "Review needs the current draft hash and an identified reviewer"
            )

    if decision["status"] == "resolved":

        # 1. Validate a local edit against the current SRT before changing it.

        updated = splice_cues(READ_CUES(working), decision, case["duration_ms"])
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".srt", dir=directory, delete=False
        ) as temp:
            temporary = Path(temp.name)
        try:
            WRITE_SRT(temporary, updated)
            READ_CUES(temporary)

            # 2. Keep both versions with the decision, then replace only the working copy.

            revision = (
                directory
                / "decisions"
                / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
            )
            revision.mkdir(parents=True)
            shutil.copy2(working, revision / "before.srt")
            shutil.copy2(temporary, revision / "after.srt")
            record["working_after_sha256"] = FILE_HASH(temporary)
            save_json(revision / "decision.json", record)
            os.replace(temporary, working)
        finally:
            temporary.unlink(missing_ok=True)
    else:
        revision = (
            directory
            / "decisions"
            / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
        )
        revision.mkdir(parents=True)
        save_json(revision / "decision.json", record)

    print(
        json.dumps(
            {
                "decision": str(revision / "decision.json"),
                "working": str(working),
                "status": decision["status"],
            },
            ensure_ascii=False,
        )
    )


def check():
    assert is_non_speech_label("[Müzik]\n[Gülme sesi]")
    assert not is_non_speech_label("[Gülme sesi]\nÖyle yapma.")

    draft = [
        {"id": 1, "start": 1000, "end": 2000, "text": "First"},
        {"id": 2, "start": 2000, "end": 3000, "text": "Second"},
    ]
    changed = splice_cues(
        draft,
        {
            "replace_ids": [2],
            "replacement": [{"start_ms": 2100, "end_ms": 2800, "text": "Corrected"}],
        },
        5000,
    )
    assert [cue["text"] for cue in changed] == ["First", "Corrected"]
    inserted = splice_cues(
        draft,
        {
            "insert_after": 1,
            "replacement": [{"start_ms": 2000, "end_ms": 2100, "text": "Extra"}],
        },
        5000,
    )
    assert [cue["text"] for cue in inserted] == ["First", "Extra", "Second"]
    assert estimate_reference_offset(draft * 4, draft * 4)["offset_ms"] is None
    gaps = long_subtitle_gaps(
        [{"id": 1, "start": 0, "end": 12_000},
         {"id": 2, "start": 9_000, "end": 18_000},
         {"id": 3, "start": 30_000, "end": 32_000}],
        40_000,
    )
    assert [(gap["id"], gap["start_ms"], gap["end_ms"]) for gap in gaps] == [
        ("subtitle_gap:2-3", 18_000, 30_000)
    ]

    with tempfile.TemporaryDirectory() as temporary_directory:
        directory = Path(temporary_directory)
        working = directory / "working.tr.srt"
        WRITE_SRT(
            working,
            [
                {"start_ms": 1000, "end_ms": 12_000, "text": "First"},
                {"start_ms": 12_100, "end_ms": 13_000, "text": "Second"},
            ],
        )
        reference = directory / "reference.srt"
        shutil.copy2(working, reference)
        save_json(
            directory / "case.json",
            {
                "language": "tr",
                "duration_ms": 20_000,
                "reference": str(reference),
                "reference_sha256": FILE_HASH(reference),
                "reference_alignment": {"offset_ms": None},
                "seam_report": None,
            },
        )
        evidence = directory / "review.wav"
        evidence.write_bytes(b"test-only evidence")
        decision = directory / "decision.json"
        save_json(
            decision,
            {
                "issue_id": "long_cue:1",
                "status": "resolved",
                "reason": "Synthetic edit test",
                "evidence": ["review.wav"],
                "reviewer": "self-check",
                "expected_working_sha256": FILE_HASH(working),
                "replace_ids": [1],
                "replacement": [
                    {"start_ms": 1000, "end_ms": 9000, "text": "Corrected"}
                ],
            },
        )
        reviewed = directory / "reviewed.json"
        review_record = json.loads(decision.read_text(encoding="utf-8"))
        review_record["status"] = "reviewed"
        review_record.pop("replace_ids")
        review_record.pop("replacement")
        save_json(reviewed, review_record)
        record_decision(directory, reviewed)
        assert READ_CUES(working)[0]["text"] == "First"

        record_decision(directory, decision)
        assert READ_CUES(working)[0]["text"] == "Corrected"
        assert len(list((directory / "decisions").glob("*/before.srt"))) == 1

    print("check ok")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    setup = commands.add_parser(
        "prepare", help="copy a source draft and assess a subtitle reference"
    )
    setup.add_argument("video", type=Path)
    setup.add_argument("draft", type=Path)
    setup.add_argument("output", type=Path)
    setup.add_argument("--language", required=True)
    setup.add_argument("--reference", type=Path)
    setup.add_argument("--seam-report", type=Path)
    setup.add_argument("--reference-url")
    setup.add_argument("--reference-offset-ms", type=int)
    setup.add_argument("--reference-timing-only", action="store_true")
    for name in ("coverage", "queue"):
        commands.add_parser(name).add_argument("case", type=Path)
    inspection = commands.add_parser(
        "inspect", help="extract original media and nearby evidence"
    )
    inspection.add_argument("case", type=Path)
    inspection.add_argument("--at-seconds", type=float, required=True)
    inspection.add_argument("--before", type=float, default=6)
    inspection.add_argument("--after", type=float, default=6)
    decision = commands.add_parser(
        "record", help="log uncertainty or apply an audio-reviewed edit"
    )
    decision.add_argument("case", type=Path)
    decision.add_argument("decision", type=Path)
    commands.add_parser("check")
    args = parser.parse_args()

    if args.command == "check":
        check()
    elif args.command == "prepare":
        prepare(args)
    elif args.command == "coverage":
        scan_coverage(args.case.resolve(strict=True))
    elif args.command == "queue":
        report = build_queue(args.case.resolve(strict=True))
        print(
            json.dumps(
                {
                    "queue": str(args.case.resolve() / "review-queue.json"),
                    "counts": report["counts"],
                    "warnings": report["warnings"],
                },
                ensure_ascii=False,
            )
        )
    elif args.command == "inspect":
        inspect(
            args.case.resolve(strict=True), args.at_seconds, args.before, args.after
        )
    else:
        record_decision(
            args.case.resolve(strict=True), args.decision.resolve(strict=True)
        )


if __name__ == "__main__":
    main()
