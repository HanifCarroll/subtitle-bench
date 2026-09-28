"""Validate and normalize saved WhisperX subtitle candidates without rerunning a model."""

import importlib.util
import json
from pathlib import Path


SCRIPT = Path(__file__).with_name("align-episodes.py")
SPEC = importlib.util.spec_from_file_location("align_episodes", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
POLICY = "start shifts >=1 second with 0.5 second lead; retain original cue ends"


def finalize(number: int) -> dict:
    # 1. Load the original subtitles and the saved candidate for this episode.

    report_path = MODULE.OUTPUT / f"{number:03}-report.json"
    report = json.loads(report_path.read_text())
    if report.get("end_policy") == POLICY:
        return report

    videos = list(MODULE.EPISODES.glob(f"{number:03} - *.webm"))
    if len(videos) != 1:
        raise ValueError(f"Expected one video for episode {number:03}")

    video = videos[0]
    basename = video.stem
    source = MODULE.read_srt(video.with_suffix(".tr.srt"))
    english = MODULE.read_srt(video.with_suffix(".en.srt"))
    source_path = MODULE.OUTPUT / f"{basename}.tr.srt"
    english_path = MODULE.OUTPUT / f"{basename}.en.srt"
    candidate_source = MODULE.read_srt(source_path)
    candidate_english = MODULE.read_srt(english_path)
    if not (len(source) == len(english) == len(candidate_source) == len(candidate_english)):
        raise ValueError(f"Cue count changed for episode {number:03}")

    if [cue["text"] for cue in source] != [cue["text"] for cue in candidate_source]:
        raise ValueError(f"Turkish text changed for episode {number:03}")

    if [cue["text"] for cue in english] != [cue["text"] for cue in candidate_english]:
        raise ValueError(f"English text changed for episode {number:03}")

    # 2. Keep only clear start corrections and preserve the full cue duration.

    moved = 0
    rejected_starts = 0
    for original, translated, turkish_cue, english_cue in zip(
        source, english, candidate_source, candidate_english
    ):
        aligned_start = turkish_cue["start"]
        if aligned_start >= original["end"]:
            aligned_start = original["start"]
            rejected_starts += 1

        start = (
            max(original["start"], aligned_start - 0.5)
            if aligned_start - original["start"] >= 1
            else original["start"]
        )
        moved += start != original["start"]
        turkish_cue["start"] = english_cue["start"] = start
        turkish_cue["end"] = english_cue["end"] = original["end"]
        if translated["start"] != original["start"] or translated["end"] != original["end"]:
            raise ValueError(f"Original language timings differ for episode {number:03}")

    # 3. Check the paired result, then update only the candidate files and report.

    if any(cue["start"] >= cue["end"] for cue in candidate_source):
        raise ValueError(f"Invalid candidate interval for episode {number:03}")

    before = MODULE.subtitle_stats(english)
    after = MODULE.subtitle_stats(candidate_english)
    if after["overlaps"] > before["overlaps"]:
        raise ValueError(f"New overlapping cues in episode {number:03}")

    for original, following, candidate, next_candidate in zip(
        source, source[1:], candidate_source, candidate_source[1:]
    ):
        if original["end"] <= following["start"] and candidate["end"] > next_candidate["start"]:
            raise ValueError(f"New overlap after cue {original['id']} in episode {number:03}")

    MODULE.write_srt(source_path, candidate_source)
    MODULE.write_srt(english_path, candidate_english)
    report.pop("moved_at_least_0_2s", None)
    report["moved_at_least_1s"] = moved
    report["rejected_starts_after_original_end"] = rejected_starts
    report["end_policy"] = POLICY
    report["english_before"] = before
    report["english_candidate"] = after
    report["longer_than_7s_before"] = sum(cue["end"] - cue["start"] > 7 for cue in english)
    report["longer_than_7s_candidate"] = sum(
        cue["end"] - cue["start"] > 7.001 for cue in candidate_english
    )
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return report


if __name__ == "__main__":
    reports = sorted(MODULE.OUTPUT.glob("???-report.json"))
    for path in reports:
        number = int(path.name[:3])
        try:
            report = finalize(number)
            print(number, report["english_before"], "->", report["english_candidate"])
        except Exception as error:
            print(f"FAILED {number:03}: {error}")
