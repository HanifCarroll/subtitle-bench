#!/usr/bin/env python3
"""Translate one source-language SRT to English with DeepSeek Flash."""

import argparse
import concurrent.futures
import fcntl
import hashlib
import json
import os
import runpy
import time
import urllib.request
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parent
READ_CUES = runpy.run_path(str(SCRIPTS / "subtitle-timing.py"))["read_cues"]
WRITE_SRT = runpy.run_path(str(SCRIPTS / "join-clip-drafts.py"))["write_srt"]
SEMANTIC = runpy.run_path(str(SCRIPTS / "semantic-review.py"))
DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-flash"
ENV_FILE = Path.home() / ".config/subtitle-workflow/.env"


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_translation(items, target):
    expected = {cue["id"] for cue in target}
    if not isinstance(items, list) or len(items) != len(target):
        raise ValueError("Translation has the wrong number of cues")

    translated = {}
    for item in items:
        if not isinstance(item, dict) or type(item.get("id")) is not int:
            raise ValueError("Translation cue needs a numeric ID")
        cue_id = item["id"]
        value = item.get("text")
        if cue_id in translated or not isinstance(value, str) or not value.strip():
            raise ValueError("Translation has a duplicate or empty cue")
        if "-->" in value or "\x00" in value:
            raise ValueError("Translation contains invalid SRT text")
        translated[cue_id] = value.replace("\r", "").strip()

    if set(translated) != expected:
        raise ValueError("Translation cue IDs do not match the source")

    return translated


def deepseek_key():
    # 1. Read the private credential file without sending the key to logs or subprocesses.

    if ENV_FILE.stat().st_mode & 0o077:
        raise PermissionError("DeepSeek .env must be readable only by its owner")
    lines = ENV_FILE.read_text(encoding="utf-8").splitlines()
    matches = [line.removeprefix("DEEPSEEK_API_KEY=") for line in lines
               if line.startswith("DEEPSEEK_API_KEY=")]
    if len(matches) != 1 or not matches[0].startswith("sk-"):
        raise RuntimeError("DeepSeek credential is unavailable in the private .env file")

    return matches[0]


def request_translation(prompt, context, max_tokens=8192):
    # 1. Send one paid request without an automatic retry.

    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
    ]
    body = {
        "model": MODEL, "temperature": 0, "thinking": {"type": "disabled"},
        "max_tokens": max_tokens, "response_format": {"type": "json_object"},
        "messages": messages,
    }
    headers = {"Content-Type": "application/json",
               "Authorization": f"Bearer {deepseek_key()}"}
    request = urllib.request.Request(
        DEEPSEEK_URL, data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers=headers,
    )
    with urllib.request.urlopen(request, timeout=600) as response:
        payload = json.load(response)

    # 2. Return the full payload so raw output survives a completion/validation failure.

    choice = payload["choices"][0]
    return choice["message"]["content"], payload.get("usage", {}), payload


def translation_prompt(language, glossary=None):
    return (
        f"Translate {language} dialogue subtitles into faithful English. "
        'Return JSON only: {"cues":[{"id":1,"text":"English subtitle"}]}. '
        "Return each target cue exactly once with its original ID. Previous and next cues "
        "are context only. Preserve spoken details, speaker turns, genuine repetition, "
        "names, songs, insults, and jokes. Do not invent speech or shorten it to fit "
        "a reading-speed limit. Use natural English; do not add notes or timestamps. "
        + ("Terminology/context: " + glossary if glossary else "")
    )


def batch_context(cues, start, size):
    return {name: [{"id": cue["id"], "text": cue["text"]} for cue in group]
            for name, group in {"previous": cues[max(0, start - 4):start],
                                "target": cues[start:start + size],
                                "next": cues[start + size:start + size + 4]}.items()}


