#!/usr/bin/env python3
"""Report possible speech/subtitle timing gaps; optionally draw an SVG review map."""

import argparse
import json
import math
import runpy
from pathlib import Path
from xml.sax.saxutils import escape


SCRIPTS = Path(__file__).resolve().parent
AUDIT = runpy.run_path(str(SCRIPTS / "audit-speech-coverage.py"))
read_cues = AUDIT["read_cues"]
duration_seconds = AUDIT["duration_seconds"]
vad_intervals = AUDIT["vad_intervals"]
uncovered_speech = AUDIT["uncovered_speech"]
subtitle_without_speech = AUDIT["subtitle_without_speech"]

LEFT = 150
WIDTH = 1200
SECONDS_PER_ROW = 60
TOP = 150


def clock(seconds):
    whole = int(seconds)
    return f"{whole // 3600:02}:{whole // 60 % 60:02}:{whole % 60:02}"


def precise_clock(seconds):
    milliseconds = round(seconds * 1000)
    return f"{clock(milliseconds // 1000)}.{milliseconds % 1000:03}"


def rectangles(intervals, row_start, row_end, y, color, tooltip):
    """Draw only the part of each interval inside this one-minute row."""
    pieces = []
    for start, end in intervals:
        clipped_start = max(start, row_start)
        clipped_end = min(end, row_end)
        if clipped_end <= clipped_start:
            continue

        x = LEFT + (clipped_start - row_start) * WIDTH / SECONDS_PER_ROW
        width = max(0.5, (clipped_end - clipped_start) * WIDTH / SECONDS_PER_ROW)
        title = escape(tooltip(start, end))
        pieces.append(
            f'<rect x="{x:.2f}" y="{y}" width="{width:.2f}" height="15" '
            f'fill="{color}"><title>{title}</title></rect>'
        )

    return pieces


def cue_summary(cue):
    if cue is None:
        return None

    return {
        "id": cue["id"],
        "start_seconds": cue["start"] / 1000,
        "end_seconds": cue["end"] / 1000,
        "text": cue["text"],
    }


def make_report(video, duration, speech, tracks):
    # 1. Keep detected speech and each track's cue coverage in machine-readable form.

    track_reports = []
    for name, path, cues in tracks:
        gaps = uncovered_speech(speech, cues)
        nonspeech = subtitle_without_speech(speech, cues)
        items = []
        for gap_start, gap_end in gaps:
            previous = max((cue for cue in cues if cue["end"] / 1000 <= gap_start + 0.15),
                           key=lambda cue: cue["end"], default=None)
            following = min((cue for cue in cues if cue["start"] / 1000 >= gap_end - 0.15),
                            key=lambda cue: cue["start"], default=None)
            items.append({
                "start_seconds": round(gap_start, 3),
                "end_seconds": round(gap_end, 3),
                "duration_seconds": round(gap_end - gap_start, 3),
                "previous_cue": cue_summary(previous),
                "next_cue": cue_summary(following),
            })

        track_reports.append({
            "name": name,
            "srt": str(path),
            "cue_count": len(cues),
            "possible_gap_count": len(items),
            "possible_gaps": items,
            "possible_subtitle_without_speech_count": len(nonspeech),
            "possible_subtitle_without_speech": nonspeech,
        })

    return {
        "video": str(video),
        "duration_seconds": round(duration, 3),
        "detected_speech_intervals": [
            {"start_seconds": round(start, 3), "end_seconds": round(end, 3)}
            for start, end in speech
        ],
        "tracks": track_reports,
        "note": "Speech gaps and subtitle time without detected speech are review prompts. VAD can miss quiet words or flag noise. Listen before editing subtitles.",
    }


