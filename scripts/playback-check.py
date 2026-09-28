#!/usr/bin/env python3
"""Render both subtitle tracks at representative video times without opening a player."""

import argparse
import hashlib
import json
import re
import runpy
import shutil
import subprocess
import tempfile
from pathlib import Path


read_cues = runpy.run_path(str(Path(__file__).with_name("subtitle-timing.py")))["read_cues"]
ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as content:
        for block in iter(lambda: content.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def duration_ms(video):
    process = subprocess.run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=nokey=1:noprint_wrappers=1", str(video),
    ], check=True, capture_output=True, text=True)
    return round(float(process.stdout.strip()) * 1000)


def active_cue(cues, at_ms):
    return next((cue for cue in cues if cue["start"] <= at_ms < cue["end"]), None)


def sample_times(source_cues, extra):
    chosen = {}
    for label, fraction in (("early", 0.1), ("middle", 0.5), ("late", 0.9)):
        cue = source_cues[round((len(source_cues) - 1) * fraction)]
        chosen[label] = (cue["start"] + cue["end"]) // 2
    for index, at_ms in enumerate(extra, 1):
        chosen[f"repair-{index}"] = at_ms
    return chosen


def render(video, subtitle, at_ms, output):
    filters = ["subtitles=sub.srt"] if subtitle else []
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
               "-copyts", "-ss", f"{at_ms / 1000:.3f}", "-i", str(video)]
    if filters:
        command += ["-vf", ",".join(filters)]
    command += ["-frames:v", "1", str(output)]
    subprocess.run(command, cwd=subtitle.parent if subtitle else None,
                   check=True, capture_output=True)


def subtitle_difference(baseline, rendered):
    """Measure visible bottom-third pixels changed by libass rendering."""
    process = subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "info", "-i", str(baseline),
        "-i", str(rendered), "-filter_complex",
        "[0:v][1:v]blend=all_mode=difference,"
        "crop=iw:ih/3:0:2*ih/3,signalstats,metadata=print",
        "-frames:v", "1", "-f", "null", "-",
    ], check=True, capture_output=True, text=True)
    match = re.search(r"lavfi\.signalstats\.YAVG=([0-9.]+)", process.stderr)
    if not match:
        raise ValueError("FFmpeg did not report rendered pixel difference")
    return float(match.group(1))


def check(video, source, target, output, extra):
    """Save rendered frames and flag missing visible text for active cues."""

    # 1. Keep original media and subtitle sidecars outside the rendering directory.

    video = video.resolve(strict=True)
    source = source.resolve(strict=True)
    target = target.resolve(strict=True)
    output = output.resolve()
    if (source == target or output == ROOT or ROOT in output.parents
            or output in (video.parent, source.parent, target.parent)):
        raise ValueError("Use separate tracks and a private output directory")
    source_cues = read_cues(source)
    target_cues = read_cues(target)
    duration = duration_ms(video)
    times = sample_times(source_cues, extra)
    if any(not 0 <= at_ms < duration for at_ms in times.values()):
        raise ValueError("Playback sample is outside the video")
    output.mkdir(parents=True, exist_ok=True)

    # 2. Render the same frame without and with each subtitle track.

    samples = []
    with tempfile.TemporaryDirectory(prefix="subtitle-render-") as directory:
        temporary = Path(directory)
        for label, at_ms in times.items():
            baseline = output / f"{label}-base.png"
            render(video, None, at_ms, baseline)
            for language, path, cues in (("tr", source, source_cues),
                                         ("en", target, target_cues)):
                shutil.copy2(path, temporary / "sub.srt")
                frame = output / f"{label}-{language}.png"
                render(video, temporary / "sub.srt", at_ms, frame)
                difference = subtitle_difference(baseline, frame)
                cue = active_cue(cues, at_ms)
                samples.append({"label": label, "language": language,
                                "at_ms": at_ms, "cue_id": cue["id"] if cue else None,
                                "cue_text": cue["text"] if cue else None,
                                "rendered_frame": str(frame),
                                "bottom_y_difference": difference,
                                "visible_pixels_changed": difference > 0.05,
                                "expected_visible": cue is not None})

    report = {"video": str(video), "video_sha256": digest(video),
              "source": str(source), "source_sha256": digest(source),
              "target": str(target), "target_sha256": digest(target),
              "renderer": "ffmpeg subtitles/libass", "samples": samples,
              "render_checks_passed": all(item["visible_pixels_changed"] ==
                                          item["expected_visible"] for item in samples),
              "note": "This verifies libass frame rendering, not IINA track state or a full watch-through."}
    report_path = output / "playback-check.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return report_path, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path)
    parser.add_argument("source", type=Path)
    parser.add_argument("target", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--at-ms", type=int, action="append", default=[])
    args = parser.parse_args()
    path, report = check(args.video, args.source, args.target,
                         args.output, args.at_ms)
    print(json.dumps({"report": str(path), "samples": len(report["samples"]),
                      "render_checks_passed": report["render_checks_passed"]}))


if __name__ == "__main__":
    main()
