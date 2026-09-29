#!/usr/bin/env python3
"""Map subtitle utterances and bind agent-reviewed English meaning to the tracks."""

import argparse
import hashlib
import json
import re
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
    same_cue = [item for item in candidates
                if item["cue_ids"] == [cue["id"]] and item["text"] == cue["text"]
                and abs(item["start_ms"] - cue["start"]) <= 10_000]
    if len(same_cue) == 1:
        return same_cue[0]["id"]
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
        if not source_ids:
            source_ids = [unit["id"] for unit in utterances
                          if unit["cue_ids"] == [cue["id"]]
                          and unit["start_ms"] == cue["start"]
                          and unit["end_ms"] == cue["end"]]
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

    # A reviewed map may group or split display cues, but it must contain the
    # exact words and punctuation that the linked SRT will deliver. Only
    # whitespace may change across cue and line boundaries.
    for name, items, cues in (("Turkish", units, source_cues),
                              ("English", translations, target_cues)):
        reviewed = " ".join(item["text"] for item in items).split()
        delivered = " ".join(cue["text"] for cue in cues).split()
        if reviewed != delivered:
            raise ValueError(f"{name} utterance-map text differs from linked SRT")
        positions = {cue["id"]: index for index, cue in enumerate(cues)}
        prior = -1
        for item in items:
            indices = [positions[identifier] for identifier in item["cue_ids"]]
            if indices != sorted(indices) or indices[0] < prior:
                raise ValueError(f"{name} cue links are out of display order")
            prior = indices[-1]
        by_cue = {cue["id"]: [] for cue in cues}
        for index, item in enumerate(items):
            for cue_id in item["cue_ids"]:
                by_cue[cue_id].append(index)
        visited = set()
        for start in range(len(items)):
            if start in visited:
                continue
            pending = [start]
            component_items = set()
            component_cues = set()
            while pending:
                index = pending.pop()
                if index in component_items:
                    continue
                component_items.add(index)
                for cue_id in items[index]["cue_ids"]:
                    component_cues.add(cue_id)
                    pending.extend(by_cue[cue_id])
            visited.update(component_items)
            reviewed_group = " ".join(items[index]["text"]
                                      for index in sorted(component_items)).split()
            delivered_group = " ".join(cue["text"] for cue in cues
                                       if cue["id"] in component_cues).split()
            if reviewed_group != delivered_group:
                raise ValueError(f"{name} cue-linked text differs from linked SRT")


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
    """Expose omitted model fields or units as uncertainty, keeping raw output."""
    if not isinstance(raw_assessments, list) or any(
        not isinstance(item, dict) for item in raw_assessments
    ):
        return None
    expected = {item["id"]: item["text"] for item in inputs["source"]}
    identifiers = [item.get("source_id") for item in raw_assessments]
    if (any(not isinstance(identifier, str) for identifier in identifiers)
            or len(identifiers) != len(set(identifiers))
            or not set(identifiers) <= set(expected)):
        return None
    by_id = {item["source_id"]: item for item in raw_assessments}
    result = []
    for source_id in expected:
        if source_id not in by_id:
            related = [translation["text"] for translation in inputs["english"]
                       if source_id in translation["source_ids"]]
            result.append({"source_id": source_id, "verdict": "uncertain",
                           "source_expression": expected[source_id],
                           "affected_english": " / ".join(related),
                           "error_type": "missing_assessment", "severity": "unknown",
                           "intended_meaning": None,
                           "explanation": "Reviewer omitted this source ID; agent review required",
                           "proposed_repair": None, "audio_needed": None,
                           "schema_uncertainty": "Model omitted assessment"})
            continue
        item = by_id[source_id]
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


