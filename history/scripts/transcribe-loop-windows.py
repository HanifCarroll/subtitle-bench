#!/usr/bin/env python3
"""Replace long Whisper repetition loops in reviewable Turkish candidates."""

import argparse
import json
import runpy
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EPISODES = ROOT / "Episodes"
OUTPUT = ROOT / "Workflow" / "pilots" / "loop-repair"
AUDIT = ROOT / "Workflow" / "pilots" / "english-reading" / "source-repetition-runs.json"
MODEL = Path.home() / ".local/share/transcribe-audio/models/ggml-large-v3.bin"
VAD = Path.home() / ".local/share/transcribe-audio/models/ggml-silero-v6.2.0.bin"
FFMPEG = "/opt/homebrew/bin/ffmpeg"
WHISPER = "/opt/homebrew/bin/whisper-cli"

srt = runpy.run_path(str(Path(__file__).with_name("light-pass.py")))
parse_srt, write_srt = srt["parse_srt"], srt["write_srt"]


def milliseconds(value):
    hours, minutes, rest = value.replace(",", ".").split(":")
    return round((int(hours) * 3600 + int(minutes) * 60 + float(rest)) * 1000)


def srt_time(value):
    hours, remainder = divmod(value, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, millis = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{seconds:02},{millis:03}"


def timed_cues(path):
    cues = []
    for cue in parse_srt(path.read_text()):
        start, end = map(milliseconds, cue["time"].split(" --> "))
        if start >= end or not cue["text"].strip():
            raise ValueError(f"Invalid cue in {path}: {cue['id']}")

        cues.append((start, end, cue["text"].strip()))

    return cues


def longest_repeat(cues):
    longest = current = 1
    for first, second in zip(cues, cues[1:]):
        current = current + 1 if first[2] == second[2] else 1
        longest = max(longest, current)

    return longest


def chunks_for_runs(runs):
    return sorted({
        chunk
        for run in runs if run["cues"] >= 100
        for chunk in range(int(run["start_seconds"] // 300), int(run["end_seconds"] // 300) + 1)
    })


def keep_chunk_cue(start, end, chunk):
    left = chunk * 300_000
    right = (chunk + 1) * 300_000
    midpoint = (start + end) // 2
    return left <= midpoint < right or start < left < end or start < right < end


def transcribe_chunk(video, folder, chunk):
    prefix = folder / f"{chunk:02}"
    transcript = prefix.with_suffix(".srt")
    if transcript.exists() and transcript.stat().st_size:
        timed_cues(transcript)
        return

    # 1. Extract a five-minute clip with two seconds of boundary context.

    wav = prefix.with_suffix(".wav")
    begin = max(0, chunk * 300 - 2)
    try:
        subprocess.run([
            FFMPEG, "-y", "-ss", str(begin), "-t", "304", "-i", str(video),
            "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le",
            str(wav), "-hide_banner", "-loglevel", "error",
        ], check=True)

        # 2. Keep model output and diagnostics outside the installed episode.

        with prefix.with_suffix(".log").open("w") as log:
            subprocess.run([
                WHISPER, "-m", str(MODEL), "-l", "tr", "--vad", "-vm", str(VAD),
                "-osrt", "-of", str(prefix), "-f", str(wav), "--no-prints",
            ], stdout=log, stderr=subprocess.STDOUT, check=True)

        timed_cues(transcript)
    finally:
        wav.unlink(missing_ok=True)


def process_episode(row):
    number = row["episode"]
    video = next(EPISODES.glob(f"{number:03}*.webm"))
    source = video.with_suffix(".tr.srt")
    original = timed_cues(source)
    if longest_repeat(original) < 100:
        print(f"episode {number:03}: installed source already repaired", flush=True)
        return

    chunks = chunks_for_runs(row["runs"])
    if not chunks:
        return

    folder = OUTPUT / f"{number:03}"
    folder.mkdir(parents=True, exist_ok=True)
    print(f"episode {number:03}: {len(chunks)} chunks", flush=True)
    for chunk in chunks:
        transcribe_chunk(video, folder, chunk)
        print(f"episode {number:03}: chunk {chunk:02} done", flush=True)

    # 3. Keep boundary-spanning cues from both clips so a split sentence is not lost.

    selected = set(chunks)
    combined = [cue for cue in original if ((cue[0] + cue[1]) // 2) // 300_000 not in selected]
    for chunk in chunks:
        offset = max(0, chunk * 300 - 2) * 1000
        for start, end, text in timed_cues(folder / f"{chunk:02}.srt"):
            shifted = (offset + start, offset + end, text)
            if keep_chunk_cue(shifted[0], shifted[1], chunk):
                combined.append(shifted)

    combined.sort(key=lambda cue: (cue[0], cue[1]))
    candidate = folder / f"{number:03}.candidate.tr.srt"
    write_srt([
        {"id": index, "time": f"{srt_time(start)} --> {srt_time(end)}", "text": text}
        for index, (start, end, text) in enumerate(combined, 1)
    ], candidate)
    report = {
        "episode": number,
        "chunks": chunks,
        "original_cues": len(original),
        "candidate_cues": len(combined),
        "original_longest_repeat": longest_repeat(original),
        "candidate_longest_repeat": longest_repeat(combined),
        "candidate_overlaps": sum(first[1] > second[0] for first, second in zip(combined, combined[1:])),
    }
    (folder / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("episode", nargs="?", type=int)
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        assert milliseconds("00:05:00,123") == 300123
        assert srt_time(300123) == "00:05:00,123"
        assert chunks_for_runs([{"cues": 100, "start_seconds": 299, "end_seconds": 601}]) == [0, 1, 2]
        assert keep_chunk_cue(4_798_420, 4_801_220, 16)
        assert not keep_chunk_cue(4_796_000, 4_797_000, 16)
        assert longest_repeat([(0, 1, "a"), (1, 2, "a"), (2, 3, "b")]) == 2
        print("check ok")
        return

    if args.all == (args.episode is not None):
        parser.error("choose one episode or --all")

    rows = json.loads(AUDIT.read_text())["episodes"]
    if args.episode is not None:
        process_episode(next(row for row in rows if row["episode"] == args.episode))
        return

    priority = sorted(rows, key=lambda row: -sum(
        run["duration_minutes"] for run in row["runs"] if run["cues"] >= 100
    ))
    for row in priority:
        if any(run["cues"] >= 100 for run in row["runs"]):
            process_episode(row)


if __name__ == "__main__":
    main()
