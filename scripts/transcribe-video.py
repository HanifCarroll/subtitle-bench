#!/usr/bin/env python3
"""Transcribe one video in overlapping clips for source-language review."""

import argparse
import hashlib
import json
import runpy
import shutil
import subprocess
import sys
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parent
READ_CUES = runpy.run_path(str(SCRIPTS / "subtitle-timing.py"))["read_cues"]


def file_hash(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)

    return digest.hexdigest()


def video_duration(ffprobe, video):
    result = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(video)],
        check=True, capture_output=True, text=True,
    )
    duration_ms = round(float(result.stdout.strip()) * 1000)
    if duration_ms <= 0:
        raise ValueError("Video duration must be positive")

    return duration_ms


def clip_ranges(duration_ms, chunk_ms, overlap_ms):
    ranges = []
    for core_start in range(0, duration_ms, chunk_ms):
        core_end = min(duration_ms, core_start + chunk_ms)
        ranges.append({
            "offset_ms": max(0, core_start - overlap_ms),
            "core_start_ms": core_start,
            "core_end_ms": core_end,
            "audio_end_ms": min(duration_ms, core_end + overlap_ms),
        })

    return ranges


def checked_srt(path):
    if not path.exists():
        raise FileNotFoundError(f"Whisper produced no SRT: {path}")
    if path.stat().st_size:
        READ_CUES(path)


def run_clip(clip, index, output, video, language, model, vad_model, ffmpeg, whisper):
    # 1. Keep completed clips on resume, but validate their subtitle format.

    prefix = output / "clips" / f"{index:03}"
    srt = prefix.with_suffix(".srt")
    if srt.exists():
        checked_srt(srt)
        return srt

    wav = prefix.with_suffix(".wav")
    with prefix.with_suffix(".log").open("w", encoding="utf-8") as log:
        subprocess.run(
            [ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
             "-ss", f"{clip['offset_ms'] / 1000:.3f}",
             "-t", f"{(clip['audio_end_ms'] - clip['offset_ms']) / 1000:.3f}",
             "-i", str(video), "-vn", "-ac", "1", "-ar", "16000",
             "-c:a", "pcm_s16le", str(wav)],
            check=True, stdout=log, stderr=subprocess.STDOUT,
        )
        command = [whisper, "-m", str(model), "-l", language, "-osrt",
                   "-of", str(prefix), "-f", str(wav), "--no-prints"]
        if vad_model:
            command.extend(["--vad", "-vm", str(vad_model)])
        subprocess.run(command, check=True, stdout=log, stderr=subprocess.STDOUT)

    # 2. Preserve a silent clip as an empty transcript and remove its large WAV.

    if not srt.exists():
        srt.write_text("", encoding="utf-8")
    checked_srt(srt)
    wav.unlink()
    return srt


def prepare_run(args):
    video = args.video.resolve(strict=True)
    model = args.model.resolve(strict=True)
    vad_model = args.vad_model.resolve(strict=True) if args.vad_model else None
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    whisper = shutil.which("whisper-cli")
    if not video.is_file() or not model.is_file() or (vad_model and not vad_model.is_file()):
        raise ValueError("Video and model inputs must be files")
    if not ffmpeg or not ffprobe or not whisper:
        raise RuntimeError("ffmpeg, ffprobe, and whisper-cli must be on PATH")
    if not args.language.isalpha() or not 2 <= len(args.language) <= 8:
        raise ValueError("Use a Whisper source-language code such as tr")
    if args.chunk_seconds < 30 or not 0 < args.overlap_seconds < args.chunk_seconds / 2:
        raise ValueError("Use chunks of at least 30 seconds and a smaller positive overlap")

    duration_ms = video_duration(ffprobe, video)
    run = {
        "video": str(video), "video_sha256": file_hash(video),
        "duration_ms": duration_ms, "language": args.language.lower(),
        "model": str(model), "model_size": model.stat().st_size,
        "model_mtime_ns": model.stat().st_mtime_ns,
        "vad_model": str(vad_model) if vad_model else None,
        "chunk_ms": round(args.chunk_seconds * 1000),
        "overlap_ms": round(args.overlap_seconds * 1000),
    }
    return run, ffmpeg, whisper


def transcribe(args):
    # 1. Bind a resumable output folder to this exact video and settings.

    run, ffmpeg, whisper = prepare_run(args)
    output = args.output.resolve()
    run_path = output / "run.json"
    if output.exists():
        if not run_path.is_file() or json.loads(run_path.read_text(encoding="utf-8")) != run:
            raise ValueError(f"Output belongs to another run or is incomplete: {output}")
    else:
        (output / "clips").mkdir(parents=True)
        run_path.write_text(json.dumps(run, indent=2) + "\n", encoding="utf-8")

    # 2. Save every raw clip SRT and a manifest on the original video timeline.

    clips = []
    ranges = clip_ranges(run["duration_ms"], run["chunk_ms"], run["overlap_ms"])
    for index, clip in enumerate(ranges):
        srt = run_clip(clip, index, output, Path(run["video"]), run["language"],
                       Path(run["model"]), Path(run["vad_model"]) if run["vad_model"] else None,
                       ffmpeg, whisper)
        clips.append({"srt": str(srt), **{key: clip[key] for key in
                      ("offset_ms", "core_start_ms", "core_end_ms")}})
        print(f"clip {index + 1}/{len(ranges)} complete", flush=True)

    manifest = output / "manifest.json"
    manifest.write_text(json.dumps({"video": run["video"],
                                    "language": run["language"], "clips": clips},
                                   indent=2) + "\n", encoding="utf-8")

    # 3. Keep both versions of every boundary phrase in the review draft.

    joined = output / "joined"
    if not joined.exists():
        if len(clips) > 1:
            subprocess.run([sys.executable,
                            str(SCRIPTS / "join-clip-drafts.py"), str(manifest),
                            str(joined)], check=True)
        else:
            joined.mkdir()
            shutil.copy2(clips[0]["srt"], joined / f"draft.{run['language']}.srt")
            (joined / "seam-review.json").write_text(
                json.dumps({"video": run["video"], "video_sha256": run["video_sha256"],
                            "language": run["language"], "seams": []}, indent=2) + "\n",
                encoding="utf-8",
            )

    if not (joined / f"draft.{run['language']}.srt").is_file() or not (joined / "seam-review.json").is_file():
        raise ValueError(f"Joined output is incomplete; inspect it before retrying: {joined}")

    print(json.dumps({"draft": str(joined / f"draft.{run['language']}.srt"),
                      "seam_review": str(joined / "seam-review.json"),
                      "clips": len(clips)}))


def check():
    ranges = clip_ranges(71_000, 30_000, 2_000)
    assert [clip["offset_ms"] for clip in ranges] == [0, 28_000, 58_000]
    assert [clip["core_start_ms"] for clip in ranges] == [0, 30_000, 60_000]
    assert [clip["audio_end_ms"] for clip in ranges] == [32_000, 62_000, 71_000]
    print("check ok")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path, nargs="?")
    parser.add_argument("output", type=Path, nargs="?", help="new or matching resume folder")
    parser.add_argument("--language")
    parser.add_argument("--model", type=Path)
    parser.add_argument("--vad-model", type=Path, help="optional Silero model")
    parser.add_argument("--chunk-seconds", type=float, default=300)
    parser.add_argument("--overlap-seconds", type=float, default=2)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        check()
        return

    if args.video is None or args.output is None or args.language is None or args.model is None:
        parser.error("provide video, output folder, --language, and --model")

    transcribe(args)


if __name__ == "__main__":
    main()
