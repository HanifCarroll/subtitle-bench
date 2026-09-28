#!/usr/bin/env python3
"""Map subtitle utterances and review English meaning against Turkish locally."""

import argparse
import hashlib
import json
import runpy
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


TIMING = runpy.run_path(str(Path(__file__).with_name("subtitle-timing.py")))
read_cues = TIMING["read_cues"]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def save_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def overlap(left, right):
    return min(left["end_ms"], right["end_ms"]) - max(left["start_ms"], right["start_ms"])


def previous_id(previous, kind, cue, used):
    """Keep one stable ID for an unchanged or one-to-one edited utterance."""
    candidates = [item for item in previous.get(kind, [])
                  if item["id"] not in used and len(item["cue_ids"]) == 1]
    exact = [item for item in candidates
             if item["text"] == cue["text"]
             and abs(item["start_ms"] - cue["start"]) <= 1000]
    if len(exact) == 1:
        return exact[0]["id"]

    timed = [item for item in candidates
             if abs(item["start_ms"] - cue["start"]) <= 200
             and abs(item["end_ms"] - cue["end"]) <= 200]
    return timed[0]["id"] if len(timed) == 1 else None


def prepare(source, target, output, previous_path=None):
    """Bootstrap explicit utterance/translation links from cue timings."""

    # 1. Preserve stable IDs when the same utterance is clearly identifiable.

    previous = json.loads(previous_path.read_text()) if previous_path else {}
    source_cues = read_cues(source)
    target_cues = read_cues(target)
    used = set()
    utterances = []
    for cue in source_cues:
        identifier = previous_id(previous, "utterances", cue, used)
        identifier = identifier or f"u{cue['id']:06d}-{cue['start']:09d}"
        if identifier in used:
            raise ValueError("Duplicate source utterance ID")
        used.add(identifier)
        utterances.append({"id": identifier, "text": cue["text"],
                           "start_ms": cue["start"], "end_ms": cue["end"],
                           "cue_ids": [cue["id"]], "evidence": [],
                           "alignment_status": "unreviewed"})

    # 2. Keep English segmentation separate and record provisional links.

    used = set()
    translations = []
    for cue in target_cues:
        identifier = previous_id(previous, "translations", cue, used)
        identifier = identifier or f"t{cue['id']:06d}-{cue['start']:09d}"
        if identifier in used:
            raise ValueError("Duplicate translation ID")
        used.add(identifier)
        interval = {"start_ms": cue["start"], "end_ms": cue["end"]}
        source_ids = [unit["id"] for unit in utterances
                      if overlap(unit, interval) >= 100]
        translations.append({"id": identifier, "text": cue["text"],
                             "start_ms": cue["start"], "end_ms": cue["end"],
                             "cue_ids": [cue["id"]], "source_ids": source_ids,
                             "link_status": "provisional"})

    manifest = {"version": 1, "source": str(source.resolve()),
                "source_sha256": digest(source), "target": str(target.resolve()),
                "target_sha256": digest(target), "utterances": utterances,
                "translations": translations,
                "note": "Cue-based bootstrap is provisional; audio and semantic review establish utterances and links."}
    validate(manifest, source, target)
    save_json(output, manifest)
    return manifest


def validate(manifest, source, target):
    """Reject stale tracks, broken links, and unrepresented display cues."""
    if (manifest.get("version") != 1 or manifest.get("source_sha256") != digest(source)
            or manifest.get("target_sha256") != digest(target)):
        raise ValueError("Utterance map is stale or malformed")
    source_cues = read_cues(source)
    target_cues = read_cues(target)
    source_ids = {cue["id"] for cue in source_cues}
    target_ids = {cue["id"] for cue in target_cues}
    units = manifest.get("utterances")
    translations = manifest.get("translations")
    if not isinstance(units, list) or not isinstance(translations, list):
        raise ValueError("Utterance map needs source units and English translations")
    unit_ids = [item.get("id") for item in units]
    translation_ids = [item.get("id") for item in translations]
    if (len(unit_ids) != len(set(unit_ids))
            or len(translation_ids) != len(set(translation_ids))):
        raise ValueError("Utterance map IDs must be unique")
    mapped_source = set()
    mapped_target = set()
    for item in units:
        if (not isinstance(item.get("text"), str) or not item["text"].strip()
                or not isinstance(item.get("cue_ids"), list)
                or not item["cue_ids"] or not set(item["cue_ids"]) <= source_ids
                or item.get("alignment_status") not in
                ("unreviewed", "aligned", "partial", "failed")):
            raise ValueError("Source utterance is incomplete")
        mapped_source.update(item["cue_ids"])
    for item in translations:
        if (not isinstance(item.get("text"), str) or not item["text"].strip()
                or not isinstance(item.get("cue_ids"), list)
                or not item["cue_ids"] or not set(item["cue_ids"]) <= target_ids
                or not isinstance(item.get("source_ids"), list)
                or not set(item["source_ids"]) <= set(unit_ids)
                or item.get("link_status") not in ("provisional", "confirmed")):
            raise ValueError("English translation has an invalid source link")
        mapped_target.update(item["cue_ids"])
    if mapped_source != source_ids or mapped_target != target_ids:
        raise ValueError("Every display cue must link to an utterance or translation")


