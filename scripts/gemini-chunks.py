#!/usr/bin/env python3
"""Transcribe overlapping five-minute clips with the tested Gemini configuration."""

import argparse
import json
import re
import runpy
import shutil
import subprocess
import time
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
TRANSCRIBE = runpy.run_path(str(SCRIPTS / "transcribe-video.py"))
JOIN = runpy.run_path(str(SCRIPTS / "join-clip-drafts.py"))
REVIEW = runpy.run_path(str(SCRIPTS / "gemini-audio-review.py"))
HASH = TRANSCRIBE["file_hash"]
SAVE = REVIEW["save_json"]
PROMPT = ('Transcribe all audible Turkish speech and intelligible sung words in this audio verbatim, '
          'in chronological order. Keep repetitions, false starts, and short replies. '
          'Do not translate, summarize, correct grammar, or infer inaudible words. '
          'Write each utterance as MM:SS.sss --> MM:SS.sss | Turkish words, using approximate '
          'times relative to this audio clip. Return only the transcript.')
PATTERN = re.compile(r'(?<!\d)(\d{1,2}:\d{2}(?::\d{2})?[.,]\d{1,3})\s*-->\s*'
                     r'(\d{1,2}:\d{2}(?::\d{2})?[.,]\d{1,3})\s*\|')


def milliseconds(text):
    seconds, fraction = text.replace(',', '.').split('.')
    parts = [int(part) for part in seconds.split(':')]
    if len(parts) not in (2, 3) or any(part >= 60 for part in parts[1:]):
        raise ValueError("Invalid Gemini timestamp")
    total = 0
    for part in parts:
        total = total * 60 + part
    return total * 1000 + int(fraction.ljust(3, '0'))


def parse_transcript(text, duration):
    matches = list(PATTERN.finditer(text))
    if not matches or text[:matches[0].start()].strip():
        raise ValueError("Gemini transcript lacks timestamps or has unparsed leading text")
    cues = []
    for index, match in enumerate(matches):
        end_offset = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        words = ' '.join(text[match.end():end_offset].split())
        start, end = milliseconds(match[1]), milliseconds(match[2])
        if not words or not 0 <= start < end <= duration:
            raise ValueError("Gemini text or timestamp outside clip; inspect saved raw response")
        cues.append({"start_ms": start, "end_ms": end, "text": words})
    return cues


