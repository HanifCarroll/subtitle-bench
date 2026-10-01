#!/usr/bin/env python3
"""Checkpoint agent-authored English drafts without calling a text model."""

import argparse
import hashlib
import json
import runpy
from bisect import bisect_left
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parent
READ_CUES = runpy.run_path(str(SCRIPTS / "subtitle-timing.py"))["read_cues"]
WRITE_SRT = runpy.run_path(str(SCRIPTS / "join-clip-drafts.py"))["write_srt"]


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False,
                                     sort_keys=True).encode("utf-8")).hexdigest()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")


def snapshot(cues):
    return [{"id": cue["id"], "start_ms": cue["start"],
             "end_ms": cue["end"], "text": cue["text"]} for cue in cues]


def rebase(record, cues, source_sha256):
    """Retain only unambiguous, unaffected translations after a source edit."""
    before = record["source_cues"]
    after = snapshot(cues)
    exact = defaultdict(list)
    for old in before:
        exact[(old["start_ms"], old["end_ms"], old["text"])].append(old)
    matched = {}
    used_old = set()
    for new in after:
        candidates = [old for old in exact[(new["start_ms"], new["end_ms"], new["text"])]
                      if old["id"] not in used_old]
        if len(candidates) == 1:
            matched[new["id"]] = candidates[0]["id"]
            used_old.add(candidates[0]["id"])

    old_by_text = defaultdict(list)
    new_by_text = defaultdict(list)
    for old in before:
        if old["id"] not in used_old:
            old_by_text[old["text"]].append(old)
    for new in after:
        if new["id"] not in matched:
            new_by_text[new["text"]].append(new)
    for text, new_items in new_by_text.items():
        old_items = old_by_text[text]
        if (len(old_items) == len(new_items) == 1
                and abs(old_items[0]["start_ms"] - new_items[0]["start_ms"]) <= 2000
                and abs(old_items[0]["end_ms"] - new_items[0]["end_ms"]) <= 2000):
            matched[new_items[0]["id"]] = old_items[0]["id"]
            used_old.add(old_items[0]["id"])

    affected = {new["id"] for new in after if new["id"] not in matched}
    starts = [new["start_ms"] for new in after]
    for old in before:
        if old["id"] in used_old:
            continue
        position = bisect_left(starts, old["start_ms"])
        if after:
            affected.add(after[min(position, len(after) - 1)]["id"])
    local = {cue_id + offset for cue_id in affected for offset in range(-2, 3)
             if 1 <= cue_id + offset <= len(after)}

    old_translations = record["translations"]
    old_deferred = record.get("deferred", {})
    translations = {str(new_id): old_translations[str(old_id)]
                    for new_id, old_id in matched.items()
                    if new_id not in local and str(old_id) in old_translations}
    deferred = {str(new_id): old_deferred[str(old_id)]
                for new_id, old_id in matched.items()
                if new_id not in local and str(old_id) in old_deferred}
    record.setdefault("history", []).append({
        "at": datetime.now(timezone.utc).isoformat(),
        "reason": "source_changed", "old_source_sha256": record["source_sha256"],
        "old_cue_count": record["cue_count"],
        "retained_translation_count": len(translations),
        "old_translations": old_translations,
        "old_deferred": old_deferred,
        "invalidated_translation_ids": sorted(
            int(key) for key in old_translations
            if int(key) not in used_old or any(
                new_id in local and old_id == int(key)
                for new_id, old_id in matched.items())),
        "old_batches": record["batches"],
    })
    record.update({"source_sha256": source_sha256, "cue_count": len(cues),
                   "source_cues": after, "translations": translations,
                   "deferred": deferred, "batches": {}})
    return record


def current(source, progress, batch_size):
    source = source.resolve(strict=True)
    cues = READ_CUES(source)
    if not cues or not 1 <= batch_size <= 30:
        raise ValueError("Source needs cues and batch size must be 1-30")
    identity = {"version": 2, "source": str(source),
                "source_sha256": digest(source), "batch_size": batch_size,
                "cue_count": len(cues)}
    if progress.exists():
        record = json.loads(progress.read_text(encoding="utf-8"))
        if record.get("version") == 1 and all(
            record.get(key) == identity[key]
            for key in ("source", "source_sha256", "batch_size", "cue_count")
        ):
            record.update({"version": 2, "source_cues": snapshot(cues),
                           "deferred": {}, "history": []})
            save(progress, record)
        if any(record.get(key) != identity[key]
               for key in ("version", "source", "batch_size")):
            raise ValueError("Translation progress belongs to another source or batch size")
        if record["source_sha256"] != identity["source_sha256"]:
            if not isinstance(record.get("source_cues"), list):
                raise ValueError("Old progress has no cue snapshot for safe rebasing")
            record = rebase(record, cues, identity["source_sha256"])
            save(progress, record)
        elif record.get("source_cues") != snapshot(cues):
            raise ValueError("Translation cue snapshot differs from its source hash")
    else:
        record = {**identity, "source_cues": snapshot(cues),
                  "translations": {}, "deferred": {}, "batches": {}, "history": []}
        save(progress, record)
    return cues, record