def groups(manifest, size):
    if not 1 <= size <= 20:
        raise ValueError("Semantic batch size must be between 1 and 20")
    units = manifest["utterances"]
    translations = manifest["translations"]
    for index in range(0, len(units), size):
        selected = units[index:index + size]
        selected_ids = {item["id"] for item in selected}
        relevant = [item for item in translations
                    if selected_ids.intersection(item["source_ids"])]
        context = units[max(0, index - 3):index]
        context += units[index + size:index + size + 3]
        yield index // size + 1, selected, relevant, context


def review_input(selected, relevant, context, glossary):
    """Exclude display timings so layout edits preserve meaning review."""
    return {"source": [{"id": item["id"], "text": item["text"]}
                       for item in selected],
            "english": [{"id": item["id"], "source_ids": item["source_ids"],
                         "text": item["text"]} for item in relevant],
            "context": [{"id": item["id"], "text": item["text"]}
                        for item in context], "glossary": glossary}


def normalize_assessments(raw_assessments, inputs):
    """Expose omitted model fields as uncertainty instead of losing a batch."""
    if not isinstance(raw_assessments, list) or any(
        not isinstance(item, dict) for item in raw_assessments
    ):
        return None
    expected = {item["id"]: item["text"] for item in inputs["source"]}
    identifiers = [item.get("source_id") for item in raw_assessments]
    if len(identifiers) != len(expected) or set(identifiers) != set(expected):
        return None
    result = []
    for item in raw_assessments:
        assessment = dict(item)
        if assessment.get("verdict") not in ("correct", "material_error", "uncertain"):
            assessment["verdict"] = "uncertain"
            assessment["schema_uncertainty"] = "Model omitted a valid verdict"
        if assessment["verdict"] != "correct":
            assessment.setdefault("source_expression", expected[item["source_id"]])
            related = [translation["text"] for translation in inputs["english"]
                       if item["source_id"] in translation["source_ids"]]
            assessment.setdefault("affected_english", " / ".join(related))
            if not isinstance(assessment.get("audio_needed"), bool):
                assessment["audio_needed"] = None
                assessment["schema_uncertainty"] = "Model omitted audio need"
                assessment["verdict"] = "uncertain"
        result.append(assessment)
    return result


PROMPT = (
    "Review every selected Turkish utterance against the linked English subtitles. "
    "Use surrounding Turkish dialogue and the glossary as context, never as replacements "
    "for the source. Check omissions, additions, negation, people, actions, names, "
    "contextual senses, idioms, jokes, and speaker turns. Flag only a material "
    "meaning change that would mislead a viewer. Accept concise paraphrases, "
    "subtitles split across neighboring cues, and stylistic differences. If context "
    "cannot resolve a sense, use uncertain rather than inventing a scene. "
    "Return compact JSON with exactly one assessment per "
    "selected source ID. A correct assessment has only source_id and verdict=correct. "
    "For material_error or uncertain, also include source_expression, affected_english, "
    "error_type, severity, intended_meaning, explanation, proposed_repair, and "
    "audio_needed. Keep every explanation and repair under 18 words. "
    "Never invent missing audio evidence.\n"
)


