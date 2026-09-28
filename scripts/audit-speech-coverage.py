#!/usr/bin/env python3
"""List VAD-detected speech without a subtitle cue; every result needs audio review."""

import argparse
import json
import os
import re
import runpy
import subprocess
import tempfile
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parent
read_cues = runpy.run_path(str(SCRIPTS / "subtitle-timing.py"))["read_cues"]
VAD_MODEL = Path(os.environ.get(
    "SUBTITLE_VAD_MODEL",
    Path.home() / ".local/share/transcribe-audio/models/ggml-silero-v6.2.0.bin",
))
SEGMENT = re.compile(r"Speech segment \d+: start = ([\d.]+), end = ([\d.]+)")


def duration_seconds(video):
    result = subprocess.run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(video),
    ], check=True, capture_output=True, text=True)
    return float(result.stdout.strip())


def vad_intervals(video, duration):
    # 1. Scan overlapping five-minute clips so speech crossing a cut is retained.

    intervals = []
    with tempfile.TemporaryDirectory(prefix="subtitle-vad-") as directory:
        audio = Path(directory) / "audio.wav"
        for chunk in range(int(duration // 300) + 1):
            begin = max(0, chunk * 300 - 2)
            if begin >= duration:
                break

            subprocess.run([
                "ffmpeg", "-y", "-ss", str(begin), "-t", "304",
                "-i", str(video), "-vn", "-ac", "1", "-ar", "16000",
                "-c:a", "pcm_s16le", str(audio), "-hide_banner", "-loglevel", "error",
            ], check=True, capture_output=True)
            result = subprocess.run([
                "whisper-vad-speech-segments", "-vm", str(VAD_MODEL),
                "-f", str(audio), "-np",
            ], check=True, capture_output=True, text=True)
            for start, end in SEGMENT.findall(result.stdout + result.stderr):
                intervals.append((begin + float(start) / 100, begin + float(end) / 100))

            audio.unlink()
            print(f"chunk {chunk:02} checked", flush=True)

    # 2. Merge the overlapping copies of each speech interval.

    merged = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))

    return merged


def uncovered_speech(speech, cues, tolerance=0.15, minimum=0.7):
    # 1. Subtract subtitle coverage, allowing a little timestamp imprecision.

    coverage = [(max(0, cue["start"] / 1000 - tolerance), cue["end"] / 1000 + tolerance)
                for cue in cues]
    uncovered = []
    for speech_start, speech_end in speech:
        cursor = speech_start
        for cue_start, cue_end in coverage:
            if cue_end <= cursor:
                continue
            if cue_start >= speech_end:
                break
            if cue_start - cursor >= minimum:
                uncovered.append((cursor, min(cue_start, speech_end)))
            cursor = max(cursor, min(cue_end, speech_end))
            if cursor >= speech_end:
                break

        if speech_end - cursor >= minimum:
            uncovered.append((cursor, speech_end))

    return uncovered


def subtitle_without_speech(speech, cues, tolerance=0.25, minimum=3.0):
    """Flag long parts of a cue with no detected voice; never change cue timing."""
    flagged = []

    # 1. Subtract detected speech from each subtitle, allowing small timing differences.

    for cue in cues:
        if re.fullmatch(r"\s*(?:\[[^\]]+\]\s*)+", cue["text"]):
            continue

        cue_start, cue_end = cue["start"] / 1000, cue["end"] / 1000
        covered = []
        for speech_start, speech_end in speech:
            start = max(cue_start, speech_start - tolerance)
            end = min(cue_end, speech_end + tolerance)
            if end > start:
                covered.append((start, end))

        cursor = cue_start
        for start, end in covered:
            if start - cursor >= minimum:
                flagged.append({
                    "cue_id": cue["id"], "start_seconds": round(cursor, 3),
                    "end_seconds": round(start, 3),
                    "duration_seconds": round(start - cursor, 3),
                    "position": "before" if cursor == cue_start else "within",
                    "cue_text": cue["text"],
                })
            cursor = max(cursor, end)

        if cue_end - cursor >= minimum:
            flagged.append({
                "cue_id": cue["id"], "start_seconds": round(cursor, 3),
                "end_seconds": round(cue_end, 3),
                "duration_seconds": round(cue_end - cursor, 3),
                "position": "entire" if not covered else "after",
                "cue_text": cue["text"],
            })

    return flagged


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", nargs="?", type=Path)
    parser.add_argument("srt", nargs="?", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    if args.check:
        cues = [{"start": 2000, "end": 4000}, {"start": 6000, "end": 8000}]
        assert uncovered_speech([(0, 10)], cues, tolerance=0, minimum=0.7) == [
            (0, 2), (4, 6), (8, 10)
        ]
        lingering = subtitle_without_speech(
            [(2, 3), (9, 10)], [{"id": 1, "start": 0, "end": 10_000,
                                 "text": "Remember."}]
        )
        assert len(lingering) == 1 and lingering[0]["position"] == "within"
        assert lingering[0]["duration_seconds"] == 5.5
        assert not subtitle_without_speech(
            [], [{"id": 2, "start": 0, "end": 8_000, "text": "[Singing]"}]
        )
        print("check ok")
        return

    if not args.video or not args.srt or not args.output:
        parser.error("provide VIDEO SRT --output REPORT.json")

    cues = read_cues(args.srt)
    duration = duration_seconds(args.video)
    speech = vad_intervals(args.video, duration)
    gaps = uncovered_speech(speech, cues)
    nonspeech = subtitle_without_speech(speech, cues)
    report = {
        "video": str(args.video), "srt": str(args.srt),
        "duration_seconds": round(duration, 3),
        "vad_speech_intervals": len(speech),
        "uncovered_intervals": len(gaps),
        "possible_subtitle_without_speech_count": len(nonspeech),
        "possible_subtitle_without_speech": nonspeech,
        "note": "Both directions are review prompts. VAD may mistake music/noise for speech or miss quiet words. Check original audio before editing.",
        "items": [
            {"start_seconds": round(start, 3), "end_seconds": round(end, 3),
             "duration_seconds": round(end - start, 3)}
            for start, end in gaps
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({key: value for key, value in report.items() if key != "items"}))


if __name__ == "__main__":
    main()
