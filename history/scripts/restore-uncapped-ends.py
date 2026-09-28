#!/usr/bin/env python3
"""Restore uncapped cue ends in a review draft from preserved source subtitles."""

import argparse
import runpy
from pathlib import Path


helpers = runpy.run_path(str(Path(__file__).with_name("light-pass.py")))
parse_srt = helpers["parse_srt"]
write_srt = helpers["write_srt"]


def milliseconds(timestamp):
    hours, minutes, seconds = timestamp.replace(",", ".").split(":")
    return round((int(hours) * 3600 + int(minutes) * 60 + float(seconds)) * 1000)


def bounds(cue):
    start, end = cue["time"].split(" --> ")
    return milliseconds(start), milliseconds(end)


def restore_ends(installed, baseline, draft):
    if len(installed) != len(baseline):
        raise ValueError("Installed and preserved cue counts differ")

    if any(left["text"] != right["text"] for left, right in zip(installed, baseline)):
        raise ValueError("Installed and preserved cue words differ")

    # 1. Match unchanged draft cues to the installed timeline.

    prior_by_key = {}
    for current, prior in zip(installed, baseline):
        key = (current["time"].split(" --> ")[0], current["text"].strip())
        if key in prior_by_key:
            raise ValueError(f"Ambiguous installed cue: {key}")

        prior_by_key[key] = prior

    # 2. Restore only later ends; keep edited and retranscribed cues untouched.

    result = []
    extended = 0
    for cue in draft:
        updated = cue.copy()
        start, end = cue["time"].split(" --> ")
        prior = prior_by_key.get((start, cue["text"].strip()))
        if prior is not None:
            prior_end = prior["time"].split(" --> ")[1]
            if milliseconds(prior_end) > milliseconds(end):
                updated["time"] = f"{start} --> {prior_end}"
                extended += 1

        if bounds(updated)[0] >= bounds(updated)[1]:
            raise ValueError(f"Invalid cue after restoration: {cue['id']}")

        result.append(updated)

    return result, extended


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("installed", type=Path, nargs="?")
    parser.add_argument("baseline", type=Path, nargs="?")
    parser.add_argument("draft", type=Path, nargs="?")
    parser.add_argument("output", type=Path, nargs="?")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    if args.check:
        current = [{"id": 1, "time": "00:00:01,000 --> 00:00:08,000", "text": "Long speech"}]
        preserved = [{**current[0], "time": "00:00:01,000 --> 00:00:16,000"}]
        reviewed = current + [{"id": 2, "time": "00:00:20,000 --> 00:00:21,000", "text": "New line"}]
        result, count = restore_ends(current, preserved, reviewed)
        assert count == 1 and result[0]["time"].endswith("00:00:16,000")
        assert result[1] == reviewed[1]
        print("check ok")
        return

    if not all((args.installed, args.baseline, args.draft, args.output)):
        parser.error("provide installed, baseline, draft, and output paths")

    if args.output.resolve() in {path.resolve() for path in (args.installed, args.baseline, args.draft)}:
        parser.error("output must be a separate review file")

    installed = parse_srt(args.installed.read_text())
    baseline = parse_srt(args.baseline.read_text())
    draft = parse_srt(args.draft.read_text())
    result, extended = restore_ends(installed, baseline, draft)
    write_srt(result, args.output)
    print(f"Restored {extended} uncapped ends in {args.output}; review against audio before installation")


if __name__ == "__main__":
    main()
