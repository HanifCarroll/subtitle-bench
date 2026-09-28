#!/usr/bin/env python3
"""Make separate Turkish and English display drafts from linked utterances."""

import argparse
import json
import runpy
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parent
SEMANTIC = runpy.run_path(str(SCRIPTS / "semantic-review.py"))
WRITE_SRT = runpy.run_path(str(SCRIPTS / "join-clip-drafts.py"))["write_srt"]
READ_CUES = runpy.run_path(str(SCRIPTS / "subtitle-timing.py"))["read_cues"]


def cue_list(items, name):
    """Reject lost text, invalid timing, and same-language overlap."""
    result = []
    for item in sorted(items, key=lambda value: (value["start_ms"], value["end_ms"])):
        if (not isinstance(item.get("text"), str) or not item["text"].strip()
                or not isinstance(item.get("start_ms"), int)
                or not isinstance(item.get("end_ms"), int)
                or item["start_ms"] < 0 or item["start_ms"] >= item["end_ms"]):
            raise ValueError(f"{name} has an invalid text or interval")
        if result and item["start_ms"] < result[-1]["end_ms"]:
            raise ValueError(f"{name} has overlapping display cues")
        result.append({"start_ms": item["start_ms"],
                       "end_ms": item["end_ms"], "text": item["text"].strip()})
    return result


def layout(manifest):
    """Preserve all source utterances and use explicit links for English timing."""

    # 1. Validate links and choose each language's own display intervals.

    units = manifest["utterances"]
    translations = manifest["translations"]
    by_id = {unit["id"]: unit for unit in units}
    linked = {identifier: 0 for identifier in by_id}
    source_items = [{"start_ms": unit["start_ms"], "end_ms": unit["end_ms"],
                     "text": unit["text"]} for unit in units]
    english_items = []
    provisional_links = []
    for translation in translations:
        ids = translation["source_ids"]
        if not ids or any(identifier not in by_id for identifier in ids):
            raise ValueError("English translation has no valid source utterance")
        for identifier in ids:
            linked[identifier] += 1
        if translation["link_status"] != "confirmed":
            provisional_links.append(translation["id"])
        english_items.append({
            "start_ms": translation.get("start_ms", min(by_id[identifier]["start_ms"]
                                                       for identifier in ids)),
            "end_ms": translation.get("end_ms", max(by_id[identifier]["end_ms"]
                                                   for identifier in ids)),
            "text": translation["text"],
        })
    missing = [identifier for identifier, count in linked.items() if count == 0]
    if missing:
        raise ValueError(f"{len(missing)} Turkish utterances lack English translations")

    # 2. Report presentation pressure without deleting dialogue or capping ends.

    source_cues = cue_list(source_items, "Turkish")
    english_cues = cue_list(english_items, "English")
    return source_cues, english_cues, {"source_utterances": len(units),
        "source_cues": len(source_cues), "english_cues": len(english_cues),
        "provisional_links": provisional_links,
        "alignment_pending": [unit["id"] for unit in units
                              if unit["alignment_status"] != "aligned"],
        "note": "Draft layout only. Word timing and translation links need evidence review before release."}


def render(manifest_path, source_output, english_output, report_output):
    # 1. Bind the layout to the current input pair and protect those inputs.

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    original_source = Path(manifest["source"])
    original_english = Path(manifest["target"])
    SEMANTIC["validate"](manifest, original_source, original_english)
    protected = {original_source.resolve(), original_english.resolve(),
                 manifest_path.resolve()}
    outputs = [source_output, english_output, report_output]
    if (len({path.resolve() for path in outputs}) != len(outputs)
            or any(path.resolve() in protected or path.exists() for path in outputs)):
        raise ValueError("Use three new output paths separate from inputs")
    if (source_output.suffix.lower() != ".srt"
            or english_output.suffix.lower() != ".srt"
            or report_output.suffix.lower() != ".json"):
        raise ValueError("Layout outputs need two .srt paths and one .json report")

    # 2. Generate both tracks, validate SRT syntax, then save a hash-bound report.

    source_cues, english_cues, summary = layout(manifest)
    for path in outputs:
        path.parent.mkdir(parents=True, exist_ok=True)
    WRITE_SRT(source_output, source_cues)
    WRITE_SRT(english_output, english_cues)
    READ_CUES(source_output)
    READ_CUES(english_output)
    report = {**summary, "utterance_map": str(manifest_path.resolve()),
              "utterance_map_sha256": SEMANTIC["digest"](manifest_path),
              "source_output": str(source_output.resolve()),
              "source_sha256": SEMANTIC["digest"](source_output),
              "english_output": str(english_output.resolve()),
              "english_sha256": SEMANTIC["digest"](english_output)}
    SEMANTIC["save_json"](report_output, report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("source_output", type=Path)
    parser.add_argument("english_output", type=Path)
    parser.add_argument("report_output", type=Path)
    args = parser.parse_args()
    result = render(args.manifest, args.source_output,
                    args.english_output, args.report_output)
    print(json.dumps({"source_cues": result["source_cues"],
                      "english_cues": result["english_cues"],
                      "provisional_links": len(result["provisional_links"]),
                      "alignment_pending": len(result["alignment_pending"]),
                      "report": str(args.report_output.resolve())}))


if __name__ == "__main__":
    main()
