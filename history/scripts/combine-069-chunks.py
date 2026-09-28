#!/usr/bin/env python3
"""Join overlapping episode 69 Whisper clips into one reviewable Turkish SRT."""

from collections import Counter
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PILOT = ROOT / "Workflow" / "pilots" / "english-reading"
CHUNKS = PILOT / "069-large-v3-chunks"
OUTPUT = PILOT / "069-large-v3-chunked.tr.srt"
REPORT = PILOT / "069-large-v3-chunked-report.json"
TIME = re.compile(r"(\d{2}):(\d{2}):(\d{2}),(\d{3})")


def milliseconds(value):
    match = TIME.fullmatch(value)
    if match is None:
        raise ValueError(f"Bad SRT time: {value}")

    hours, minutes, seconds, millis = map(int, match.groups())
    return ((hours * 60 + minutes) * 60 + seconds) * 1000 + millis


def srt_time(value):
    hours, remainder = divmod(value, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, millis = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{seconds:02},{millis:03}"


def select_chunk_cue(start, end, chunk):
    midpoint = (start + end) // 2
    return chunk * 300_000 <= midpoint < (chunk + 1) * 300_000


def read_srt(path):
    cues = []
    for block in re.split(r"\n\s*\n", path.read_text().strip()):
        lines = block.splitlines()
        if len(lines) < 3 or " --> " not in lines[1]:
            raise ValueError(f"Bad SRT cue in {path}")

        start, end = lines[1].split(" --> ")
        text = "\n".join(line.strip() for line in lines[2:]).strip()
        if not text:
            raise ValueError(f"Empty SRT cue in {path}")

        cues.append((milliseconds(start), milliseconds(end), text))

    return cues


def check():
    assert milliseconds("00:05:00,123") == 300123
    assert srt_time(300123) == "00:05:00,123"
    assert select_chunk_cue(299000, 299500, 0)
    assert not select_chunk_cue(299000, 301500, 0)
    assert select_chunk_cue(299000, 301500, 1)
    print("check ok")


def main():
    if sys.argv[1:] == ["--check"]:
        check()
        return

    # 1. Shift each clip onto the episode timeline and keep its center region.

    combined = []
    for chunk in range(18):
        path = CHUNKS / f"{chunk:02}.srt"
        begin = max(0, chunk * 300 - 2) * 1000
        for relative_start, relative_end, text in read_srt(path):
            start = begin + relative_start
            end = begin + relative_end
            if start >= end:
                raise ValueError(f"Invalid cue in {path}")

            if select_chunk_cue(start, end, chunk):
                combined.append((start, end, text))

    combined.sort(key=lambda cue: (cue[0], cue[1]))

    # 2. Write sequential cues and report repetition and overlap risks.

    blocks = [
        f"{number}\n{srt_time(start)} --> {srt_time(end)}\n{text}"
        for number, (start, end, text) in enumerate(combined, 1)
    ]
    OUTPUT.write_text("\n\n".join(blocks) + "\n")
    top_phrase, count = Counter(text for _, _, text in combined).most_common(1)[0]
    report = {
        "cues": len(combined),
        "overlaps": sum(first[1] > second[0] for first, second in zip(combined, combined[1:])),
        "top_phrase": top_phrase,
        "top_phrase_count": count,
        "under_1s": sum(end - start < 1000 for start, end, _ in combined),
    }
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