def response_assessments(response):
    """Keep complete objects from a token-truncated JSON response as evidence."""
    content = response["message"]["content"]
    try:
        return json.loads(content)["assessments"]
    except json.JSONDecodeError:
        if response.get("done_reason") != "length":
            raise
    prefix = re.match(r'\s*\{\s*"assessments"\s*:\s*\[', content)
    if not prefix:
        raise ValueError("Truncated response has no assessments array")
    decoder = json.JSONDecoder()
    position = prefix.end()
    complete = []
    while position < len(content):
        while position < len(content) and content[position] in " \n\r\t,":
            position += 1
        if position == len(content) or content[position] == "]":
            break
        try:
            item, position = decoder.raw_decode(content, position)
        except json.JSONDecodeError:
            break
        if not isinstance(item, dict):
            raise ValueError("Truncated assessment is malformed")
        complete.append(item)
    if not complete:
        raise ValueError("Truncated response has no complete assessment")
    return complete


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
           retry_invalid=False, batch_numbers=None):
    """Legacy saved-review runner; agent-authored reviews are the release source."""

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
        if batch_numbers is not None and number not in batch_numbers:
            continue
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
                       "options": {"temperature": 0, "num_predict": 2400,
                                   "num_ctx": 8192}}).encode(),
            headers={"Content-Type": "application/json"},
        )
        started = time.monotonic()
        with urllib.request.urlopen(request, timeout=900) as response:
            raw = json.load(response)
        try:
            assessments = normalize_assessments(response_assessments(raw), inputs)
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


def agent_assessments(authored, selected):
    """Require an explicit judgment for each current source ID."""
    correct_ids = authored.get("correct_ids")
    findings = authored.get("findings")
    if (not isinstance(correct_ids, list) or not isinstance(findings, list)
            or any(not isinstance(item, str) for item in correct_ids)
            or any(not isinstance(item, dict) for item in findings)):
        raise ValueError("Agent review needs explicit correct IDs and findings")
    expected = [item["id"] for item in selected]
    finding_ids = [item.get("source_id") for item in findings]
    if (len(correct_ids + finding_ids) != len(expected)
            or len(set(correct_ids + finding_ids)) != len(expected)
            or set(correct_ids + finding_ids) != set(expected)):
        raise ValueError("Agent review must assess every source ID exactly once")
    for finding in findings:
        if (finding.get("verdict") not in ("material_error", "uncertain")
                or not isinstance(finding.get("reason"), str)
                or not finding["reason"].strip()):
            raise ValueError("Agent finding needs a verdict and specific reason")
    by_id = {item["source_id"]: item for item in findings}
    return [by_id.get(identifier, {"source_id": identifier,
                                   "verdict": "correct"})
            for identifier in expected]


