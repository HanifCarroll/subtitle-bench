#!/usr/bin/env python3
"""Join overlapping SRT drafts while keeping every clip seam open for review."""

import argparse
import hashlib
import json
import runpy
import shutil
import subprocess
from pathlib import Path


READ_CUES = runpy.run_path(str(Path(__file__).with_name("subtitle-timing.py")))["read_cues"]


def timestamp(milliseconds):
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, millis = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{seconds:02},{millis:03}"


def file_hash(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)

    return digest.hexdigest()


def source_path(value, manifest_path):
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = manifest_path.parent / path

    return path.resolve(strict=True)


def load_manifest(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    video = source_path(data["video"], path)
    language = data["language"]
    clips = []

    if not video.is_file() or not isinstance(language, str) or not language.isalpha():
        raise ValueError("Expected a video file and an alphabetic source language")

    for item in data["clips"]:
        clip = {
            "srt": source_path(item["srt"], path),
            "offset_ms": item["offset_ms"],
            "core_start_ms": item["core_start_ms"],
            "core_end_ms": item["core_end_ms"],
        }
        times = (clip["offset_ms"], clip["core_start_ms"], clip["core_end_ms"])
        if not clip["srt"].is_file() or any(type(value) is not int for value in times):
            raise ValueError("Each clip needs an SRT file and integer millisecond times")
        if not 0 <= clip["offset_ms"] <= clip["core_start_ms"] < clip["core_end_ms"]:
            raise ValueError(f"Invalid clip timeline: {clip['srt']}")

        clips.append(clip)

    if len(clips) < 2:
        raise ValueError("Provide at least two overlapping clips")

    for left, right in zip(clips, clips[1:]):
        if left["core_end_ms"] != right["core_start_ms"]:
            raise ValueError("Clip core intervals must meet at one seam")
        if right["offset_ms"] >= right["core_start_ms"]:
            raise ValueError("The next clip must include audio before its core starts")

    return video, language.lower(), clips


def shifted_cues(clip):
    cues = []
    raw = clip["srt"].read_text(encoding="utf-8-sig").strip()
    for cue in READ_CUES(clip["srt"]) if raw else []:
        start = clip["offset_ms"] + cue["start"]
        end = clip["offset_ms"] + cue["end"]
        cues.append({
            "source": str(clip["srt"]),
            "source_cue": cue["id"],
            "start_ms": start,
            "end_ms": end,
            "text": cue["text"],
        })

    return cues


def intersects(cue, start, end):
    return cue["start_ms"] < end and cue["end_ms"] > start


def write_srt(path, cues):
    blocks = [
        f"{number}\n{timestamp(cue['start_ms'])} --> {timestamp(cue['end_ms'])}\n{cue['text']}"
        for number, cue in enumerate(cues, 1)
    ]
    path.write_text("\n\n".join(blocks) + "\n", encoding="utf-8")


def extract_review_audio(video, start_ms, end_ms, path):
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError("ffmpeg is required to extract seam audio")

    subprocess.run([
        ffmpeg, "-hide_banner", "-loglevel", "error", "-ss", f"{start_ms / 1000:.3f}",
        "-t", f"{(end_ms - start_ms) / 1000:.3f}", "-i", str(video), "-vn",
        "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", "-y", str(path),
    ], check=True)

    if not path.is_file() or path.stat().st_size == 0:
        raise RuntimeError(f"No audio was extracted at {timestamp(start_ms)}")


def join(manifest_path, output_dir, padding_ms):
    # 1. Validate sources and keep the output separate from every input.

    video, language, clips = load_manifest(manifest_path)
    if output_dir.exists():
        raise FileExistsError(f"Choose a new output folder: {output_dir}")

    source_cues = [shifted_cues(clip) for clip in clips]
    output_dir.mkdir(parents=True)

    # 2. Keep every cue that touches its clip's core, including boundary phrases.

    draft = [
        cue
        for clip, cues in zip(clips, source_cues)
        for cue in cues
        if intersects(cue, clip["core_start_ms"], clip["core_end_ms"])
    ]
    draft.sort(key=lambda cue: (cue["start_ms"], cue["end_ms"], cue["source"]))
    draft_path = output_dir / f"draft.{language}.srt"
    write_srt(draft_path, draft)

    # 3. Expose both versions and real audio at each seam for agent review.

    seams = []
    for index, (left, right) in enumerate(zip(clips, clips[1:]), 1):
        boundary = left["core_end_ms"]
        start = max(0, boundary - padding_ms)
        end = boundary + padding_ms
        audio_path = output_dir / f"seam-{index:02}-{boundary}.wav"
        extract_review_audio(video, start, end, audio_path)
        seams.append({
            "status": "unresolved",
            "boundary_ms": boundary,
            "review_start_ms": start,
            "review_end_ms": end,
            "audio": str(audio_path),
            "audio_sha256": file_hash(audio_path),
            "left": [cue for cue in source_cues[index - 1] if intersects(cue, start, end)],
            "right": [cue for cue in source_cues[index] if intersects(cue, start, end)],
        })

    report = {
        "video": str(video),
        "video_sha256": file_hash(video),
        "language": language,
        "draft": str(draft_path),
        "draft_cues": len(draft),
        "note": "The draft may contain duplicate seam transcriptions. Review audio and both versions before editing; this command makes no choice.",
        "clips": [{**clip, "srt": str(clip["srt"]), "srt_sha256": file_hash(clip["srt"])} for clip in clips],
        "seams": seams,
    }
    report_path = output_dir / "seam-review.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"draft": str(draft_path), "review": str(report_path), "seams": len(seams)}))


def check():
    cue = {"start_ms": 4_798_420, "end_ms": 4_801_220}
    assert intersects(cue, 4_500_000, 4_800_000)
    assert intersects(cue, 4_800_000, 5_100_000)
    assert intersects(cue, 4_800_000, 4_801_000)
    assert timestamp(4_800_000) == "01:20:00,000"
    print("check ok")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, nargs="?")
    parser.add_argument("output", type=Path, nargs="?")
    parser.add_argument("--padding-seconds", type=float, default=6)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    if args.check:
        check()
        return

    if args.manifest is None or args.output is None or not 1 <= args.padding_seconds <= 30:
        parser.error("provide a manifest, a new output folder, and 1-30 seconds of seam padding")

    join(args.manifest.resolve(strict=True), args.output.resolve(), round(args.padding_seconds * 1000))


if __name__ == "__main__":
    main()
