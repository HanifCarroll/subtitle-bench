#!/usr/bin/env python3
"""Transcribe one video in overlapping clips for source-language review."""

import argparse
import hashlib
import json
import re
import runpy
import shutil
import subprocess
import sys
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parent
TIMING = runpy.run_path(str(SCRIPTS / "subtitle-timing.py"))
READ_CUES = TIMING["read_cues"]
JOIN = runpy.run_path(str(SCRIPTS / "join-clip-drafts.py"))


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
    # 1. Reuse only a completed, unchanged clip. A partial SRT is not a receipt.

    prefix = output / "clips" / f"{index:03}"
    srt = prefix.with_suffix(".srt")
    receipt = prefix.with_suffix(".complete.json")
    if receipt.exists():
        saved = json.loads(receipt.read_text(encoding="utf-8"))
        if not srt.exists() or saved.get("srt_sha256") != file_hash(srt):
            raise ValueError(f"Completed clip changed: {srt}")
        checked_srt(srt)
        return srt
    srt.unlink(missing_ok=True)

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
    timing_fixes = []
    if srt.stat().st_size:
        text = srt.read_text(encoding="utf-8-sig")
        for match in list(re.finditer(r"^(\d\d:\d\d:\d\d,\d{3}) --> (\d\d:\d\d:\d\d,\d{3})$", text, re.M)):
            start, end = TIMING["milliseconds"](match[1]), TIMING["milliseconds"](match[2])
            if end <= start:
                if not timing_fixes:
                    shutil.copy2(srt, prefix.with_suffix(".raw.srt"))
                timing_fixes.append({"start_ms": start, "raw_end_ms": end, "end_ms": start + 1})
                text = text.replace(match[0], match[1] + " --> " + JOIN["timestamp"](start + 1), 1)
        if timing_fixes:
            srt.write_text(text, encoding="utf-8")
    checked_srt(srt)
    receipt.write_text(json.dumps({
        "index": index, "clip": clip, "srt_sha256": file_hash(srt),
        "empty_transcript": srt.stat().st_size == 0, "provisional_timing_fixes": timing_fixes,
        "raw_srt_sha256": file_hash(prefix.with_suffix(".raw.srt")) if timing_fixes else None,
    }, indent=2) + "\n", encoding="utf-8")
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
        "profile": getattr(args, "profile", None) or "custom-whisper",
        "process_isolation": "one whisper-cli process per clip",
        "duration_ms": duration_ms, "language": args.language.lower(),
        "model": str(model), "model_size": model.stat().st_size,
        "model_mtime_ns": model.stat().st_mtime_ns,
        "model_sha256": file_hash(model),
        "vad_model": str(vad_model) if vad_model else None,
        "vad_model_sha256": file_hash(vad_model) if vad_model else None,
        "chunk_ms": round(args.chunk_seconds * 1000),
        "overlap_ms": round(args.overlap_seconds * 1000),
    }
    return run, ffmpeg, whisper


def transcribe(args):
    profile = getattr(args, "profile", None)
    if profile == "gemini-five-minute":
        if (args.model or args.vad_model or args.language not in (None, "tr")
                or args.chunk_seconds != 300 or args.overlap_seconds != 5):
            raise ValueError("Gemini profile fixes Turkish, 300-second cores and 5-second overlap")
        if args.apply and not args.authorization:
            raise ValueError("Gemini execution requires an approved authorization")
        gemini = runpy.run_path(str(SCRIPTS / "gemini-chunks.py"))
        result = gemini["transcribe"](args.video, args.output, args.authorization, args.apply)
        print(json.dumps(result))
        return result
    if profile == "whisper-turbo":
        args.model = args.model or Path.home() / ".local/share/transcribe-audio/models/ggml-large-v3-turbo.bin"
        if (args.model.name != "ggml-large-v3-turbo.bin" or args.vad_model
                or args.chunk_seconds != 300 or args.overlap_seconds != 5):
            raise ValueError("Whisper turbo requires isolated 300-second cores, 5-second overlap, no VAD")
        args.language = args.language or "tr"
    return transcribe_whisper(args)


def transcribe_whisper(args):
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
    manifest_sha256 = file_hash(manifest)

    # 3. Keep both versions of every boundary phrase in the review draft.

    joined = output / "joined"
    joined_receipt = joined / "manifest.sha256"
    if joined.exists() and (not joined_receipt.exists()
                            or joined_receipt.read_text().strip() != manifest_sha256):
        raise ValueError(f"Joined output is stale or unbound; preserve it and use a new run: {joined}")
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
        joined_receipt.write_text(manifest_sha256 + "\n", encoding="utf-8")

    if not (joined / f"draft.{run['language']}.srt").is_file() or not (joined / "seam-review.json").is_file():
        raise ValueError(f"Joined output is incomplete; inspect it before retrying: {joined}")

    print(json.dumps({"draft": str(joined / f"draft.{run['language']}.srt"),
                      "seam_review": str(joined / "seam-review.json"),
                      "clips": len(clips),
                      "empty_clip_indices": [i for i in range(len(clips)) if json.loads(
                          (output / "clips" / f"{i:03}.complete.json").read_text()
                      )["empty_transcript"]]}))


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
    parser.add_argument("--overlap-seconds", type=float, default=5)
    parser.add_argument("--profile", choices=("whisper-turbo", "gemini-five-minute"))
    parser.add_argument("--authorization", type=Path)
    parser.add_argument("--apply", action="store_true", help="authorize Gemini execution from the supplied receipt")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        check()
        return

    if args.video is None or args.output is None:
        parser.error("provide video and output folder")
    if args.profile is None and (args.language is None or args.model is None):
        parser.error("provide --profile or --language and --model")

    transcribe(args)


if __name__ == "__main__":
    main()
