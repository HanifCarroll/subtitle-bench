#!/usr/bin/env python3
"""Compare separate display cues with current Turkish word-timing evidence."""

import argparse
import json
import runpy
import sys
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
            if any(alignment_results.get(identifier, {}).get("status") in
                   ("partial", "failed", "suspicious") for identifier in identifiers):
                flags.append({"kind": "unreliable_alignment", "language": language,
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
              "source_sha256": manifest["source_sha256"],
              "target_sha256": manifest["target_sha256"],
              "source_units": len(manifest["utterances"]),
              "aligned_units": len(results), "stale_units": sorted(stale),
              "lead_tail_threshold_ms": threshold_ms, "max_cps": max_cps,
              "flags": flags,
              "note": "Forced-alignment and reading-speed flags are review evidence, not permission to delete words or cap cues."}
    SEMANTIC["save_json"](output, report)
    return {"report": str(output.resolve()), "aligned_units": len(results),
            "stale_units": len(stale), "flags": len(flags)}


def needs_resolution(flag):
    """Reserve blocking review for material timing and unreliable evidence."""
    kind = flag["kind"]
    return (kind in ("stale_alignment", "unreliable_alignment",
                     "missing_word_timing", "translation_spans_dialogue_gap",
                     "missing_english_link")
            or kind == "possible_early_cue" and flag["lead_ms"] >= 2000
            or kind == "possible_lingering_cue" and flag["tail_ms"] >= 2000)


def flag_binding(flag, manifest, results, stale, video_sha256):
    items = manifest["utterances"] if flag["language"] == "source" else manifest["translations"]
    item = next(value for value in items if value["id"] == flag["id"])
    identifiers = [item["id"]] if flag["language"] == "source" else item["source_ids"]
    return SEMANTIC["fingerprint"]({
        "flag": flag, "item": item, "video_sha256": video_sha256,
        "alignment": {identifier: results.get(identifier) for identifier in identifiers},
        "stale": sorted(identifier for identifier in identifiers if identifier in stale),
    })


def current_report(report_path, manifest_path, video):
    """Recompute current findings so an edited report cannot clear the gate."""
    report = json.loads(report_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    SEMANTIC["validate"](manifest, Path(manifest["source"]), Path(manifest["target"]))
    video_sha256 = ALIGNER["digest"](video)
    if (report.get("utterance_map") != str(manifest_path.resolve())
            or report.get("utterance_map_sha256") != SEMANTIC["digest"](manifest_path)
            or report.get("source_sha256") != manifest["source_sha256"]
            or report.get("target_sha256") != manifest["target_sha256"]
            or report.get("video_sha256") != video_sha256):
        raise ValueError("Layout report is stale or belongs to another candidate")
    results, stale = aligned_units(Path(report["alignment_directory"]),
                                   manifest, video_sha256)
    flags = audit(manifest, results, stale, report["lead_tail_threshold_ms"],
                  report["max_cps"])
    if (flags != report.get("flags") or report.get("aligned_units") != len(results)
            or report.get("stale_units") != sorted(stale)):
        raise ValueError("Layout findings differ from current alignment evidence")
    return report, manifest, results, stale


def evidence_is_current(evidence, require_audio):
    if not isinstance(evidence, list) or not evidence:
        return False
    if require_audio and not any(isinstance(item, dict)
                                 and item.get("kind") == "original_audio"
                                 for item in evidence):
        return False
    return all(isinstance(item, dict)
               and item.get("kind") in ("original_audio", "alignment_result",
                                        "scene_context", "render_frame", "other")
               and isinstance(item.get("path"), str)
               and Path(item["path"]).is_file()
               and item.get("sha256") == SEMANTIC["digest"](Path(item["path"]))
               for item in evidence)


def decision_key(flag):
    return f"{flag['language']}:{flag['id']}:{flag['kind']}"


def layout_blockers(report_path, manifest_path, video, decisions_path=None):
    if not report_path or not report_path.is_file():
        return ["Current layout report is missing"]
    try:
        report, manifest, results, stale = current_report(
            report_path, manifest_path, video
        )
    except (OSError, ValueError, KeyError, TypeError) as error:
        return [f"Layout report is invalid: {error}"]
    required = [flag for flag in report["flags"] if needs_resolution(flag)]
    if not required:
        return []
    decisions = {}
    if decisions_path and decisions_path.is_file():
        try:
            data = json.loads(decisions_path.read_text(encoding="utf-8"))
            decisions = data.get("decisions", {})
            if not isinstance(decisions, dict):
                raise ValueError("Timing decisions must be keyed by finding")
        except (OSError, ValueError) as error:
            return [f"Timing decisions are invalid: {error}"]
    unresolved = []
    for flag in required:
        decision = decisions.get(decision_key(flag))
        binding = flag_binding(flag, manifest, results, stale, report["video_sha256"])
        if (not isinstance(decision, dict)
                or decision.get("finding_sha256") != binding
                or decision.get("disposition") not in
                ("false_positive", "accepted_exception", "alternate_timing_evidence")
                or not isinstance(decision.get("reviewer"), str)
                or not decision["reviewer"].strip()
                or not isinstance(decision.get("reason"), str)
                or not decision["reason"].strip()
                or not evidence_is_current(decision.get("evidence"),
                                           flag["kind"] in
                                           ("possible_early_cue", "possible_lingering_cue",
                                            "translation_spans_dialogue_gap"))):
            unresolved.append(flag)
    if not unresolved:
        return []
    kinds = {}
    for flag in unresolved:
        kinds[flag["kind"]] = kinds.get(flag["kind"], 0) + 1
    return [f"{len(unresolved)} material timing or alignment findings need resolution: {kinds}"]


def adjudicate(report_path, manifest_path, video, decisions_path, decision_path):
    """Resolve one scene's overlapping timing findings with shared evidence."""
    report, manifest, results, stale = current_report(report_path, manifest_path, video)
    decision = json.loads(decision_path.read_text(encoding="utf-8"))
    keys = decision.get("findings", [decision.get("finding")])
    if not isinstance(keys, list) or not keys or len(keys) != len(set(keys)):
        raise ValueError("Timing decision needs distinct current findings")
    by_key = {decision_key(item): item for item in report["flags"]}
    flags = [by_key.get(key) for key in keys]
    if any(flag is None or not needs_resolution(flag) for flag in flags):
        raise ValueError("Timing decision does not name current required findings")
    intervals = []
    for flag in flags:
        items = (manifest["utterances"] if flag["language"] == "source"
                 else manifest["translations"])
        item = next(value for value in items if value["id"] == flag["id"])
        intervals.append((item["start_ms"], item["end_ms"]))
    intervals.sort()
    if any(right[0] > left[1] + 2000
           for left, right in zip(intervals, intervals[1:])):
        raise ValueError("One timing decision must concern one overlapping scene")
    if (decision.get("disposition") not in
            ("false_positive", "accepted_exception", "alternate_timing_evidence",
             "unresolved")
            or not isinstance(decision.get("reviewer"), str)
            or not decision["reviewer"].strip()
            or not isinstance(decision.get("reason"), str)
            or not decision["reason"].strip()
            or not evidence_is_current(decision.get("evidence"),
                                       any(flag["kind"] in
                                           ("possible_early_cue", "possible_lingering_cue",
                                            "translation_spans_dialogue_gap")
                                           for flag in flags))):
        raise ValueError("Timing decision needs a reviewer, reason, and current evidence")
    data = json.loads(decisions_path.read_text(encoding="utf-8")) if decisions_path.exists() else {}
    entries = data.setdefault("decisions", {})
    if not isinstance(entries, dict):
        raise ValueError("Timing decisions must be keyed by finding")
    group_id = SEMANTIC["fingerprint"](sorted(keys))
    for key, flag in zip(keys, flags):
        entries[key] = {"finding_sha256": flag_binding(
            flag, manifest, results, stale, report["video_sha256"]),
            "flag": flag, "group_id": group_id,
            "disposition": decision["disposition"],
            "reviewer": decision["reviewer"], "reason": decision["reason"],
            "evidence": decision["evidence"]}
    SEMANTIC["save_json"](decisions_path, data)
    return keys


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "adjudicate":
        parser = argparse.ArgumentParser(description="Resolve one timing finding")
        parser.add_argument("video", type=Path)
        parser.add_argument("manifest", type=Path)
        parser.add_argument("report", type=Path)
        parser.add_argument("decisions", type=Path)
        parser.add_argument("decision", type=Path)
        args = parser.parse_args(sys.argv[2:])
        print(json.dumps({"resolved": adjudicate(
            args.report, args.manifest, args.video, args.decisions, args.decision
        )}))
        return
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("alignment_directory", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--lead-tail-ms", type=int, default=700)
    parser.add_argument("--max-cps", type=float, default=25)
    args = parser.parse_args()
    print(json.dumps(run(args.video, args.manifest, args.alignment_directory,
                         args.output, args.lead_tail_ms, args.max_cps)))


if __name__ == "__main__":
    main()