def batches(cues, size, token_budget, prompt):
    """Bound input conservatively by UTF-8 bytes, without a tokenizer dependency."""
    # ponytail: smaller batches from the byte bound; add a tokenizer if throughput matters.
    start = 0
    while start < len(cues):
        count = min(size, len(cues) - start)
        while count > 0:
            context = batch_context(cues, start, count)
            if len((prompt + json.dumps(context, ensure_ascii=False)).encode()) <= token_budget:
                break
            count -= 1
        if count == 0:
            raise ValueError("One cue plus surrounding context exceeds the input token budget")
        yield start, count, context
        start += count


def translate_batch(cues, start, size, language):
    response_text, usage, payload = request_translation(translation_prompt(language),
                                                       batch_context(cues, start, size))
    if payload["choices"][0]["finish_reason"] != "stop":
        raise ValueError("DeepSeek stopped before completing the batch")
    return validate_translation(json.loads(response_text)["cues"], cues[start:start + size]), [usage]


def generate_batch(path, identity, prompt, context, max_tokens):
    """Save raw output before validation; a crash can resume without another call."""
    if path.exists():
        raw = json.loads(path.read_text(encoding="utf-8"))
        if raw.get("input_sha256") != identity:
            raise ValueError("Cached translation batch is stale")
        if raw.get("status") != "response_saved":
            raise ValueError("Prior request has no response; inspect it before authorizing a retry")
    else:
        save_json(path, {"input_sha256": identity, "status": "attempted",
                         "prompt": prompt, "input": context, "max_tokens": max_tokens})
        started = time.monotonic()
        text, usage, payload = request_translation(prompt, context, max_tokens)
        raw = {"input_sha256": identity, "status": "response_saved", "prompt": prompt,
               "input": context, "max_tokens": max_tokens, "raw_text": text,
               "usage": usage, "provider_response": payload, "seconds": round(time.monotonic() - started, 3)}
        save_json(path, raw)
    if raw["provider_response"]["choices"][0]["finish_reason"] != "stop":
        raise ValueError("DeepSeek stopped before completing the batch; raw response retained")
    translated = validate_translation(json.loads(raw["raw_text"])["cues"], context["target"])
    return translated, raw