def transcribe(video, output, authorization, apply=False):
    # 1. Freeze the tested profile and exact media; planning makes no upload.
    video = video.resolve(strict=True)
    ffprobe, ffmpeg = shutil.which("ffprobe"), shutil.which("ffmpeg")
    if not ffprobe or not ffmpeg:
        raise RuntimeError("ffprobe and ffmpeg are required")
    duration = TRANSCRIBE["video_duration"](ffprobe, video)
    run = {"video": str(video), "video_sha256": HASH(video), "duration_ms": duration,
           "profile": "gemini-five-minute", "model": "gemini-3.8-flash", "language": "tr",
           "chunk_ms": 300000, "overlap_ms": 5000, "prompt": PROMPT,
           "max_output_tokens": 32768, "model_revision": "provider_unreported"}
    ranges = TRANSCRIBE["clip_ranges"](duration, 300000, 5000)
    if output.exists():
        if not (output / "run.json").is_file() or json.loads((output / "run.json").read_text()) != run:
            raise ValueError("Output belongs to another profile or media; use a new directory")
    else:
        (output / "clips").mkdir(parents=True)
        SAVE(output / "run.json", run)
    if not apply:
        return {"status": "planned", "clips": len(ranges), "settings": run,
                "note": "No upload. --apply requires an approved episode authorization."}
    # Reuse the existing episode budget and deletion/usage accounting.
    selected = [(str(index), output / "run.json",
                 {"video_sha256": run["video_sha256"], "start_ms": clip["offset_ms"],
                  "end_ms": clip["audio_end_ms"]}, None)
                for index, clip in enumerate(ranges)]
    budget = REVIEW["EpisodeBudget"](authorization, run, selected)
    from google import genai
    from google.genai import types
    client = genai.Client(http_options=types.HttpOptions(
        retry_options=types.HttpRetryOptions(attempts=1)))
    clips = []
    for index, clip in enumerate(ranges):
        prefix = output / "clips" / f"{index:03d}"
        receipt_path, srt = prefix.with_suffix(".json"), prefix.with_suffix(".srt")
        clip_duration = clip["audio_end_ms"] - clip["offset_ms"]
        receipt = json.loads(receipt_path.read_text()) if receipt_path.exists() else None
        if receipt:
            if (receipt.get("video_sha256") != run["video_sha256"] or receipt.get("clip") != clip
                    or receipt.get("authorization_sha256") != budget.sha256
                    or receipt.get("status") != "complete"
                    or receipt.get("provider_status") != "completed"
                    or receipt.get("provider_file_deletion") != "deleted"):
                raise ValueError("Prior chunk is incomplete or changed; inspect before retrying")
            if not srt.exists():
                JOIN["write_srt"](srt, parse_transcript(receipt["output_text"], clip_duration))
            if HASH(srt) != receipt["srt_sha256"]:
                raise ValueError("Saved Gemini SRT changed")
        else:
            # 2. Save raw response and delete the remote file even on failure.
            audio = prefix.with_suffix(".wav")
            REVIEW["extract_audio"](video, {"start_ms": clip["offset_ms"],
                                           "end_ms": clip["audio_end_ms"]}, audio)
            receipt = {"status": "attempted", "video_sha256": run["video_sha256"],
                       "clip": clip, "audio_sha256": HASH(audio),
                       "authorization_sha256": budget.sha256, "settings": run}
            SAVE(receipt_path, receipt)
            budget.reserve_upload(output / "run.json", str(index), output / "run.json",
                                  audio, clip_duration)
            uploaded = None
            started = time.monotonic()
            try:
                uploaded = client.files.upload(file=str(audio), config=types.UploadFileConfig(mime_type="audio/wav"))
                receipt["remote_file_name"] = uploaded.name
                SAVE(receipt_path, receipt)
                for attempt in range(25):
                    uploaded = client.files.get(name=uploaded.name)
                    state = getattr(getattr(uploaded, "state", None), "name", None)
                    if state == "ACTIVE":
                        break
                    if state == "FAILED":
                        raise RuntimeError("Gemini file processing failed")
                    time.sleep(5)
                else:
                    raise TimeoutError("Gemini upload did not become active")
                event = budget.reserve_call(output / "run.json", str(index), output / "run.json",
                                            audio, clip_duration, "chunk_transcription",
                                            len(PROMPT.encode()), 32768)
                result = client.interactions.create(
                    model=run["model"], input=[{"type": "text", "text": PROMPT},
                    {"type": "audio", "uri": uploaded.uri, "mime_type": "audio/wav"}],
                    generation_config={"max_output_tokens": 32768})
                receipt.update({"provider_status": REVIEW["interaction_status"](result),
                                "raw_response": result.model_dump(mode="json", exclude_none=True),
                                "output_text": result.output_text or ""})
                receipt["usage"] = result.usage.model_dump(mode="json", exclude_none=True) if result.usage else {}
                budget.record_usage(event, receipt["usage"])
                SAVE(receipt_path, receipt)
                if receipt["provider_status"] != "completed":
                    raise ValueError("Gemini provider response is incomplete")
                JOIN["write_srt"](srt, parse_transcript(receipt["output_text"], clip_duration))
                receipt.update({"status": "complete", "srt_sha256": HASH(srt)})
            finally:
                if uploaded:
                    try:
                        client.files.delete(name=uploaded.name)
                        receipt["provider_file_deletion"] = "deleted"
                    except Exception as error:
                        receipt["provider_file_deletion"] = "failed"
                        receipt["deletion_error_type"] = type(error).__name__
                receipt["elapsed_seconds"] = round(time.monotonic() - started, 3)
                SAVE(receipt_path, receipt)
            if receipt.get("provider_file_deletion") != "deleted":
                raise ValueError("Remote file deletion failed; resolve before continuing")
        clips.append({"srt": str(srt.resolve()), "offset_ms": clip["offset_ms"],
                      "core_start_ms": clip["core_start_ms"], "core_end_ms": clip["core_end_ms"]})
        print(json.dumps({"clip": index, "status": "complete"}), flush=True)
    # 3. Feed the existing join/seam tool, retaining both boundary alternatives.
    manifest = output / "manifest.json"
    SAVE(manifest, {"video": str(video), "language": "tr", "clips": clips})
    joined = output / "joined"
    joined_identity = joined / "manifest.sha256"
    if joined.exists() and (not joined_identity.exists()
                            or joined_identity.read_text().strip() != HASH(manifest)):
        raise ValueError("Joined Gemini output is incomplete or belongs to another manifest")
    if not joined.exists():
        if len(clips) > 1:
            JOIN["join"](manifest, joined, 5000)
        else:
            joined.mkdir()
            shutil.copy2(Path(clips[0]["srt"]), joined / "draft.tr.srt")
            SAVE(joined / "seam-review.json", {"seams": []})
        joined_identity.write_text(HASH(manifest) + "\n")
    if not (joined / "draft.tr.srt").is_file() or not (joined / "seam-review.json").is_file():
        raise ValueError("Joined Gemini output is incomplete; inspect saved clips")
    return {"status": "recognition_complete", "draft": str(joined / "draft.tr.srt"),
            "note": "Provisional words and timing; source and seam review remain."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--authorization", type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if args.apply and not args.authorization:
        parser.error("--apply needs --authorization")
    print(json.dumps(transcribe(args.video, args.output, args.authorization, args.apply)))


if __name__ == "__main__":
    main()
