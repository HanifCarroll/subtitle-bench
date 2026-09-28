"""Validate every aligned subtitle pair and optionally install it beside its video."""

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
from pathlib import Path


SCRIPT = Path(__file__).with_name("align-episodes.py")
SPEC = importlib.util.spec_from_file_location("align_episodes", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

REPAIR = MODULE.OUTPUT.parent / "episode-071-repair"
BACKUP = MODULE.ROOT / "Workflow" / "pre-alignment-2026-09-25"
POLICY = "start shifts >=1 second with 0.5 second lead; reading time up to 7 seconds"


def checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate() -> tuple[list[tuple[Path, Path]], dict]:
    # 1. Require a finished, normalized candidate for every video.

    videos = sorted(MODULE.EPISODES.glob("*.webm"))
    if len(videos) != 104 or [int(video.name[:3]) for video in videos] != list(range(1, 105)):
        raise ValueError("Expected exactly episodes 001 through 104")

    replacements = []
    totals = {"episodes": 0, "cues_before": 0, "cues_after": 0,
              "under_1s_before": 0, "under_1s_after": 0,
              "over_20_chars_per_s_before": 0, "over_20_chars_per_s_after": 0,
              "overlaps_before": 0, "overlaps_after": 0,
              "moved_at_least_1s": 0, "alignment_flags": 0}
    for video in videos:
        number = int(video.name[:3])
        report_path = MODULE.OUTPUT / f"{number:03}-report.json"
        report = json.loads(report_path.read_text())
        if report.get("end_policy") != POLICY:
            raise ValueError(f"Episode {number:03} has not been finalized")

        directory = REPAIR if number == 71 else MODULE.OUTPUT
        original_turkish = video.with_suffix(".tr.srt")
        original_english = video.with_suffix(".en.srt")
        candidate_turkish = directory / f"{video.stem}.tr.srt"
        candidate_english = directory / f"{video.stem}.en.srt"
        original = MODULE.read_srt(original_turkish)
        original_en = MODULE.read_srt(original_english)
        candidate = MODULE.read_srt(candidate_turkish)
        candidate_en = MODULE.read_srt(candidate_english)

        # 2. Check IDs, paired timings, text preservation, and cue boundaries.

        if len(original) != len(original_en) or len(candidate) != len(candidate_en):
            raise ValueError(f"Episode {number:03} language cue counts differ")

        if any(
            tr["start"] != en["start"] or tr["end"] != en["end"]
            for tr, en in zip(candidate, candidate_en)
        ):
            raise ValueError(f"Episode {number:03} language timings differ")

        if any(cue["start"] < 0 or cue["start"] >= cue["end"] for cue in candidate):
            raise ValueError(f"Episode {number:03} has invalid cue intervals")

        if number != 71:
            if len(original) != len(candidate):
                raise ValueError(f"Episode {number:03} changed cue count")

            if any(first["text"] != second["text"] for first, second in zip(original, candidate)):
                raise ValueError(f"Episode {number:03} changed Turkish text")

            if any(first["text"] != second["text"] for first, second in zip(original_en, candidate_en)):
                raise ValueError(f"Episode {number:03} changed English text")

        before = MODULE.subtitle_stats(original_en)
        after = MODULE.subtitle_stats(candidate_en)
        if after["overlaps"] > before["overlaps"]:
            raise ValueError(f"Episode {number:03} gained overlaps")

        totals["episodes"] += 1
        totals["cues_before"] += len(original)
        totals["cues_after"] += len(candidate)
        totals["under_1s_before"] += before["under_1s"]
        totals["under_1s_after"] += after["under_1s"]
        totals["over_20_chars_per_s_before"] += before["over_20_chars_per_s"]
        totals["over_20_chars_per_s_after"] += after["over_20_chars_per_s"]
        totals["overlaps_before"] += before["overlaps"]
        totals["overlaps_after"] += after["overlaps"]
        totals["moved_at_least_1s"] += report["moved_at_least_1s"]
        totals["alignment_flags"] += len(report["flagged"])
        replacements.extend([(original_turkish, candidate_turkish),
                             (original_english, candidate_english)])

    return replacements, totals


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="back up and install validated subtitles")
    arguments = parser.parse_args()
    replacements, totals = validate()
    print(json.dumps(totals, indent=2))
    if not arguments.apply:
        return

    # 3. Preserve exact originals before replacing any sidecar.

    if BACKUP.exists():
        raise FileExistsError(f"Backup already exists: {BACKUP}")

    BACKUP.mkdir(parents=True)
    manifest = {}
    for original, candidate in replacements:
        shutil.copy2(original, BACKUP / original.name)
        manifest[original.name] = {"sha256": checksum(original), "candidate": str(candidate)}

    (BACKUP / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    if len(list(BACKUP.glob("*.srt"))) != 208:
        raise ValueError("Original subtitle backup is incomplete")

    if any(
        checksum(BACKUP / name) != record["sha256"]
        for name, record in manifest.items()
    ):
        raise ValueError("Original subtitle backup failed checksum verification")

    # 4. Install each fully validated candidate beside its video.

    for original, candidate in replacements:
        staged = original.with_name(original.name + ".new")
        shutil.copy2(candidate, staged)
        os.replace(staged, original)

    print(f"Installed 208 subtitle files; original copies: {BACKUP}")


if __name__ == "__main__":
    main()
