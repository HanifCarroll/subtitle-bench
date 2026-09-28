"""Create reviewable Turkish and English subtitle timing candidates with WhisperX."""

import argparse
import json
import math
import re
import time
from pathlib import Path

from whisperx.alignment import align, load_align_model


ROOT = Path(__file__).resolve().parents[2]
EPISODES = ROOT / "Episodes"
OUTPUT = ROOT / "Workflow" / "pilots" / "whisperx-candidates"
TIME_PATTERN = re.compile(r"(\d{2}):(\d{2}):(\d{2}),(\d{3})")


def seconds(value: str) -> float:
    match = TIME_PATTERN.fullmatch(value)
    if match is None:
        raise ValueError(f"Invalid SRT time: {value}")

    hours, minutes, seconds_part, milliseconds = map(int, match.groups())
    return hours * 3600 + minutes * 60 + seconds_part + milliseconds / 1000


def srt_time(value: float) -> str:
    total_milliseconds = round(value * 1000)
    hours, remainder = divmod(total_milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds_part, milliseconds = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{seconds_part:02},{milliseconds:03}"


def read_srt(path: Path) -> list[dict]:
    cues = []
    for block in re.split(r"\n\s*\n", path.read_text().strip()):
        lines = block.splitlines()
        if len(lines) < 3 or " --> " not in lines[1]:
            raise ValueError(f"Malformed SRT cue in {path}: {block[:80]}")

        start_text, end_text = lines[1].split(" --> ", 1)
        cues.append({
            "id": int(lines[0]),
            "start": seconds(start_text),
            "end": seconds(end_text),
            "text": "\n".join(lines[2:]),
        })

    if [cue["id"] for cue in cues] != list(range(1, len(cues) + 1)):
        raise ValueError(f"Nonsequential cue numbers in {path}")

    return cues


def write_srt(path: Path, cues: list[dict]) -> None:
    blocks = []
    for cue in cues:
        blocks.append(
            f"{cue['id']}\n{srt_time(cue['start'])} --> {srt_time(cue['end'])}\n{cue['text']}"
        )

    path.write_text("\n\n".join(blocks) + "\n")


def alignment_text(text: str) -> str:
    words_only = re.sub(r"[^\w\s]", " ", text)
    return " ".join(words_only.split())


def subtitle_stats(cues: list[dict]) -> dict:
    short = 0
    fast = 0
    for cue in cues:
        duration = cue["end"] - cue["start"]
        if duration < 1:
            short += 1
        if duration > 0 and len(cue["text"].replace("\n", " ")) / duration > 20:
            fast += 1

    overlaps = sum(first["end"] > second["start"] for first, second in zip(cues, cues[1:]))
    return {"under_1s": short, "over_20_chars_per_s": fast, "overlaps": overlaps}


def process_episode(number: int, model: object, metadata: dict) -> dict:
    # 1. Match the video and both subtitle languages by episode number.

    videos = list(EPISODES.glob(f"{number:03} - *.webm"))
    if len(videos) != 1:
        raise ValueError(f"Expected one video for episode {number:03}, found {len(videos)}")

    video = videos[0]
    source_path = video.with_suffix(".tr.srt")
    english_path = video.with_suffix(".en.srt")
    source = read_srt(source_path)
    english = read_srt(english_path)
    if len(source) != len(english):
        raise ValueError(f"Subtitle cue counts differ for episode {number:03}")

    if any(
        first["start"] != second["start"] or first["end"] != second["end"]
        for first, second in zip(source, english)
    ):
        raise ValueError(f"Subtitle timings already differ for episode {number:03}")

    # 2. Align the existing Turkish cues to the full episode audio.

    started = time.monotonic()
    aligned = align(
        [
            {"start": cue["start"], "end": cue["end"], "text": alignment_text(cue["text"])}
            for cue in source
        ],
        model,
        metadata,
        str(video),
        device="cpu",
    )["segments"]
    if len(aligned) != len(source):
        raise ValueError(f"Alignment changed cue count for episode {number:03}")

    # 3. Apply valid aligned starts to both languages, preserving every word.

    candidate_source = []
    candidate_english = []
    flagged = []
    moved = 0
    for turkish_cue, english_cue, result in zip(source, english, aligned):
        start = result.get("start")
        end = result.get("end")
        has_timed_word = any(
            "start" in word and "end" in word for word in result.get("words", [])
        )
        valid = (
            has_timed_word
            and isinstance(start, (int, float))
            and isinstance(end, (int, float))
            and math.isfinite(start)
            and math.isfinite(end)
            and 0 <= start < end
        )
        if not valid:
            start, end = turkish_cue["start"], turkish_cue["end"]
            flagged.append({"id": turkish_cue["id"], "reason": "no_valid_alignment"})
        else:
            shift = start - turkish_cue["start"]
            if abs(shift) >= 5:
                flagged.append({"id": turkish_cue["id"], "reason": "start_shift", "seconds": round(shift, 2)})
            if abs(shift) < 1:
                start = turkish_cue["start"]

            end = turkish_cue["end"]

        if start >= end:
            flagged.append({"id": turkish_cue["id"], "reason": "aligned_start_after_original_end"})
            start = turkish_cue["start"]

        moved += start != turkish_cue["start"]

        candidate_source.append({**turkish_cue, "start": start, "end": end})
        candidate_english.append({**english_cue, "start": start, "end": end})

    # 4. Save candidates separately and record timing risks for review.

    OUTPUT.mkdir(parents=True, exist_ok=True)
    prefix = OUTPUT / video.stem
    write_srt(Path(f"{prefix}.tr.srt"), candidate_source)
    write_srt(Path(f"{prefix}.en.srt"), candidate_english)
    report = {
        "episode": number,
        "cues": len(source),
        "moved_at_least_1s": moved,
        "flagged": flagged,
        "end_policy": "apply starts shifted at least 1 second; retain original cue ends",
        "english_before": subtitle_stats(english),
        "english_candidate": subtitle_stats(candidate_english),
        "elapsed_seconds": round(time.monotonic() - started, 1),
    }
    (OUTPUT / f"{number:03}-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("episode", type=int, nargs="*")
    parser.add_argument("--all", action="store_true", help="process episodes 1 through 104")
    parser.add_argument("--force", action="store_true", help="rerun completed candidates")
    arguments = parser.parse_args()
    numbers = list(range(1, 105)) if arguments.all else arguments.episode
    if not numbers:
        parser.error("Choose episode numbers or --all")

    model, metadata = load_align_model(language_code="tr", device="cpu")
    for number in numbers:
        report_path = OUTPUT / f"{number:03}-report.json"
        if report_path.exists() and not arguments.force:
            print(f"SKIP {number:03}: candidate already exists", flush=True)
            continue

        try:
            report = process_episode(number, model, metadata)
            summary = {key: value for key, value in report.items() if key != "flagged"}
            print(json.dumps(summary), flush=True)
        except Exception as error:
            OUTPUT.mkdir(parents=True, exist_ok=True)
            (OUTPUT / f"{number:03}-error.txt").write_text(f"{type(error).__name__}: {error}\n")
            print(f"FAILED {number:03}: {error}", flush=True)


if __name__ == "__main__":
    main()