def save_json(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def translation_targets(source, utterance_map):
    """Return source units and IDs without tying English to Turkish cue boundaries."""
    if utterance_map is None:
        return READ_CUES(source), None

    manifest = json.loads(utterance_map.read_text(encoding="utf-8"))
    SEMANTIC["validate"](manifest, source, Path(manifest["target"]))
    units = manifest["utterances"]
    cues = [{"id": index, "text": unit["text"],
             "start": unit["start_ms"], "end": unit["end_ms"]}
            for index, unit in enumerate(units, start=1)]
    return cues, [unit["id"] for unit in units]


def translate(args):
    # A second process must not race this run's serialized checkpoint writer.
    lock_path = args.output.with_suffix(".translation.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return translate_locked(args)


def translate_locked(args):
    # 1. Bind resumable progress to the exact source text, language, and model.

    source = args.source.resolve(strict=True)
    output = args.output.resolve()
    utterance_map = getattr(args, "utterance_map", None)
    expected_suffix = ".json" if utterance_map else ".srt"
    if source == output or output.exists() or output.suffix.lower() != expected_suffix:
        raise ValueError(f"Use a new {expected_suffix} output path separate from the source")
    if not args.source_language.isalpha() or not 2 <= len(args.source_language) <= 8:
        raise ValueError("Use a source-language code such as tr")
    if not 1 <= args.batch_size <= 300:
        raise ValueError("Batch size must be 1-300 source units")

    concurrency = getattr(args, "concurrency", 4)
    token_budget = getattr(args, "input_token_budget", 6000)
    max_tokens = getattr(args, "max_output_tokens", 8192)
    if not 1 <= concurrency <= 4 or token_budget < 1000 or not 1024 <= max_tokens <= 32768:
        raise ValueError("Use concurrency 1-4, input budget >=1000 and output tokens 1024-32768")
    ready = getattr(args, "ready", None)
    if ready:
        runpy.run_path(str(SCRIPTS / "source-review.py"))["check_ready"](source, ready)
    glossary_path = getattr(args, "glossary", None)
    glossary = glossary_path.read_text(encoding="utf-8") if glossary_path else None
    prompt = translation_prompt(args.source_language.lower(), glossary)
    output.parent.mkdir(parents=True, exist_ok=True)
    source_sha256 = file_hash(source)
    map_sha256 = file_hash(utterance_map) if utterance_map else None
    cues, source_unit_ids = translation_targets(source, utterance_map)
    if (file_hash(source) != source_sha256 or
            (utterance_map and file_hash(utterance_map) != map_sha256)):
        raise ValueError("Translation inputs changed while reading them; no calls made")
    progress_path = output.with_suffix(".progress.json")
    report_path = output.with_suffix(".translation.json")
    if report_path.exists():
        raise FileExistsError(f"Translation report already exists: {report_path}")
    settings = {
        "source": str(source), "source_sha256": source_sha256,
        "source_language": args.source_language.lower(),
        "target_language": "en", "provider": "deepseek", "model": MODEL,
        "batch_size": args.batch_size, "prompt": prompt,
        "input_token_budget": token_budget, "max_output_tokens": max_tokens,
        "temperature": 0, "thinking": "disabled", "response_format": "json_object",
        "utterance_map_sha256": map_sha256,
    }
    progress = (
        json.loads(progress_path.read_text(encoding="utf-8"))
        if progress_path.exists() else {**settings, "texts": {}, "batch_seconds": [], "usage": [], "completed_batches": {}}
    )
    if any(progress.get(key) != value for key, value in settings.items()):
        raise ValueError("Translation progress belongs to another source or model")

    # 2. Save each complete batch, allowing a stopped run to resume.

    jobs = list(batches(cues, args.batch_size, token_budget, prompt))
    input_rate = getattr(args, "input_usd_per_million", 0.30)
    output_rate = getattr(args, "output_usd_per_million", 1.20)
    cost_ceiling = getattr(args, "max_estimated_usd", None)
    upper_cost = sum((len((prompt + json.dumps(context, ensure_ascii=False)).encode()) + 1000)
                     * input_rate + max_tokens * output_rate for _, _, context in jobs) / 1_000_000
    if input_rate <= 0 or output_rate <= 0 or (cost_ceiling is not None and upper_cost > cost_ceiling):
        raise ValueError("Translation exceeds estimated cost cap or has invalid pricing; no calls made")
    raw_directory = output.with_suffix(".batches")
    raw_directory.mkdir(exist_ok=True)
    failures = []
    started = time.monotonic()
    pending = []
    # Validate every saved batch before scheduling any paid work.
    for start, count, context in jobs:
        identity = SEMANTIC["fingerprint"]({"settings": settings, "input": context})
        key = str(start)
        saved = progress["completed_batches"].get(key)
        if saved is not None:
            if saved != identity:
                raise ValueError("Translation checkpoint batch identity changed")
            validate_translation([{"id": cue["id"], "text": progress["texts"][str(cue["id"])]}
                                  for cue in context["target"]], context["target"])
            continue
        pending.append((raw_directory / f"{start:06d}.json", key, identity, context))
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = {pool.submit(generate_batch, path, identity, prompt, context, max_tokens): (key, identity)
                   for path, key, identity, context in pending}
        for future in concurrent.futures.as_completed(futures):
            key, identity = futures[future]
            try:
                translated, raw = future.result()
            except Exception as error:
                failures.append(f"Batch {key}: {type(error).__name__}: {error}")
                continue
            # Only this coordinator thread writes shared progress.
            progress["texts"].update({str(key): value for key, value in translated.items()})
            progress["completed_batches"][key] = identity
            progress["batch_seconds"].append(raw["seconds"])
            progress["usage"].append(raw["usage"])
            save_json(progress_path, progress)
            print(f"translated {len(progress['texts'])}/{len(cues)} source units", flush=True)
    progress["generation_wall_seconds"] = progress.get("generation_wall_seconds", 0) + time.monotonic() - started
    save_json(progress_path, progress)
    if failures:
        raise ValueError("Translation incomplete; successful batches retained. " + "; ".join(failures))

    # 3. Write a cue draft or source-linked utterance draft only when complete.

    if set(progress["texts"]) != {str(cue["id"]) for cue in cues}:
        raise ValueError("Translation checkpoint is incomplete or contains extra cues")
    if (file_hash(source) != source_sha256 or
            (utterance_map and file_hash(utterance_map) != settings["utterance_map_sha256"])):
        raise ValueError("Translation inputs changed during generation")
    if source_unit_ids is None:
        result = [
            {"start_ms": cue["start"], "end_ms": cue["end"],
             "text": progress["texts"][str(cue["id"])]}
            for cue in cues
        ]
        temporary = output.with_suffix(".srt.tmp")
        WRITE_SRT(temporary, result)
        READ_CUES(temporary)
        os.replace(temporary, output)
    else:
        save_json(output, {"version": 1, "source": str(source),
                           "source_sha256": source_sha256,
                           "utterance_map": str(utterance_map.resolve()),
                           "utterance_map_sha256": settings["utterance_map_sha256"],
                           "translations": [
                               {"source_ids": [unit_id],
                                "text": progress["texts"][str(index)]}
                               for index, unit_id in enumerate(source_unit_ids, start=1)
                           ],
                           "note": "Draft translations need source-referenced semantic review and display layout."})
    save_json(report_path, {
        **settings, "output": str(output), "output_sha256": file_hash(output),
        "cues": len(cues), "batch_seconds": progress["batch_seconds"],
        "generation_seconds": round(progress["generation_wall_seconds"], 3),
        "request_seconds_sum": round(sum(progress["batch_seconds"]), 3),
        "concurrency": concurrency, "status": "provider_draft", "semantic_approved": False,
        "raw_batches": str(raw_directory),
        "pricing": {"source": "https://api-docs.deepseek.com/quick_start/pricing/",
                    "input_usd_per_million": input_rate, "output_usd_per_million": output_rate},
        "estimated_cost_usd": sum(item.get("prompt_tokens", 0) * input_rate
                                  + item.get("completion_tokens", 0) * output_rate
                                  for item in progress["usage"]) / 1_000_000,
        "estimated_cost_upper_bound_usd": upper_cost,
        "cost_note": "Configured cache-miss rates; estimate, not a billing receipt.",
        "usage": progress["usage"],
        "note": "Model output is a draft; review English meaning against the source.",
    })
    print(json.dumps({"output": str(output), "report": str(report_path),
                      "cues": len(cues)}, ensure_ascii=False))


def check():
    target = [{"id": 1}, {"id": 2}]
    assert validate_translation([{"id": 2, "text": "Two"},
                                 {"id": 1, "text": "One"}], target) == {1: "One", 2: "Two"}
    try:
        validate_translation([{"id": 1, "text": "One"},
                              {"id": 1, "text": "Again"}], target)
    except ValueError:
        pass
    else:
        raise AssertionError("Duplicate translations were accepted")
    print("check ok")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, nargs="?")
    parser.add_argument("output", type=Path, nargs="?")
    parser.add_argument("--source-language")
    parser.add_argument("--batch-size", type=int, default=80)
    parser.add_argument("--utterance-map", type=Path,
                        help="write a source-linked JSON draft with independent display layout")
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--input-token-budget", type=int, default=6000,
                        help="conservative UTF-8 byte bound on prompt and context")
    parser.add_argument("--max-output-tokens", type=int, default=8192)
    parser.add_argument("--input-usd-per-million", type=float, default=0.30)
    parser.add_argument("--output-usd-per-million", type=float, default=1.20)
    parser.add_argument("--max-estimated-usd", type=float)
    parser.add_argument("--glossary", type=Path)
    parser.add_argument("--ready", type=Path, help="current Turkish-ready checkpoint")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        check()
        return

    if args.source is None or args.output is None or args.source_language is None:
        parser.error("provide source SRT, output SRT, and --source-language")

    translate(args)


if __name__ == "__main__":
    main()