def make_svg(video, duration, speech, tracks):
    # 1. Compare every subtitle track with the same detected speech intervals.

    gap_sets = [uncovered_speech(speech, cues) for _, _, cues in tracks]
    nonspeech_sets = [subtitle_without_speech(speech, cues) for _, _, cues in tracks]
    row_height = 48 + 23 * len(tracks)
    row_count = math.ceil(duration / SECONDS_PER_ROW)
    height = TOP + row_count * row_height + 25
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="1400" height="{height}" '
        f'viewBox="0 0 1400 {height}">',
        '<style>text{font-family:-apple-system,BlinkMacSystemFont,Arial,sans-serif;fill:#1c2732}'
        '.title{font-size:22px;font-weight:700}.small{font-size:12px;fill:#526170}'
        '.label{font-size:12px;font-weight:600}.tick{stroke:#d9e0e6;stroke-width:1}</style>',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<text x="24" y="35" class="title">Speech and subtitles: {escape(video.name)}</text>',
        f'<text x="24" y="59" class="small">{clock(duration)} video · '
        f'{len(speech)} detected speech intervals · '
        + " · ".join(f"{escape(name)}: {len(gaps)} possible gaps" for (name, _, _), gaps in zip(tracks, gap_sets))
        + '</text>',
        '<rect x="24" y="75" width="16" height="14" fill="#2775b6"/>'
        '<text x="46" y="87" class="small">detected speech</text>'
        '<rect x="190" y="75" width="16" height="14" fill="#3b9871"/>'
        '<text x="212" y="87" class="small">subtitle visible</text>'
        '<rect x="365" y="75" width="16" height="14" fill="#d94b47"/>'
        '<text x="387" y="87" class="small">possible speech without subtitle</text>',
        '<rect x="670" y="75" width="16" height="14" fill="#d68b17"/>'
        '<text x="692" y="87" class="small">possible subtitle without speech</text>',
        '<text x="24" y="111" class="small">Each row is one minute. Hover over a bar for its times. '
        'Red and amber are review prompts, not proof of a timing error.</text>',
    ]

    # 2. Repeat a minute-scale ruler so short mismatches stay visible throughout.

    for index in range(row_count):
        row_start = index * SECONDS_PER_ROW
        row_end = min(duration, row_start + SECONDS_PER_ROW)
        y = TOP + index * row_height
        if index % 2:
            parts.append(f'<rect x="0" y="{y - 18}" width="1400" height="{row_height}" fill="#f5f7f9"/>')

        parts.append(f'<text x="24" y="{y + 5}" class="label">{clock(row_start)}</text>')
        for second in range(0, 61, 10):
            x = LEFT + second * WIDTH / SECONDS_PER_ROW
            parts.append(f'<line x1="{x:.0f}" y1="{y - 16}" x2="{x:.0f}" '
                         f'y2="{y + 25 + 23 * len(tracks)}" class="tick"/>')
            parts.append(f'<text x="{x + 2:.0f}" y="{y - 4}" class="small">:{second:02}</text>')

        parts.append(f'<text x="88" y="{y + 18}" class="small">Speech</text>')
        parts.extend(rectangles(speech, row_start, row_end, y + 6, "#2775b6",
                                lambda start, end: f"Speech detected {precise_clock(start)}–{precise_clock(end)}"))

        for track_index, ((name, _, cues), gaps, nonspeech) in enumerate(
            zip(tracks, gap_sets, nonspeech_sets)
        ):
            track_y = y + 29 + 23 * track_index
            parts.append(f'<text x="88" y="{track_y + 12}" class="small">{escape(name)}</text>')
            intervals = [(cue["start"] / 1000, cue["end"] / 1000) for cue in cues]
            parts.extend(rectangles(intervals, row_start, row_end, track_y, "#3b9871",
                                    lambda start, end: f"Subtitle {precise_clock(start)}–{precise_clock(end)}"))
            parts.extend(rectangles(
                [(item["start_seconds"], item["end_seconds"]) for item in nonspeech],
                row_start, row_end, track_y, "#d68b17",
                lambda start, end: f"Check subtitle without detected speech {precise_clock(start)}–{precise_clock(end)}",
            ))
            parts.extend(rectangles(gaps, row_start, row_end, track_y, "#d94b47",
                                    lambda start, end: f"Check audio {precise_clock(start)}–{precise_clock(end)}"))

    parts.append("</svg>")
    return "\n".join(parts) + "\n", gap_sets


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", nargs="?", type=Path)
    parser.add_argument("srts", nargs="*", type=Path, help="one or more SRT files")
    parser.add_argument("--output", type=Path, help="JSON report to create")
    parser.add_argument("--svg", type=Path, help="optional visual timeline")
    parser.add_argument("--speech-json", type=Path, help="reuse detected speech from an earlier report")
    parser.add_argument("--check", action="store_true", help="run a small synthetic rendering check")
    args = parser.parse_args()

    if args.check:
        tracks = [("TR", Path("demo.tr.srt"), [{"id": 1, "start": 4000, "end": 8000, "text": "Test"}])]
        report = make_report(Path("demo.webm"), 60, [(2, 12)], tracks)
        svg, gaps = make_svg(Path("demo.webm"), 60, [(2, 12)], tracks)
        assert len(gaps[0]) == 2 and 'fill="#d94b47"' in svg
        assert report["tracks"][0]["possible_gap_count"] == 2
        assert report["tracks"][0]["possible_gaps"][0]["next_cue"]["id"] == 1
        assert report["tracks"][0]["possible_subtitle_without_speech_count"] == 0
        cue = [{"id": 436, "start": 1_626_680, "end": 1_648_420,
                "text": "Hatırlasana."}]
        flags = subtitle_without_speech(
            [(1_620.82, 1_627.31), (1_648.21, 1_649.23)], cue
        )
        assert len(flags) == 1 and flags[0]["duration_seconds"] > 20
        assert "00:00:00" in svg and "Check audio" in svg
        print("check ok")
        return

    if not args.video or not args.srts or not args.output:
        parser.error("provide VIDEO SRT [SRT ...] --output REPORT.json")

    # 1. Keep report destinations separate from the video and subtitle inputs.

    video = args.video.resolve(strict=True)
    tracks = [(path.name.split(".")[-2].upper(), path.resolve(strict=True),
               sorted(read_cues(path), key=lambda cue: cue["start"]))
              for path in args.srts]
    media_inputs = {video}
    media_inputs.update(path for _, path, _ in tracks)

    destinations = [args.output.resolve()]
    if args.svg:
        destinations.append(args.svg.resolve())
    if any(path in media_inputs for path in destinations) or len(set(destinations)) != len(destinations):
        parser.error("report and SVG destinations must differ from media inputs and each other")
    if args.svg and args.speech_json and args.svg.resolve() == args.speech_json.resolve(strict=True):
        parser.error("SVG destination must differ from the speech report being reused")
    if args.output.suffix.lower() != ".json" or (args.svg and args.svg.suffix.lower() != ".svg"):
        parser.error("use a .json report and, optionally, a .svg chart")

    # 2. Scan speech once, or reuse a report for this exact video and duration.

    duration = duration_seconds(video)
    if args.speech_json:
        cache = json.loads(args.speech_json.read_text(encoding="utf-8"))
        if cache["video"] != str(video) or abs(cache["duration_seconds"] - duration) > 0.1:
            parser.error("speech cache belongs to a different video")

        speech = [(item["start_seconds"], item["end_seconds"])
                  for item in cache["detected_speech_intervals"]]
    else:
        speech = vad_intervals(video, duration)

    # 3. Write the structured review queue and only draw a chart when requested.

    report = make_report(video, duration, speech, tracks)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.svg:
        svg, _ = make_svg(video, duration, speech, tracks)
        args.svg.parent.mkdir(parents=True, exist_ok=True)
        args.svg.write_text(svg, encoding="utf-8")

    print(json.dumps({"report": str(args.output), "svg": str(args.svg) if args.svg else None,
                      "speech_intervals": len(speech),
                      "possible_gaps": {track["name"]: track["possible_gap_count"]
                                        for track in report["tracks"]},
                      "possible_subtitle_without_speech": {
                          track["name"]: track["possible_subtitle_without_speech_count"]
                          for track in report["tracks"]}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