def record_agent_review(manifest_path, directory, authored_path, size,
                        glossary_path=None):
    """Record explicit agent judgments for every source unit in one current batch."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    validate(manifest, Path(manifest["source"]), Path(manifest["target"]))
    authored = json.loads(authored_path.read_text(encoding="utf-8"))
    number = authored.get("batch_number")
    if type(number) is not int or number < 1:
        raise ValueError("Agent review needs a batch number")
    group = next((values for values in groups(manifest, size)
                  if values[0] == number), None)
    if group is None:
        raise ValueError("Agent review names an unknown batch")
    _, selected, relevant, context = group
    glossary = json.loads(glossary_path.read_text()) if glossary_path else []
    inputs = review_input(selected, relevant, context, glossary)
    input_sha256 = fingerprint(inputs)
    if authored.get("review_input_sha256") != input_sha256:
        raise ValueError("Agent review input fingerprint is missing or stale")
    reviewer = authored.get("reviewer")
    if not isinstance(reviewer, str) or not reviewer.strip():
        raise ValueError("Agent review needs an identified reviewer")
    assessments = agent_assessments(authored, selected)
    path = directory / f"agent-batch-{number:04d}.json"
    if authored_path.resolve() == path.resolve():
        raise ValueError("Keep authored judgments separate from the review receipt")
    if path.exists():
        old = json.loads(path.read_text(encoding="utf-8"))
        archive = directory / (f"agent-batch-{number:04d}.prior-"
                               f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')}.json")
        save_json(archive, old)
    save_json(path, {"status": "complete", "reviewer": reviewer,
                     "reviewed_at": datetime.now(timezone.utc).isoformat(),
                     "batch_number": number, "input": inputs,
                     "input_sha256": input_sha256,
                     "authored_path": str(authored_path.resolve()),
                     "authored_sha256": digest(authored_path),
                     "assessments": assessments})
    return path


def recover_saved(path):
    """Expose omissions in a saved response without repeating a model call."""
    saved = json.loads(path.read_text(encoding="utf-8"))
    if (not isinstance(saved.get("response"), dict)
            or fingerprint(saved["response"]) != saved.get("response_sha256")):
        raise ValueError("Saved semantic response is missing or stale")
    try:
        assessments = normalize_assessments(response_assessments(saved["response"]),
                                            saved["input"])
    except (AttributeError, KeyError, TypeError, ValueError) as error:
        raise ValueError("Saved response has no usable structured assessments") from error
    if assessments is None:
        raise ValueError("Saved response omits source IDs")
    saved["assessments"] = assessments
    saved["normalized_model_output"] = any(
        "schema_uncertainty" in item for item in assessments
    )
    saved["status"] = "complete"
    save_json(path, saved)
    return len(assessments)


def current_finding(manifest, review_directory, model, size, glossary, source_id):
    """Find a valid raw assessment for one current source utterance."""
    for number, selected, relevant, context in groups(manifest, size):
        if source_id not in {item["id"] for item in selected}:
            continue
        inputs = review_input(selected, relevant, context, glossary)
        identity = fingerprint({"model": model, "prompt": PROMPT, "input": inputs})
        path = review_directory / f"batch-{number:04d}.json"
        if not path.is_file():
            raise ValueError(f"Current semantic batch is missing: {path}")
        saved = json.loads(path.read_text(encoding="utf-8"))
        if (saved.get("status") != "complete" or saved.get("model") != model
                or saved.get("prompt_version") != "semantic-v1"
                or saved.get("input_sha256") != identity
                or saved.get("input") != inputs
                or saved.get("response_sha256") != fingerprint(saved.get("response"))):
            raise ValueError(f"Current semantic batch is stale: {path}")
        try:
            raw = response_assessments(saved["response"])
            normalized = normalize_assessments(raw, inputs)
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(f"Current semantic batch is malformed: {path}") from error
        if normalized != saved.get("assessments"):
            raise ValueError(f"Current semantic batch was altered: {path}")
        assessment = next(item for item in normalized
                          if item["source_id"] == source_id)
        return path, saved, inputs, assessment
    raise ValueError(f"Unknown source utterance: {source_id}")


def adjudication_path(review_directory, source_id):
    return review_directory / "adjudications" / (fingerprint(source_id) + ".json")


def evidence_is_current(evidence, question_type):
    if not isinstance(evidence, list) or not evidence:
        return False
    if question_type == "source_recognition" and not any(
            item.get("kind") == "original_audio" for item in evidence
            if isinstance(item, dict)):
        return False
    return all(isinstance(item, dict)
               and item.get("kind") in ("source_text", "scene_context",
                                        "original_audio", "model_receipt", "other")
               and isinstance(item.get("path"), str)
               and Path(item["path"]).is_file()
               and item.get("sha256") == digest(Path(item["path"]))
               for item in evidence)


def current_adjudication(record, saved, inputs, assessment):
    """A disposition expires with the finding, context, or cited evidence."""
    return (isinstance(record, dict)
            and record.get("source_id") == assessment["source_id"]
            and record.get("input_sha256") == saved["input_sha256"]
            and record.get("response_sha256") == saved["response_sha256"]
            and record.get("finding_sha256") == fingerprint(assessment)
            and record.get("review_context") == inputs
            and record.get("finding") == assessment
            and record.get("disposition") == "supported_as_written"
            and record.get("question_type") in
            ("translation_semantics", "source_recognition")
            and isinstance(record.get("reviewer"), str)
            and bool(record["reviewer"].strip())
            and isinstance(record.get("reason"), str)
            and bool(record["reason"].strip())
            and evidence_is_current(record.get("evidence"),
                                    record["question_type"]))


def current_agent_batch(path, number, inputs, selected):
    """Verify the agent's explicit judgments and their authored source file."""
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
        authored_path = Path(saved.get("authored_path", ""))
        if (not authored_path.is_file()
                or saved.get("authored_sha256") != digest(authored_path)):
            return None
        authored = json.loads(authored_path.read_text(encoding="utf-8"))
        if (saved.get("status") != "complete"
                or saved.get("batch_number") != number
                or authored.get("batch_number") != number
                or authored.get("review_input_sha256") != fingerprint(inputs)
                or saved.get("reviewer") != authored.get("reviewer")
                or not isinstance(saved.get("reviewer"), str)
                or not saved["reviewer"].strip()
                or saved.get("input") != inputs
                or saved.get("input_sha256") != fingerprint(inputs)
                or saved.get("assessments") != agent_assessments(authored, selected)):
            return None
        return saved["assessments"]
    except (OSError, ValueError, TypeError, KeyError):
        return None


