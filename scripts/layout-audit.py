#!/usr/bin/env python3
"""Compare separate display cues with current Turkish word-timing evidence."""

import argparse
import json
import runpy
from pathlib import Path


SEMANTIC = runpy.run_path(str(Path(__file__).with_name("semantic-review.py")))
ALIGNER = runpy.run_path(str(Path(__file__).with_name("align-turkish.py")))


def aligned_units(directory, manifest, video_sha256):
    """Read current per-unit results while leaving stale sections visible."""
    expected = {unit["id"]: unit for unit in manifest["utterances"]}
    found = {}
    stale = set()
    for path in directory.glob("*.json"):
        report = json.loads(path.read_text(encoding="utf-8"))
        if report.get("video_sha256") != video_sha256:
            raise ValueError("Alignment report belongs to another video")
        current_units = [expected[item["id"]] for item in report.get("utterances", [])
                         if item.get("id") in expected]
        identity = ALIGNER["alignment_input"](
            current_units, report["audio_start_ms"], report["audio_end_ms"],
            video_sha256, report["model"])
        report_stale = identity != report.get("input_sha256")
        for result in report.get("utterances", []):
            unit = expected.get(result.get("id"))
            if unit is None:
                continue
            if (report_stale or result.get("text") != unit["text"]
                    or result.get("source_cue_ids") != unit["cue_ids"]):
                stale.add(unit["id"])
                continue
            if unit["id"] in found:
                raise ValueError("Duplicate alignment result for one source utterance")
            found[unit["id"]] = result
    return found, stale


def word_span(results, identifiers):
    timings = [word for identifier in identifiers
               for word in results.get(identifier, {}).get("word_timings", [])
               if isinstance(word.get("start_ms"), int)
               and isinstance(word.get("end_ms"), int)]
    if not timings:
        return None
    return min(word["start_ms"] for word in timings), max(
        word["end_ms"] for word in timings)


def audit(manifest, alignment_results, stale, threshold_ms=700, max_cps=25):
    """Flag timing and density questions without rewriting or deleting speech."""
    if threshold_ms < 0 or max_cps <= 0:
        raise ValueError("Layout thresholds must be positive")
    units = manifest["utterances"]
    translations = manifest["translations"]
    by_id = {unit["id"]: unit for unit in units}
    linked = {unit["id"]: 0 for unit in units}
    flags = []
    for language, items in (("source", units), ("english", translations)):
        for item in items:
            identifiers = [item["id"]] if language == "source" else item["source_ids"]
            if language == "english":
                for identifier in identifiers:
                    linked[identifier] += 1
            span = word_span(alignment_results, identifiers)
            if any(identifier in stale for identifier in identifiers):
                flags.append({"kind": "stale_alignment", "language": language,
                              "id": item["id"]})
            if span is None:
                flags.append({"kind": "missing_word_timing", "language": language,
                              "id": item["id"]})
            else:
                lead_ms = span[0] - item["start_ms"]
                tail_ms = item["end_ms"] - span[1]
                if lead_ms > threshold_ms:
                    flags.append({"kind": "possible_early_cue", "language": language,
                                  "id": item["id"], "lead_ms": lead_ms})
                if tail_ms > threshold_ms:
                    flags.append({"kind": "possible_lingering_cue",
                                  "language": language, "id": item["id"],
                                  "tail_ms": tail_ms})
            duration_seconds = (item["end_ms"] - item["start_ms"]) / 1000
            if duration_seconds <= 0:
                raise ValueError("Display cue has invalid timing")
            cps = len(item["text"].replace("\n", "")) / duration_seconds
            if cps > max_cps:
                flags.append({"kind": "fast_cue", "language": language,
                              "id": item["id"], "characters_per_second": round(cps, 2)})
            if language == "english" and len(identifiers) >= 2:
                ordered = sorted((by_id[identifier] for identifier in identifiers),
                                 key=lambda unit: unit["start_ms"])
                gap = max((right["start_ms"] - left["end_ms"]
                           for left, right in zip(ordered, ordered[1:])), default=0)
                if gap > 1000:
                    flags.append({"kind": "translation_spans_dialogue_gap",
                                  "language": language, "id": item["id"],
                                  "gap_ms": gap})
    for identifier, count in linked.items():
        if count == 0:
            flags.append({"kind": "missing_english_link", "language": "source",
                          "id": identifier})
    return flags


def run(video, manifest_path, alignment_directory, output, threshold_ms, max_cps):
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    SEMANTIC["validate"](manifest, Path(manifest["source"]),
                         Path(manifest["target"]))
    if output.exists() or output.suffix.lower() != ".json":
        raise ValueError("Choose a new JSON report path")
    video_sha256 = ALIGNER["digest"](video)
    results, stale = aligned_units(alignment_directory, manifest, video_sha256)
    flags = audit(manifest, results, stale, threshold_ms, max_cps)
    report = {"utterance_map": str(manifest_path.resolve()),
              "utterance_map_sha256": SEMANTIC["digest"](manifest_path),
              "alignment_directory": str(alignment_directory.resolve()),
              "video_sha256": video_sha256,
              "source_units": len(manifest["utterances"]),
              "aligned_units": len(results), "stale_units": sorted(stale),
              "lead_tail_threshold_ms": threshold_ms, "max_cps": max_cps,
              "flags": flags,
              "note": "Forced-alignment and reading-speed flags are review evidence, not permission to delete words or cap cues."}
    SEMANTIC["save_json"](output, report)
    return {"report": str(output.resolve()), "aligned_units": len(results),
            "stale_units": len(stale), "flags": len(flags)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("alignment_directory", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--lead-tail-ms", type=int, default=700)
    parser.add_argument("--max-cps", type=float, default=25)
    args = parser.parse_args()
    print(json.dumps(run(args.video, args.manifest, args.alignment_directory, args.output,
                         args.lead_tail_ms, args.max_cps)))


if __name__ == "__main__":
    main()