def batch_input(cues, record, number):
    size = record["batch_size"]
    total = (len(cues) + size - 1) // size
    if not 1 <= number <= total:
        raise ValueError("Batch number is outside the source")
    start = (number - 1) * size
    selected = cues[start:start + size]
    context = cues[max(0, start - 2):min(len(cues), start + size + 2)]
    payload = {
        "batch_number": number, "source_sha256": record["source_sha256"],
        "cue_ids": [cue["id"] for cue in selected],
        "context": [{"id": cue["id"], "start_ms": cue["start"],
                     "end_ms": cue["end"], "text": cue["text"]}
                    for cue in context],
        "instruction": "Translate each settled Turkish cue into natural, faithful English. For a disputed cue return defer_reason instead of inventing English. Return every selected cue ID once; continue independent cues.",
    }
    payload["deferred_ids"] = [cue["id"] for cue in selected
                               if str(cue["id"]) in record["deferred"]]
    payload["input_sha256"] = fingerprint(payload)
    payload["completed"] = all(str(cue["id"]) in record["translations"]
                               for cue in selected)
    return payload


def apply(source, progress, response):
    record = json.loads(progress.read_text(encoding="utf-8"))
    cues, record = current(source, progress, record["batch_size"])
    authored = json.loads(response.read_text(encoding="utf-8"))
    number = authored.get("batch_number")
    if type(number) is not int:
        raise ValueError("Response needs a batch number")
    expected = batch_input(cues, record, number)
    rows = authored.get("translations")
    if (authored.get("input_sha256") != expected["input_sha256"]
            or not isinstance(authored.get("reviewer"), str)
            or not authored["reviewer"].strip()
            or not isinstance(rows, list)
            or len(rows) != len(expected["cue_ids"])):
        raise ValueError("Translation response is stale or incomplete")
    if any(not isinstance(row, dict) or type(row.get("cue_id")) is not int
           for row in rows):
        raise ValueError("Translation response has an invalid cue ID")
    ids = [row["cue_id"] for row in rows]
    if set(ids) != set(expected["cue_ids"]) or len(ids) != len(set(ids)):
        raise ValueError("Translation response must cover each selected cue once")
    for row in rows:
        translated = isinstance(row.get("text"), str) and bool(row["text"].strip())
        deferred = isinstance(row.get("defer_reason"), str) and bool(
            row["defer_reason"].strip())
        if (translated == deferred
                or ("text" in row) == ("defer_reason" in row)
                or set(row) - {"cue_id", "text", "defer_reason"}):
            raise ValueError("Each cue needs English text or a specific defer_reason")
    key = str(number)
    saved = {str(row["cue_id"]): ({"text": row["text"].strip()}
             if "text" in row else {"defer_reason": row["defer_reason"].strip()})
             for row in rows}
    if key in record["batches"]:
        previous = record["batches"][key]
        previous_saved = previous.get("entries", {
            cue_id: {"text": value}
            for cue_id, value in previous.get("translations", {}).items()
        })
        if previous_saved == saved:
            return record
        if any("text" in old and old != saved[cue_id]
               for cue_id, old in previous_saved.items()):
            raise ValueError("A translated cue changed; preserve it and rebase after source repair")
        record.setdefault("history", []).append({
            "at": datetime.now(timezone.utc).isoformat(),
            "reason": "resolved_deferred", "old_batch": previous,
        })
    for cue_id, entry in saved.items():
        if "text" in entry:
            record["translations"][cue_id] = entry["text"]
            record["deferred"].pop(cue_id, None)
        else:
            record["deferred"][cue_id] = entry["defer_reason"]
            record["translations"].pop(cue_id, None)
    record["batches"][key] = {
        "reviewer": authored["reviewer"],
        "input_sha256": expected["input_sha256"],
        "response_sha256": digest(response),
        "entries": saved, "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    save(progress, record)
    return record


def import_responses(source, progress, response, batch_size=12):
    """Checkpoint any sized agent-authored set without episode-specific parsing code."""
    cues, record = current(source, progress, batch_size)
    authored = json.loads(response.read_text(encoding="utf-8"))
    rows = authored.get("translations")
    if (authored.get("source_sha256") != record["source_sha256"]
            or not isinstance(authored.get("reviewer"), str)
            or not authored["reviewer"].strip()
            or not isinstance(rows, list) or not rows):
        raise ValueError("Import needs current source hash, reviewer, and translations")
    valid_ids = {cue["id"] for cue in cues}
    seen = set()
    for row in rows:
        if (not isinstance(row, dict) or type(row.get("cue_id")) is not int
                or row["cue_id"] not in valid_ids or row["cue_id"] in seen):
            raise ValueError("Import has a duplicate or invalid source cue ID")
        seen.add(row["cue_id"])
        translated = isinstance(row.get("text"), str) and bool(row["text"].strip())
        deferred = isinstance(row.get("defer_reason"), str) and bool(
            row["defer_reason"].strip())
        if (translated == deferred
                or ("text" in row) == ("defer_reason" in row)
                or set(row) - {"cue_id", "text", "defer_reason"}):
            raise ValueError("Each import row needs English text or a defer_reason")
        key = str(row["cue_id"])
        if translated and key in record["translations"] and (
                record["translations"][key] != row["text"].strip()):
            raise ValueError("Changed English needs a source rebase or a reviewed paired edit")
        if deferred and key in record["translations"]:
            raise ValueError("Cannot defer an accepted English cue without a source rebase")

    # Commit all rows together after checking the entire input.
    for row in rows:
        key = str(row["cue_id"])
        if "text" in row:
            record["translations"][key] = row["text"].strip()
            record["deferred"].pop(key, None)
        else:
            record["deferred"][key] = row["defer_reason"].strip()
    record.setdefault("imports", []).append({
        "reviewer": authored["reviewer"], "source_sha256": record["source_sha256"],
        "response_sha256": digest(response), "cue_ids": sorted(seen),
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    })
    save(progress, record)
    return record


def export(source, progress, output, partial=False):
    record = json.loads(progress.read_text(encoding="utf-8"))
    cues, record = current(source, progress, record["batch_size"])
    if output.exists() or output.suffix.lower() != ".srt":
        raise ValueError("Use a new English .srt output")
    if partial and not output.name.endswith(".partial.en.srt"):
        raise ValueError("Partial export must be named *.partial.en.srt")
    expected = {str(cue["id"]) for cue in cues}
    missing = expected - set(record["translations"])
    if missing and not partial:
        raise ValueError(f"English draft is incomplete: {len(missing)} cues remain")
    if partial and not record["translations"]:
        raise ValueError("Partial English draft has no settled translations")
    output.parent.mkdir(parents=True, exist_ok=True)
    WRITE_SRT(output, [{"start_ms": cue["start"], "end_ms": cue["end"],
                        "text": record["translations"][str(cue["id"])]}
                       for cue in cues if str(cue["id"]) in record["translations"]])
    READ_CUES(output)
    report = {"source": str(source.resolve()), "source_sha256": digest(source),
              "output": str(output.resolve()), "output_sha256": digest(output),
              "status": "partial" if missing else "complete_draft",
              "cues": len(cues), "source_cues": len(cues),
              "english_cues": len(record["translations"]),
              "untranslated_source_ids": sorted(int(key) for key in missing),
              "deferred": {key: value for key, value in record["deferred"].items()
                           if key in missing},
              "agent_batches": len(record["batches"]),
              "agent_imports": len(record.get("imports", [])),
              "note": "Agent-authored draft; unresolved source cues are absent from partial export and final release remains blocked."}
    save(output.with_suffix(".agent-translation.json"), report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    showing = actions.add_parser("batch-input")
    showing.add_argument("source", type=Path)
    showing.add_argument("progress", type=Path)
    showing.add_argument("batch", type=int)
    showing.add_argument("--batch-size", type=int, default=12)
    recording = actions.add_parser("apply")
    recording.add_argument("source", type=Path)
    recording.add_argument("progress", type=Path)
    recording.add_argument("response", type=Path)
    importing = actions.add_parser("import", help="save agent-authored cue rows of any size")
    importing.add_argument("source", type=Path)
    importing.add_argument("progress", type=Path)
    importing.add_argument("response", type=Path)
    importing.add_argument("--batch-size", type=int, default=12)
    exporting = actions.add_parser("export")
    exporting.add_argument("source", type=Path)
    exporting.add_argument("progress", type=Path)
    exporting.add_argument("output", type=Path)
    exporting.add_argument("--partial", action="store_true",
                           help="export only settled cues and record excluded source IDs")
    args = parser.parse_args()
    if args.action == "batch-input":
        cues, record = current(args.source, args.progress, args.batch_size)
        print(json.dumps(batch_input(cues, record, args.batch), ensure_ascii=False, indent=2))
    elif args.action == "apply":
        record = apply(args.source, args.progress, args.response)
        print(json.dumps({"translated": len(record["translations"]),
                          "total": record["cue_count"]}))
    elif args.action == "import":
        record = import_responses(args.source, args.progress, args.response,
                                  args.batch_size)
        print(json.dumps({"translated": len(record["translations"]),
                          "deferred": len(record["deferred"]),
                          "total": record["cue_count"]}))
    else:
        print(json.dumps(export(args.source, args.progress, args.output,
                                partial=args.partial)))


if __name__ == "__main__":
    main()