def adjudicate(manifest_path, review_directory, decision_path, model, size,
               glossary_path=None):
    """Record an agent decision beside the untouched model response."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    validate(manifest, Path(manifest["source"]), Path(manifest["target"]))
    glossary = json.loads(glossary_path.read_text()) if glossary_path else []
    decision = json.loads(decision_path.read_text(encoding="utf-8"))
    source_id = decision.get("source_id")
    path, saved, inputs, assessment = current_finding(
        manifest, review_directory, model, size, glossary, source_id
    )
    disposition = decision.get("disposition")
    if disposition not in ("supported_as_written", "repaired_rechecked", "unresolved"):
        raise ValueError("Unknown semantic disposition")
    if (decision.get("question_type") not in
            ("translation_semantics", "source_recognition")
            or not isinstance(decision.get("reviewer"), str)
            or not decision["reviewer"].strip()
            or not isinstance(decision.get("reason"), str)
            or not decision["reason"].strip()
            or not evidence_is_current(decision.get("evidence"),
                                       decision["question_type"])):
        raise ValueError("Semantic decision needs a reviewer, reason, and current evidence")
    if disposition == "repaired_rechecked":
        if assessment["verdict"] != "correct":
            raise ValueError("A repaired translation needs a current correct recheck")
        prior_path = Path(decision.get("prior_review", ""))
        if not prior_path.is_file() or prior_path.resolve() == path.resolve():
            raise ValueError("Repair needs the saved earlier finding")
        prior = json.loads(prior_path.read_text(encoding="utf-8"))
        if (prior.get("response_sha256") != fingerprint(prior.get("response"))
                or prior.get("status") != "complete"):
            raise ValueError("Earlier finding is not intact")
        prior_assessment = next((item for item in prior.get("assessments", [])
                                 if item.get("source_id") == source_id), None)
        if (not prior_assessment or prior_assessment.get("verdict") not in
                ("material_error", "uncertain")
                or prior.get("input") == inputs):
            raise ValueError("Repair needs a changed, previously flagged input")
        prior_binding = {"path": str(prior_path.resolve()),
                         "sha256": digest(prior_path),
                         "finding": prior_assessment}
    elif assessment["verdict"] == "correct":
        raise ValueError("A current correct assessment needs no false-alarm decision")
    else:
        prior_binding = None
    record = {"version": 1, "source_id": source_id,
              "disposition": disposition, "question_type": decision["question_type"],
              "reviewer": decision["reviewer"], "reason": decision["reason"],
              "evidence": decision["evidence"], "batch": str(path.resolve()),
              "input_sha256": saved["input_sha256"],
              "response_sha256": saved["response_sha256"],
              "finding_sha256": fingerprint(assessment),
              "review_context": inputs, "finding": assessment,
              "prior_finding": prior_binding}
    output = adjudication_path(review_directory, source_id)
    save_json(output, record)
    return output


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
        inputs = review_input(selected, relevant, context, glossary)
        if model == "agent":
            path = review_directory / f"agent-batch-{number:04d}.json"
            assessments = current_agent_batch(path, number, inputs, selected)
            if assessments is None:
                pending += len(selected)
                continue
            material += sum(item["verdict"] == "material_error"
                            for item in assessments)
            uncertain += sum(item["verdict"] == "uncertain"
                             for item in assessments)
            continue
        path = review_directory / f"batch-{number:04d}.json"
        if not path.is_file():
            pending += len(selected)
            continue
        saved = json.loads(path.read_text(encoding="utf-8"))
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
            raw_assessments = response_assessments(saved["response"])
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
        for assessment in assessments:
            if assessment["verdict"] == "correct":
                continue
            decision_path = adjudication_path(review_directory,
                                              assessment["source_id"])
            if decision_path.is_file():
                decision = json.loads(decision_path.read_text(encoding="utf-8"))
                if current_adjudication(decision, saved, inputs, assessment):
                    continue
            if assessment["verdict"] == "material_error":
                material += 1
            else:
                uncertain += 1
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
        failures.append(f"{uncertain} semantic review findings need adjudication")
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
    reviewing = commands.add_parser("review", help="record one agent-reviewed batch")
    reviewing.add_argument("manifest", type=Path)
    reviewing.add_argument("output", type=Path)
    reviewing.add_argument("--batch-size", type=int, default=12)
    reviewing.add_argument("--glossary", type=Path)
    reviewing.add_argument("--agent-input", type=Path, required=True)
    showing = commands.add_parser("review-input", help="show one current batch for agent review")
    showing.add_argument("manifest", type=Path)
    showing.add_argument("batch_number", type=int)
    showing.add_argument("--batch-size", type=int, default=12)
    showing.add_argument("--glossary", type=Path)
    checking = commands.add_parser("check")
    checking.add_argument("manifest", type=Path)
    checking.add_argument("reviews", type=Path)
    checking.add_argument("--model", default="agent")
    checking.add_argument("--batch-size", type=int, default=12)
    checking.add_argument("--glossary", type=Path)
    recovering = commands.add_parser("recover")
    recovering.add_argument("batch", type=Path)
    adjudicating = commands.add_parser("adjudicate")
    adjudicating.add_argument("manifest", type=Path)
    adjudicating.add_argument("reviews", type=Path)
    adjudicating.add_argument("decision", type=Path)
    adjudicating.add_argument("--model", default="qwen3.5:27b")
    adjudicating.add_argument("--batch-size", type=int, default=12)
    adjudicating.add_argument("--glossary", type=Path)
    args = parser.parse_args()
    if args.action == "prepare":
        result = prepare(args.source, args.target, args.output, args.previous)
        print(json.dumps({"utterances": len(result["utterances"]),
                          "translations": len(result["translations"]),
                          "manifest": str(args.output)}))
    elif args.action == "review":
        path = record_agent_review(args.manifest, args.output, args.agent_input,
                                   args.batch_size, args.glossary)
        print(json.dumps({"agent_review": str(path)}))
    elif args.action == "review-input":
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        validate(manifest, Path(manifest["source"]), Path(manifest["target"]))
        group = next((item for item in groups(manifest, args.batch_size)
                      if item[0] == args.batch_number), None)
        if group is None:
            raise ValueError("Agent review names an unknown batch")
        glossary = json.loads(args.glossary.read_text(encoding="utf-8")) if args.glossary else []
        inputs = review_input(*group[1:], glossary)
        print(json.dumps({"batch_number": args.batch_number,
                          "review_input_sha256": fingerprint(inputs),
                          "input": inputs}, ensure_ascii=False))
    elif args.action == "recover":
        print(json.dumps({"recovered": recover_saved(args.batch)}))
    elif args.action == "adjudicate":
        path = adjudicate(args.manifest, args.reviews, args.decision,
                          args.model, args.batch_size, args.glossary)
        print(json.dumps({"adjudication": str(path)}))
    else:
        failures = blockers(args.manifest, args.reviews, args.model,
                            args.batch_size, args.glossary)
        print(json.dumps({"complete": not failures, "blockers": failures}))


if __name__ == "__main__":
    main()
