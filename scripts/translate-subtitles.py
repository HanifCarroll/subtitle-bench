#!/usr/bin/env python3
"""Translate one source-language SRT to English with DeepSeek Flash."""

import argparse
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


def request_translation(prompt, context):
    # 1. Send one paid request without an automatic retry.

    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
    ]
    body = {
        "model": MODEL, "temperature": 0, "thinking": {"type": "disabled"},
        "max_tokens": 2048, "response_format": {"type": "json_object"},
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

    # 2. Return text only when DeepSeek says the response is complete.

    choice = payload["choices"][0]
    if choice["finish_reason"] != "stop":
        raise ValueError("DeepSeek stopped before completing the batch")

    return choice["message"]["content"], payload.get("usage", {})


def translate_batch(cues, start, size, language):
    # 1. Give the model neighboring dialogue without asking it to translate context cues.

    target = cues[start:start + size]
    context = {
        name: [{"id": cue["id"], "text": cue["text"]} for cue in group]
        for name, group in {
            "previous": cues[max(0, start - 4):start],
            "target": target,
            "next": cues[start + size:start + size + 4],
        }.items()
    }
    prompt = (
        f"Translate {language} dialogue subtitles into faithful English. "
        'Return JSON only: {"cues":[{"id":1,"text":"English subtitle"}]}. '
        "Return each target cue exactly once with its original ID. Previous and next cues "
        "are context only. Preserve spoken details, speaker turns, genuine repetition, "
        "names, songs, insults, and jokes. Do not invent speech or shorten it to fit "
        "a reading-speed limit. Use natural English; do not add notes or timestamps."
    )
    response_text, usage = request_translation(prompt, context)

    # 2. Accept only a complete batch with the requested cue IDs.

    try:
        items = json.loads(response_text)["cues"]
        return validate_translation(items, target), [usage] if usage else []
    except (KeyError, TypeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError("DeepSeek returned incomplete or unmatched cues") from error


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
    # 1. Bind resumable progress to the exact source text, language, and model.

    source = args.source.resolve(strict=True)
    output = args.output.resolve()
    utterance_map = getattr(args, "utterance_map", None)
    expected_suffix = ".json" if utterance_map else ".srt"
    if source == output or output.exists() or output.suffix.lower() != expected_suffix:
        raise ValueError(f"Use a new {expected_suffix} output path separate from the source")
    if not args.source_language.isalpha() or not 2 <= len(args.source_language) <= 8:
        raise ValueError("Use a source-language code such as tr")
    if not 1 <= args.batch_size <= 30:
        raise ValueError("Batch size must be 1-30 cues")

    output.parent.mkdir(parents=True, exist_ok=True)
    cues, source_unit_ids = translation_targets(source, utterance_map)
    source_sha256 = file_hash(source)
    progress_path = output.with_suffix(".progress.json")
    report_path = output.with_suffix(".translation.json")
    if report_path.exists():
        raise FileExistsError(f"Translation report already exists: {report_path}")
    settings = {
        "source": str(source), "source_sha256": source_sha256,
        "source_language": args.source_language.lower(),
        "target_language": "en", "provider": "deepseek", "model": MODEL,
        "batch_size": args.batch_size,
        "utterance_map_sha256": file_hash(utterance_map) if utterance_map else None,
    }
    progress = (
        json.loads(progress_path.read_text(encoding="utf-8"))
        if progress_path.exists() else {**settings, "texts": {}, "batch_seconds": [], "usage": []}
    )
    if any(progress.get(key) != value for key, value in settings.items()):
        raise ValueError("Translation progress belongs to another source or model")

    # 2. Save each complete batch, allowing a stopped run to resume.

    for start in range(0, len(cues), args.batch_size):
        target = cues[start:start + args.batch_size]
        if all(str(cue["id"]) in progress["texts"] for cue in target):
            continue

        started = time.monotonic()
        translated, usage = translate_batch(cues, start, len(target),
                                            args.source_language)
        progress["texts"].update({str(key): value for key, value in translated.items()})
        progress["batch_seconds"].append(round(time.monotonic() - started, 3))
        progress["usage"].extend(usage)
        save_json(progress_path, progress)
        print(f"translated {len(progress['texts'])}/{len(cues)} cues", flush=True)

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
        "generation_seconds": round(sum(progress["batch_seconds"]), 3),
        "usage": progress["usage"],
        "note": "Model output is a draft; review English meaning against the source.",
    })
    progress_path.unlink(missing_ok=True)
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
    parser.add_argument("--batch-size", type=int, default=15)
    parser.add_argument("--utterance-map", type=Path,
                        help="write a source-linked JSON draft with independent display layout")
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