def review(manifest_path, output, model, size, glossary_path=None, limit=None,
           retry_invalid=False):
    """Run resumable source-referenced review with a local Ollama model."""

    # 1. Bind each batch to the current dialogue and optional sourced glossary.

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    validate(manifest, Path(manifest["source"]), Path(manifest["target"]))
    glossary = json.loads(glossary_path.read_text()) if glossary_path else []
    if (not isinstance(glossary, list) or len(glossary) > 20
            or any(not isinstance(item, dict) or not all(
                isinstance(item.get(field), str) and item[field].strip()
                for field in ("term", "meaning", "evidence")) for item in glossary)):
        raise ValueError("Glossary needs at most 20 evidence-backed entries")
    output.mkdir(parents=True, exist_ok=True)
    completed = 0
    new_calls = 0
    for number, selected, relevant, context in groups(manifest, size):
        inputs = review_input(selected, relevant, context, glossary)
        identity = fingerprint({"model": model, "prompt": PROMPT, "input": inputs})
        path = output / f"batch-{number:04d}.json"
        if path.exists():
            saved = json.loads(path.read_text(encoding="utf-8"))
            if saved.get("input_sha256") == identity and saved.get("status") == "complete":
                completed += 1
                continue
            if not retry_invalid:
                raise ValueError(f"Stale or invalid semantic batch: {path}")
            archive = path.with_name(path.stem + ".invalid-" +
                                     datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
                                     + path.suffix)
            path.replace(archive)
        if limit is not None and new_calls >= limit:
            break

        # 2. Save raw model output and validate one assessment per utterance.

        request = urllib.request.Request(
            "http://127.0.0.1:11434/api/chat",
            data=json.dumps({"model": model, "messages": [{"role": "user",
                       "content": PROMPT + json.dumps(inputs, ensure_ascii=False)}],
                       "format": "json", "stream": False, "think": False,
                       "options": {"temperature": 0, "num_predict": 1200,
                                   "num_ctx": 8192}}).encode(),
            headers={"Content-Type": "application/json"},
        )
        started = time.monotonic()
        with urllib.request.urlopen(request, timeout=900) as response:
            raw = json.load(response)
        try:
            parsed = json.loads(raw["message"]["content"])
            assessments = normalize_assessments(parsed.get("assessments"), inputs)
        except (AttributeError, KeyError, TypeError, ValueError):
            assessments = None
        expected = {item["id"] for item in selected}
        if (not isinstance(assessments, list)
                or {item.get("source_id") for item in assessments} != expected
                or len(assessments) != len(expected)
                or any(item.get("verdict") not in
                       ("correct", "material_error", "uncertain")
                       for item in assessments)):
            status = "invalid"
        else:
            status = "complete"
        save_json(path, {"status": status, "model": model, "prompt_version": "semantic-v1",
                         "input_sha256": identity, "input": inputs, "response": raw,
                         "response_sha256": fingerprint(raw),
                         "normalized_model_output": any(
                             "schema_uncertainty" in item for item in assessments or []
                         ),
                         "assessments": assessments, "seconds": round(time.monotonic() - started, 3)})
        if status != "complete":
            raise ValueError(f"Semantic model returned incomplete assessments: {path}")
        completed += 1
        new_calls += 1
        print(json.dumps({"batch": number, "reviewed": len(selected),
                          "seconds": round(time.monotonic() - started, 3)}), flush=True)

    return completed


def recover_saved(path):
    """Normalize a saved structured response without repeating a model call."""
    saved = json.loads(path.read_text(encoding="utf-8"))
    if (not isinstance(saved.get("response"), dict)
            or fingerprint(saved["response"]) != saved.get("response_sha256")):
        raise ValueError("Saved semantic response is missing or stale")
    try:
        parsed = json.loads(saved["response"]["message"]["content"])
        assessments = normalize_assessments(parsed.get("assessments"), saved["input"])
    except (AttributeError, KeyError, TypeError, ValueError) as error:
        raise ValueError("Saved response is not complete structured JSON") from error
    if assessments is None:
        raise ValueError("Saved response omits source IDs")
    saved["assessments"] = assessments
    saved["normalized_model_output"] = any(
        "schema_uncertainty" in item for item in assessments
    )
    saved["status"] = "complete"
    save_json(path, saved)
    return len(assessments)


