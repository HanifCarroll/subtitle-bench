#!/usr/bin/env python3
"""Audit long subtitle cues and apply audio-verified timing to a TR/EN pair."""

import argparse
import json
import os
import re
import shutil
import tempfile
from datetime import datetime
from pathlib import Path


ROOT = Path(os.environ.get("LEYLA_MEDIA_ROOT", Path.home() / "Movies/Leyla ile Mecnun"))
EPISODES = ROOT / "Episodes"
REVIEWS = ROOT / "Workflow" / "pilots"
TIMESTAMP = re.compile(r"(\d{2}):(\d{2}):(\d{2}),(\d{3})")


def milliseconds(value):
    match = TIMESTAMP.fullmatch(value)
    if match is None:
        raise ValueError(f"Invalid SRT timestamp: {value}")

    hours, minutes, seconds, millis = map(int, match.groups())
    if minutes >= 60 or seconds >= 60:
        raise ValueError(f"Invalid SRT timestamp: {value}")

    return ((hours * 60 + minutes) * 60 + seconds) * 1000 + millis


def read_cues(path):
    # 1. Parse each SRT block and reject malformed or unnumbered cues.

    raw = path.read_text(encoding="utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
    cues = []
    for block in re.split(r"\n\s*\n", raw.strip()):
        lines = block.splitlines()
        if len(lines) < 3 or " --> " not in lines[1]:
            raise ValueError(f"Malformed cue in {path}: {block[:80]}")

        cue_id = int(lines[0])
        start_text, end_text = lines[1].split(" --> ", 1)
        start, end = milliseconds(start_text), milliseconds(end_text)
        text = "\n".join(lines[2:]).strip()
        if cue_id != len(cues) + 1 or start >= end or not text:
            raise ValueError(f"Invalid cue {cue_id} in {path}")

        cues.append({
            "id": cue_id, "start": start, "end": end,
            "start_text": start_text, "end_text": end_text, "text": text,
        })

    return cues


def video_for_episode(number):
    videos = list(EPISODES.glob(f"{number:03} - *.webm"))
    if len(videos) != 1:
        raise ValueError(f"Expected one video for episode {number:03}; found {len(videos)}")

    return videos[0]


def paired_cues(video):
    turkish_path = video.with_suffix(".tr.srt")
    english_path = video.with_suffix(".en.srt")
    turkish, english = read_cues(turkish_path), read_cues(english_path)
    if len(turkish) != len(english):
        raise ValueError(f"Different TR/EN cue counts for {video.name}")

    for source, translation in zip(turkish, english):
        if (source["start"], source["end"]) != (translation["start"], translation["end"]):
            raise ValueError(f"TR/EN timing differs at cue {source['id']} in {video.name}")

    return turkish_path, english_path, turkish


def audit(paths, max_seconds):
    # 1. Measure every cue on the SRT timeline; a flag is a review request.

    results = []
    total_cues = 0
    for path in paths:
        cues = read_cues(path)
        total_cues += len(cues)
        episode = path.name[:3]
        for cue in cues:
            duration = (cue["end"] - cue["start"]) / 1000
            if duration <= max_seconds:
                continue

            results.append({
                "episode": episode,
                "cue": cue["id"],
                "start": cue["start_text"],
                "end": cue["end_text"],
                "duration_seconds": round(duration, 3),
                "text": cue["text"],
                "file": str(path),
            })

    # 2. Put the worst outliers first and summarize the exact audit policy.

    results.sort(key=lambda item: -item["duration_seconds"])
    return {
        "max_seconds": max_seconds,
        "files": len(paths),
        "cues_checked": total_cues,
        "flagged": len(results),
        "note": "Duration flags cannot prove speech timing. Compare each flagged cue with audio before editing.",
        "items": results,
    }


def replace_timestamp(path, cue, new_start, new_end):
    raw = path.read_text(encoding="utf-8")
    old_header = f"{cue['id']}\n{cue['start_text']} --> {cue['end_text']}\n"
    new_header = f"{cue['id']}\n{new_start} --> {new_end}\n"
    if raw.count(old_header) != 1:
        raise ValueError(f"Cannot uniquely find cue {cue['id']} in {path}")

    return raw.replace(old_header, new_header, 1)


def install_text(path, text):
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as temp:
        temp.write(text)
        temp.flush()
        os.fsync(temp.fileno())
        temporary_path = Path(temp.name)

    os.chmod(temporary_path, path.stat().st_mode)
    temporary_path.replace(path)


def retime(number, cue_id, start_text, end_text, evidence):
    # 1. Validate both installed languages and the proposed audio-based interval.

    video = video_for_episode(number)
    turkish_path, english_path, cues = paired_cues(video)
    start, end = milliseconds(start_text), milliseconds(end_text)
    if not 1 <= cue_id <= len(cues) or start >= end:
        raise ValueError("Invalid cue number or interval")

    cue = cues[cue_id - 1]
    if cue_id > 1 and start < cues[cue_id - 2]["end"]:
        raise ValueError("New start overlaps the previous cue")
    if cue_id < len(cues) and end > cues[cue_id]["start"]:
        raise ValueError("New end overlaps the next cue")

    english_cue = read_cues(english_path)[cue_id - 1]
    updated = {
        turkish_path: replace_timestamp(turkish_path, cue, start_text, end_text),
        english_path: replace_timestamp(english_path, english_cue, start_text, end_text),
    }

    # 2. Save a separate rollback, then update both sidecars and verify parity.

    revision = REVIEWS / "timing-revisions" / f"{number:03}-{cue_id}-{datetime.now().strftime('%Y%m%dT%H%M%S')}"
    revision.mkdir(parents=True, exist_ok=False)
    for path in updated:
        shutil.copy2(path, revision / path.name)

    try:
        for path, text in updated.items():
            install_text(path, text)

        paired_cues(video)
    except Exception:
        for path in updated:
            shutil.copy2(revision / path.name, path)
        raise

    result = {
        "episode": number, "cue": cue_id,
        "old": [cue["start_text"], cue["end_text"]],
        "new": [start_text, end_text],
        "evidence": evidence,
        "rollback": str(revision),
    }
    (revision / "change.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    audit_command = actions.add_parser("audit", help="flag long cues without editing subtitles")
    target = audit_command.add_mutually_exclusive_group()
    target.add_argument("--episode", type=int)
    target.add_argument("--srt", type=Path)
    audit_command.add_argument("--max-seconds", type=float, default=8.0)
    audit_command.add_argument("--output", type=Path)
    retime_command = actions.add_parser("retime", help="change one cue in both installed languages")
    retime_command.add_argument("episode", type=int)
    retime_command.add_argument("cue", type=int)
    retime_command.add_argument("start")
    retime_command.add_argument("end")
    retime_command.add_argument("--evidence", required=True)
    actions.add_parser("check", help="run a small parser and duration self-check")
    args = parser.parse_args()

    if args.action == "check":
        assert milliseconds("00:17:31,099") == 1_051_099
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "069.tr.srt"
            path.write_text("1\n00:17:04,250 --> 00:17:32,700\nBenim kısmetimde neler var?\n", encoding="utf-8")
            report = audit([path], 8.0)
            assert report["flagged"] == 1 and report["items"][0]["duration_seconds"] == 28.45
            changed = replace_timestamp(path, read_cues(path)[0], "00:17:31,000", "00:17:32,600")
            assert "00:17:31,000 --> 00:17:32,600" in changed
        print("check ok")
        return

    if args.action == "retime":
        print(json.dumps(retime(args.episode, args.cue, args.start, args.end, args.evidence), ensure_ascii=False))
        return

    if args.max_seconds <= 0:
        parser.error("--max-seconds must be positive")

    if args.srt:
        paths = [args.srt]
    elif args.episode:
        video = video_for_episode(args.episode)
        turkish_path, _, _ = paired_cues(video)
        paths = [turkish_path]
    else:
        paths = []
        for number in range(1, 105):
            video = video_for_episode(number)
            turkish_path, _, _ = paired_cues(video)
            paths.append(turkish_path)

    report = audit(paths, args.max_seconds)
    output = args.output or (
        REVIEWS / "timing-audit.json" if not args.srt and not args.episode
        else REVIEWS / f"timing-audit-{paths[0].name[:3]}.json"
    )
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({key: value for key, value in report.items() if key != "items"} | {"output": str(output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
