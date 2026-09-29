#!/usr/bin/env python3
"""Checkpoint agent-authored English drafts without calling a text model."""

import argparse
import hashlib
import json
import runpy
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


def current(source, progress, batch_size):
    source = source.resolve(strict=True)
    cues = READ_CUES(source)
    if not cues or not 1 <= batch_size <= 30:
        raise ValueError("Source needs cues and batch size must be 1-30")
    identity = {"version": 1, "source": str(source),
                "source_sha256": digest(source), "batch_size": batch_size,
                "cue_count": len(cues)}
    if progress.exists():
        record = json.loads(progress.read_text(encoding="utf-8"))
        if any(record.get(key) != value for key, value in identity.items()):
            raise ValueError("Translation progress belongs to another source version")
    else:
        record = {**identity, "translations": {}, "batches": {}}
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
        "instruction": "Translate each selected Turkish cue into natural, faithful English. Use context; do not omit or invent spoken meaning. Return every selected cue ID once.",
    }
    payload["input_sha256"] = fingerprint(payload)
    payload["completed"] = str(number) in record["batches"]
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
        if not isinstance(row.get("text"), str) or not row["text"].strip():
            raise ValueError("English translation cannot be blank")
    key = str(number)
    saved = {str(row["cue_id"]): row["text"].strip() for row in rows}
    if key in record["batches"]:
        if record["batches"][key]["translations"] != saved:
            raise ValueError("Completed batch differs; preserve it and start a new revision")
        return record
    record["translations"].update(saved)
    record["batches"][key] = {
        "reviewer": authored["reviewer"],
        "input_sha256": expected["input_sha256"],
        "response_sha256": digest(response),
        "translations": saved, "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    save(progress, record)
    return record


def export(source, progress, output):
    record = json.loads(progress.read_text(encoding="utf-8"))
    cues, record = current(source, progress, record["batch_size"])
    if output.exists() or output.suffix.lower() != ".srt":
        raise ValueError("Use a new English .srt output")
    expected = {str(cue["id"]) for cue in cues}
    if set(record["translations"]) != expected:
        raise ValueError(f"English draft is incomplete: {len(expected - set(record['translations']))} cues remain")
    output.parent.mkdir(parents=True, exist_ok=True)
    WRITE_SRT(output, [{"start_ms": cue["start"], "end_ms": cue["end"],
                        "text": record["translations"][str(cue["id"])]}
                       for cue in cues])
    READ_CUES(output)
    report = {"source": str(source.resolve()), "source_sha256": digest(source),
              "output": str(output.resolve()), "output_sha256": digest(output),
              "cues": len(cues), "agent_batches": len(record["batches"]),
              "note": "Agent-authored draft; source and English meaning still need review."}
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
    exporting = actions.add_parser("export")
    exporting.add_argument("source", type=Path)
    exporting.add_argument("progress", type=Path)
    exporting.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.action == "batch-input":
        cues, record = current(args.source, args.progress, args.batch_size)
        print(json.dumps(batch_input(cues, record, args.batch), ensure_ascii=False, indent=2))
    elif args.action == "apply":
        record = apply(args.source, args.progress, args.response)
        print(json.dumps({"translated": len(record["translations"]),
                          "total": record["cue_count"]}))
    else:
        print(json.dumps(export(args.source, args.progress, args.output)))


if __name__ == "__main__":
    main()
