#!/usr/bin/env python3
"""Review planned original-video audio clips with Gemini after approval."""

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path


def file_hash(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def save_json(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)


def planned_windows(plan):
    if plan["model"] != "gemini-3.5-transcribe":
        raise ValueError("The plan must use the reviewed transcription model")

    windows = plan["full_chunks"] + plan["focus_clips"]
    duration = int(plan["duration_ms"])
    if len(windows) != int(plan["planned_calls"]) or len(windows) > int(plan["max_calls"]):
        raise ValueError("The plan exceeds its approved call count")

    total_ms = 0
    seen_ids = set()
    for window in windows:
        clip_id = window["id"]
        start = int(window["start_ms"])
        end = int(window["end_ms"])
        if (not re.fullmatch(r"[a-z0-9-]+", clip_id) or clip_id in seen_ids
                or start < 0 or end > duration or start >= end):
            raise ValueError(f"Invalid audio window: {clip_id}")

        seen_ids.add(clip_id)
        total_ms += end - start

    if total_ms != round(float(plan["planned_audio_seconds"]) * 1000):
        raise ValueError("The planned audio duration changed")
    if total_ms > round(float(plan["max_audio_seconds"]) * 1000):
        raise ValueError("The plan exceeds its approved audio duration")

    return windows, total_ms


def extract_audio(video, window, output):
    start = window["start_ms"] / 1000
    seconds = (window["end_ms"] - window["start_ms"]) / 1000
    subprocess.run([
        "ffmpeg", "-y", "-v", "error", "-ss", str(start), "-t", str(seconds),
        "-i", str(video), "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le",
        str(output),
    ], check=True)


def review_clip(client, clip, result_path, plan, window):
    # 1. Save an upload receipt before the billable transcription request.

    record = {
        "video_sha256": plan["video_sha256"],
        "clip": str(clip),
        "clip_sha256": file_hash(clip),
        "start_ms": window["start_ms"],
        "end_ms": window["end_ms"],
        "model": plan["model"],
        "config": {"language_codes": plan["language_codes"], "mode": "verbatim"},
        "status": "uploading",
    }
    save_json(result_path, record)
    uploaded = client.files.upload(file=str(clip))
    record["remote_file_name"] = uploaded.name
    record["status"] = "uploaded"
    save_json(result_path, record)

    # 2. Transcribe the untouched audio, then delete its provider copy.

    try:
        interaction = client.interactions.create(
            model=plan["model"],
            input=[{"type": "audio", "uri": uploaded.uri, "mime_type": uploaded.mime_type}],
            generation_config={"transcription_config": {
                "language_codes": plan["language_codes"],
                "mode": {"type": "verbatim"},
            }},
        )
        record["output_text"] = interaction.output_text
        record["response_id"] = interaction.id
        record["status"] = "transcribed"
        save_json(result_path, record)
    finally:
        client.files.delete(name=uploaded.name)
        record["provider_file_deleted"] = True
        save_json(result_path, record)


INDEPENDENT_PROMPT = (
    "Listen to this original Turkish audio before seeing any subtitle wording. "
    "Return JSON with utterances (approximate clip-relative start/end seconds, "
    "spoken Turkish, speaker if distinguishable, confidence), short replies, "
    "vocalizations, and uncertain spans. Include speech under music. "
    "Do not infer unclear words. Do not treat your timestamps as final alignment."
)
COMPARISON_PROMPT = (
    "Listen to the same original audio again. Compare it with the independent "
    "observation and the supplied Turkish, English, reference, and ASR candidates. "
    "Return JSON with supported corrections, omitted utterances, unsupported "
    "subtitle text, meaning-changing differences, and unresolved ambiguities. "
    "For each finding include approximate clip-relative interval, source expression, "
    "current wording, proposed repair, evidence explanation, and uncertainty. "
    "The original audio is authoritative; a reference or ASR agreement is not proof."
)


def parsed_response(raw):
    """Keep a machine-readable copy without accepting prose as a finding."""
    content = raw.strip()
    if content.startswith("```json"):
        content = content[7:]
    elif content.startswith("```"):
        content = content[3:]
    if content.endswith("```"):
        content = content[:-3]
    parsed = json.loads(content.strip())
    if not isinstance(parsed, (dict, list)) or not parsed:
        raise ValueError("Audio review response is empty or not structured JSON")
    return parsed


def parse_saved_review(receipt, audio):
    """Parse saved responses without another upload or provider call."""
    record = json.loads(receipt.read_text(encoding="utf-8"))
    if (record.get("status") != "complete"
            or record.get("provider_file_deleted") is not True
            or record.get("clip_sha256") != file_hash(audio)):
        raise ValueError(f"Audio review receipt is incomplete: {receipt}")
    for stage in ("independent", "comparison"):
        raw = Path(record[f"{stage}_raw_response"])
        prompt = Path(record[f"{stage}_prompt"])
        if (not raw.is_file() or file_hash(raw) != record.get(f"{stage}_raw_sha256")
                or not prompt.is_file()
                or file_hash(prompt) != record.get(f"{stage}_prompt_sha256")):
            raise ValueError(f"Audio review inputs are stale: {receipt}")
        record[f"{stage}_parsed"] = parsed_response(raw.read_text(encoding="utf-8"))
    save_json(receipt, record)
    return record


def two_stage_plan(plan):
    """Validate an exact, bounded set of private original-audio clips."""
    if (plan.get("kind") != "two_stage_audio_review"
            or plan.get("model") != "gemini-3.8-flash"
            or ("max_output_tokens" in plan
                and (type(plan["max_output_tokens"]) is not int
                     or not 1 <= plan["max_output_tokens"] <= 8192))
            or type(plan.get("max_audio_seconds")) not in (int, float)
            or not 0 < plan["max_audio_seconds"] <= 90
            or plan.get("max_calls") != 6
            or not isinstance(plan.get("bundles"), list)
            or not 1 <= len(plan["bundles"]) <= 3):
        raise ValueError("Use a bounded two-stage Gemini plan")

    selected = []
    seen_ids = set()
    total_ms = 0
    for entry in plan["bundles"]:
        label = entry.get("id")
        if (not isinstance(label, str) or not re.fullmatch(r"[a-z0-9-]+", label)
                or label in seen_ids):
            raise ValueError("Gemini bundle IDs must be unique safe names")
        seen_ids.add(label)
        bundle_path = Path(entry["path"]).resolve(strict=True)
        bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
        if len(bundle.get("clips", [])) != 1:
            raise ValueError("Each Gemini bundle must contain exactly one clip")
        clip = bundle["clips"][0]
        audio = Path(clip["audio_clip"]).resolve(strict=True)
        if (bundle["start_ms"] != clip["video_start_ms"]
                or bundle["end_ms"] != clip["video_end_ms"]
                or bundle["start_ms"] != entry.get("start_ms")
                or bundle["end_ms"] != entry.get("end_ms")
                or file_hash(audio) != clip["audio_sha256"]
                or bundle["video_sha256"] != entry.get("video_sha256")
                or bundle["source_sha256"] != entry.get("source_sha256")
                or bundle["target_sha256"] != entry.get("target_sha256")):
            raise ValueError("Gemini plan has stale clip, video, or subtitles")
        selected.append((label, bundle_path, bundle, audio))
        total_ms += bundle["end_ms"] - bundle["start_ms"]

    if total_ms > round(plan["max_audio_seconds"] * 1000):
        raise ValueError("Gemini plan exceeds its approved audio duration")

    return selected, total_ms


def two_stage_review(client, plan_path, plan, selected):
    """Observe original audio first, then compare it with saved candidates."""
    output = plan_path.parent / "gemini-two-stage"
    output.mkdir(exist_ok=True)
    for label, bundle_path, bundle, audio in selected:
        receipt = output / f"{label}.json"
        if receipt.exists():
            saved = json.loads(receipt.read_text(encoding="utf-8"))
            if (saved.get("status") == "complete"
                    and saved.get("clip_sha256") == file_hash(audio)
                    and saved.get("provider_file_deleted") is True):
                continue
            raise ValueError(f"Review interrupted at {label}; inspect its receipt")

        record = {
            "provider": "google-gemini", "model": plan["model"],
            "bundle": str(bundle_path), "bundle_sha256": file_hash(bundle_path),
            "video_sha256": bundle["video_sha256"],
            "source_sha256": bundle["source_sha256"],
            "target_sha256": bundle["target_sha256"],
            "start_ms": bundle["start_ms"], "end_ms": bundle["end_ms"],
            "clip_sha256": file_hash(audio), "status": "uploading",
            "prompt_version": "two-stage-audio-v1",
            "settings": {"generation_config": (
                {"max_output_tokens": plan["max_output_tokens"]}
                if "max_output_tokens" in plan else "provider_default")},
        }
        save_json(receipt, record)
        uploaded = client.files.upload(file=str(audio))
        record["remote_file_name"] = uploaded.name
        record["status"] = "uploaded"
        save_json(receipt, record)

        try:
            for stage in ("independent", "comparison"):
                prompt = INDEPENDENT_PROMPT if stage == "independent" else (
                    COMPARISON_PROMPT + "\n" + json.dumps({
                        "independent_observation": record["independent_output"],
                        "candidate_timeline": bundle["timeline"],
                    }, ensure_ascii=False)
                )
                prompt_path = output / f"{label}-{stage}-prompt.txt"
                raw_path = output / f"{label}-{stage}-raw.txt"
                prompt_path.write_text(prompt, encoding="utf-8")
                request = {"model": plan["model"],
                           "input": [{"type": "text", "text": prompt},
                                     {"type": "audio", "uri": uploaded.uri,
                                      "mime_type": uploaded.mime_type}]}
                if "max_output_tokens" in plan:
                    request["generation_config"] = {
                        "max_output_tokens": plan["max_output_tokens"]}
                response = client.interactions.create(**request)
                raw_path.write_text(response.output_text or "", encoding="utf-8")
                record[f"{stage}_prompt"] = str(prompt_path)
                record[f"{stage}_prompt_sha256"] = file_hash(prompt_path)
                record[f"{stage}_prompt_bytes"] = len(prompt.encode("utf-8"))
                record[f"{stage}_raw_response"] = str(raw_path)
                record[f"{stage}_raw_sha256"] = file_hash(raw_path)
                record[f"{stage}_response_id"] = response.id
                record[f"{stage}_output"] = response.output_text
                usage = getattr(response, "usage", None)
                if hasattr(usage, "model_dump"):
                    record[f"{stage}_usage"] = usage.model_dump(
                        mode="json", exclude_none=True)
                elif isinstance(usage, dict):
                    record[f"{stage}_usage"] = usage
                if response.output_text:
                    record[f"{stage}_parsed"] = parsed_response(response.output_text)
                record["status"] = f"{stage}_complete"
                save_json(receipt, record)
                if not response.output_text:
                    raise ValueError(f"Gemini returned empty {stage} output for {label}")
        finally:
            client.files.delete(name=uploaded.name)
            record["provider_file_deleted"] = True
            save_json(receipt, record)

        record["status"] = "complete"
        save_json(receipt, record)
        print(f"Reviewed {label}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("--apply", action="store_true", help="upload audio and make billable calls")
    parser.add_argument("--parse-saved", action="store_true",
                        help="parse existing responses without a provider call")
    args = parser.parse_args()

    # 1. Validate the exact video and planned audio budget.

    plan = json.loads(args.plan.read_text())
    if plan.get("kind") == "two_stage_audio_review":
        selected, total_ms = two_stage_plan(plan)
        print(json.dumps({"calls": len(selected) * 2,
                          "audio_seconds": round(total_ms / 1000, 3),
                          "apply": args.apply}))
        if args.parse_saved:
            if args.apply:
                raise ValueError("Parse saved review separately from billable calls")
            output = args.plan.parent / "gemini-two-stage"
            for label, _, _, audio in selected:
                parse_saved_review(output / f"{label}.json", audio)
            print(json.dumps({"parsed_receipts": len(selected)}))
            return
        if args.apply:
            from google import genai
            two_stage_review(genai.Client(), args.plan, plan, selected)
        return

    video = Path(plan["video"]).resolve(strict=True)
    if file_hash(video) != plan["video_sha256"]:
        raise ValueError("The video differs from the approved plan")

    windows, total_ms = planned_windows(plan)
    print(json.dumps({"calls": len(windows), "audio_minutes": round(total_ms / 60_000, 2),
                      "apply": args.apply}))
    if not args.apply:
        return

    # 2. Run only the planned clips and keep each result separate from subtitles.

    from google import genai

    output_directory = args.plan.parent / "gemini-audio"
    output_directory.mkdir(exist_ok=True)
    client = genai.Client()
    for window in windows:
        clip = output_directory / f"{window['id']}.wav"
        result_path = output_directory / f"{window['id']}.json"
        if result_path.exists():
            result = json.loads(result_path.read_text())
            if (result.get("status") == "transcribed"
                    and result.get("provider_file_deleted") is True
                    and result.get("video_sha256") == plan["video_sha256"]
                    and result.get("start_ms") == window["start_ms"]
                    and result.get("end_ms") == window["end_ms"]
                    and result.get("model") == plan["model"]
                    and clip.is_file() and result.get("clip_sha256") == file_hash(clip)):
                continue

            raise ValueError(f"Review interrupted at {window['id']}; inspect its receipt before retrying")

        extract_audio(video, window, clip)
        review_clip(client, clip, result_path, plan, window)
        print(f"Reviewed {window['id']}", flush=True)


if __name__ == "__main__":
    main()