def blockers(manifest_path, review_directory, model, size, glossary_path=None):
    """Require current assessment of every source unit and resolved findings."""
    if not manifest_path.is_file():
        return ["Utterance map is missing"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    try:
        validate(manifest, Path(manifest["source"]), Path(manifest["target"]))
    except (ValueError, OSError) as error:
        return [str(error)]
    linked_source_ids = {identifier for item in manifest["translations"]
                         for identifier in item["source_ids"]}
    missing_links = [item["id"] for item in manifest["utterances"]
                     if item["id"] not in linked_source_ids]
    unlinked_english = [item["id"] for item in manifest["translations"]
                        if not item["source_ids"]]
    glossary = json.loads(glossary_path.read_text()) if glossary_path else []
    pending = 0
    material = 0
    uncertain = 0
    for number, selected, relevant, context in groups(manifest, size):
        path = review_directory / f"batch-{number:04d}.json"
        if not path.is_file():
            pending += len(selected)
            continue
        saved = json.loads(path.read_text(encoding="utf-8"))
        inputs = review_input(selected, relevant, context, glossary)
        identity = fingerprint({"model": model, "prompt": PROMPT,
                                "input": inputs})
        if (saved.get("status") != "complete" or saved.get("input_sha256") != identity
                or saved.get("input") != inputs
                or saved.get("model") != model
                or saved.get("prompt_version") != "semantic-v1"
                or not isinstance(saved.get("response"), dict)
                or saved.get("response_sha256") != fingerprint(saved["response"])):
            pending += len(selected)
            continue
        assessments = saved.get("assessments", [])
        try:
            raw_assessments = json.loads(saved["response"]["message"]["content"])[
                "assessments"]
            normalized = normalize_assessments(raw_assessments, inputs)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            normalized = None
        if (assessments != normalized or not isinstance(assessments, list)
                or {item.get("source_id") for item in assessments}
                != {item["id"] for item in selected}
                or len(assessments) != len(selected)
                or any(item.get("verdict") not in
                       ("correct", "material_error", "uncertain")
                       for item in assessments)):
            pending += len(selected)
            continue
        material += sum(item.get("verdict") == "material_error" for item in assessments)
        uncertain += sum(item.get("verdict") == "uncertain" for item in assessments)
    failures = []
    if missing_links:
        failures.append(f"{len(missing_links)} source utterances lack English links")
    if unlinked_english:
        failures.append(f"{len(unlinked_english)} English translations lack source links")
    if pending:
        failures.append(f"{pending} source utterances need current English semantic review")
    if material:
        failures.append(f"{material} English meaning errors need repair and recheck")
    if uncertain:
        failures.append(f"{uncertain} English meanings need adjudication")
    return failures


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    prepared = commands.add_parser("prepare")
    for command in (prepared,):
        command.add_argument("source", type=Path)
        command.add_argument("target", type=Path)
    prepared.add_argument("output", type=Path)
    prepared.add_argument("--previous", type=Path)
    reviewing = commands.add_parser("review")
    reviewing.add_argument("manifest", type=Path)
    reviewing.add_argument("output", type=Path)
    reviewing.add_argument("--model", default="qwen3.5:27b")
    reviewing.add_argument("--batch-size", type=int, default=12)
    reviewing.add_argument("--glossary", type=Path)
    reviewing.add_argument("--limit", type=int)
    reviewing.add_argument("--retry-invalid", action="store_true")
    checking = commands.add_parser("check")
    checking.add_argument("manifest", type=Path)
    checking.add_argument("reviews", type=Path)
    checking.add_argument("--model", default="qwen3.5:27b")
    checking.add_argument("--batch-size", type=int, default=12)
    checking.add_argument("--glossary", type=Path)
    recovering = commands.add_parser("recover")
    recovering.add_argument("batch", type=Path)
    args = parser.parse_args()
    if args.action == "prepare":
        result = prepare(args.source, args.target, args.output, args.previous)
        print(json.dumps({"utterances": len(result["utterances"]),
                          "translations": len(result["translations"]),
                          "manifest": str(args.output)}))
    elif args.action == "review":
        print(json.dumps({"completed_batches": review(
            args.manifest, args.output, args.model, args.batch_size,
            args.glossary, args.limit, args.retry_invalid)}))
    elif args.action == "recover":
        print(json.dumps({"recovered": recover_saved(args.batch)}))
    else:
        failures = blockers(args.manifest, args.reviews, args.model,
                            args.batch_size, args.glossary)
        print(json.dumps({"complete": not failures, "blockers": failures}))


if __name__ == "__main__":
    main()
