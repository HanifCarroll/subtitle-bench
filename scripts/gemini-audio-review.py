#!/usr/bin/env python3
"""Review planned original-video audio clips with Gemini after approval."""

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path


def file_hash(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def save_json(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)


def planned_windows(plan):
    if plan["model"] != "gemini-3.5-transcribe":
        raise ValueError("The plan must use the reviewed transcription model")

    windows = plan["full_chunks"] + plan["focus_clips"]
    duration = int(plan["duration_ms"])
    if len(windows) != int(plan["planned_calls"]) or len(windows) > int(plan["max_calls"]):
        raise ValueError("The plan exceeds its approved call count")

    total_ms = 0
    seen_ids = set()
    for window in windows:
        clip_id = window["id"]
        start = int(window["start_ms"])
        end = int(window["end_ms"])
        if (not re.fullmatch(r"[a-z0-9-]+", clip_id) or clip_id in seen_ids
                or start < 0 or end > duration or start >= end):
            raise ValueError(f"Invalid audio window: {clip_id}")

        seen_ids.add(clip_id)
        total_ms += end - start

    if total_ms != round(float(plan["planned_audio_seconds"]) * 1000):
        raise ValueError("The planned audio duration changed")
    if total_ms > round(float(plan["max_audio_seconds"]) * 1000):
        raise ValueError("The plan exceeds its approved audio duration")

    return windows, total_ms


def extract_audio(video, window, output):
    start = window["start_ms"] / 1000
    seconds = (window["end_ms"] - window["start_ms"]) / 1000
    subprocess.run([
        "ffmpeg", "-y", "-v", "error", "-ss", str(start), "-t", str(seconds),
        "-i", str(video), "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le",
        str(output),
    ], check=True)


def review_clip(client, clip, result_path, plan, window):
    # 1. Save an upload receipt before the billable transcription request.

    record = {
        "video_sha256": plan["video_sha256"],
        "clip": str(clip),
        "clip_sha256": file_hash(clip),
        "start_ms": window["start_ms"],
        "end_ms": window["end_ms"],
        "model": plan["model"],
        "config": {"language_codes": plan["language_codes"], "mode": "verbatim"},
        "status": "uploading",
    }
    save_json(result_path, record)
    uploaded = client.files.upload(file=str(clip))
    record["remote_file_name"] = uploaded.name
    record["status"] = "uploaded"
    save_json(result_path, record)

    # 2. Transcribe the untouched audio, then delete its provider copy.

    try:
        interaction = client.interactions.create(
            model=plan["model"],
            input=[{"type": "audio", "uri": uploaded.uri, "mime_type": uploaded.mime_type}],
            generation_config={"transcription_config": {
                "language_codes": plan["language_codes"],
                "mode": {"type": "verbatim"},
            }},
        )
        record["output_text"] = interaction.output_text
        record["response_id"] = interaction.id
        record["status"] = "transcribed"
        save_json(result_path, record)
    finally:
        client.files.delete(name=uploaded.name)
        record["provider_file_deleted"] = True
        save_json(result_path, record)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("--apply", action="store_true", help="upload audio and make billable calls")
    args = parser.parse_args()

    # 1. Validate the exact video and planned audio budget.

    plan = json.loads(args.plan.read_text())
    video = Path(plan["video"]).resolve(strict=True)
    if file_hash(video) != plan["video_sha256"]:
        raise ValueError("The video differs from the approved plan")

    windows, total_ms = planned_windows(plan)
    print(json.dumps({"calls": len(windows), "audio_minutes": round(total_ms / 60_000, 2),
                      "apply": args.apply}))
    if not args.apply:
        return

    # 2. Run only the planned clips and keep each result separate from subtitles.

    from google import genai

    output_directory = args.plan.parent / "gemini-audio"
    output_directory.mkdir(exist_ok=True)
    client = genai.Client()
    for window in windows:
        clip = output_directory / f"{window['id']}.wav"
        result_path = output_directory / f"{window['id']}.json"
        if result_path.exists():
            result = json.loads(result_path.read_text())
            if (result.get("status") == "transcribed"
                    and result.get("provider_file_deleted") is True
                    and result.get("video_sha256") == plan["video_sha256"]
                    and result.get("start_ms") == window["start_ms"]
                    and result.get("end_ms") == window["end_ms"]
                    and result.get("model") == plan["model"]
                    and clip.is_file() and result.get("clip_sha256") == file_hash(clip)):
                continue

            raise ValueError(f"Review interrupted at {window['id']}; inspect its receipt before retrying")

        extract_audio(video, window, clip)
        review_clip(client, clip, result_path, plan, window)
        print(f"Reviewed {window['id']}", flush=True)


if __name__ == "__main__":
    main()
