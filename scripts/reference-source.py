#!/usr/bin/env python3
"""Propose a cut-aligned Turkish source candidate from an existing SRT.

The proposal is timing evidence. An agent must check the words and sampled
audio before choosing it as the working source.
"""

import argparse
import json
import runpy
import shutil
import subprocess
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parent
SOURCE = runpy.run_path(str(SCRIPTS / "source-review.py"))
TIMING = runpy.run_path(str(SCRIPTS / "subtitle-timing.py"))
JOIN = runpy.run_path(str(SCRIPTS / "join-clip-drafts.py"))


def duration_ms(video):
    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        raise RuntimeError("ffprobe is required")
    result = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(video)],
        check=True, capture_output=True, text=True,
    )
    return round(float(result.stdout.strip()) * 1000)


def propose(video, transcript, reference, output, encoding="utf-8"):
    # 1. Read the independent transcript and the actual reference file.

    video = video.resolve(strict=True)
    transcript = transcript.resolve(strict=True)
    reference = reference.resolve(strict=True)
    output = output.resolve()
    if output.exists():
        raise FileExistsError(f"Use a new output directory: {output}")
    draft = TIMING["read_cues"](transcript)
    reference_text = reference.read_bytes().decode(encoding)
    output.mkdir(parents=True)
    normalized = output / "reference.utf8.srt"
    normalized.write_text(reference_text, encoding="utf-8")
    source = TIMING["read_cues"](normalized)
    alignment = SOURCE["estimate_reference_offset"](draft, source)
    length = duration_ms(video)

    # 2. Propose a shifted copy only when the match is spread across the cut.

    offset = alignment.get("offset_ms")
    anchors = alignment.get("anchors", [])
    anchor_coverage = len({min(2, 3 * item["video_start_ms"] // length)
                           for item in anchors}) if length else 0
    anchor_values = [item["median_offset_ms"] for item in anchors]
    spread = max(anchor_values) - min(anchor_values) if anchor_values else None
    checks = {
        "at_least_20_agreeing_cues": alignment.get("agreeing_cues", 0) >= 20,
        "anchors_in_three_thirds": anchor_coverage == 3,
        "anchor_spread_at_most_1000_ms": spread is not None and spread <= 1000,
    }
    candidate = None
    if offset is not None and all(checks.values()):
        shifted = []
        for cue in source:
            start, end = cue["start"] - offset, cue["end"] - offset
            if start < 0 or end > length:
                continue
            shifted.append({"start_ms": start, "end_ms": end,
                            "text": cue["text"]})
        candidate = output / "proposed.tr.srt"
        JOIN["write_srt"](candidate, shifted)
        TIMING["read_cues"](candidate)

    # 3. Save an inspectable decision input; never claim the reference is true.

    report = {
        "video": str(video), "video_sha256": JOIN["file_hash"](video),
        "duration_ms": length,
        "transcript": str(transcript), "transcript_sha256": JOIN["file_hash"](transcript),
        "reference": str(reference), "reference_sha256": JOIN["file_hash"](reference),
        "reference_encoding": encoding, "alignment": alignment,
        "anchor_spread_ms": spread, "checks": checks,
        "status": "timing_proposal" if candidate else "insufficient_timing_evidence",
        "candidate": str(candidate) if candidate else None,
        "candidate_sha256": JOIN["file_hash"](candidate) if candidate else None,
        "agent_checks": [
            "Verify the reference belongs to the episode and this cut.",
            "Compare original audio with the proposed source at opening, middle, tail, and every suspicious span.",
            "Check omissions, additions, music, short replies, and any detected drift before selecting a working source.",
        ],
    }
    (output / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path)
    parser.add_argument("transcript", type=Path,
                        help="independent Turkish ASR draft on the video clock")
    parser.add_argument("reference", type=Path)
    parser.add_argument("output", type=Path, help="new output directory")
    parser.add_argument("--encoding", default="utf-8")
    args = parser.parse_args()
    report = propose(args.video, args.transcript, args.reference,
                     args.output, args.encoding)
    print(json.dumps({key: report[key] for key in
                      ("status", "candidate", "checks", "alignment")},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
