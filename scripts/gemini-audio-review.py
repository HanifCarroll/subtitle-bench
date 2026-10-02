#!/usr/bin/env python3
"""Review planned original-video audio clips with Gemini after approval."""

import argparse
import fcntl
import hashlib
import json
import math
import re
import subprocess
from datetime import datetime, timezone
from decimal import Decimal
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


def interaction_status(response):
    """Read the provider's completion status, including SDK enum values."""
    status = getattr(response, "status", None)
    if hasattr(response, "model_dump"):
        raw = response.model_dump(mode="json", exclude_none=True)
        if isinstance(raw, dict):
            status = raw.get("status", status)
    return getattr(status, "value", status)


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
    "Return JSON with an acoustic assessment for each distinct interval: "
    "relevant_speech, unintelligible_speech, music_without_relevant_words, "
    "nonverbal_sound, or silence. Mixed intervals may have more than one category. "
    "Give approximate clip-relative times, what you actually hear, and uncertainty. "
    "For recoverable speech, include spoken Turkish, short replies, and speakers "
    "where distinguishable. Check quiet speech and speech under music. "
    "Do not invent words or treat your timestamps as final alignment."
)
COMPARISON_PROMPT = (
    "Listen to the same original audio again. Compare it with the independent "
    "observation and the supplied Turkish, English, reference, and ASR candidates. "
    "Candidate cues may cross the clip boundary: never claim that words outside "
    "the supplied audio are absent, or propose a repair for an utterance whose "
    "ending is outside the clip. If your new exact-word reading materially "
    "differs from your independent observation, report that disagreement as "
    "unresolved unless the audio itself explains the change. "
    "Return JSON with the supported acoustic outcome for each disputed interval, "
    "supported corrections, omitted utterances, unsupported subtitle text, "
    "meaning-changing differences, and unresolved ambiguities. Explain any "
    "no-relevant-speech conclusion from the audio, including quiet-speech checks. "
    "For each finding include approximate clip-relative interval, source expression, "
    "current wording, proposed repair, evidence explanation, and uncertainty. "
    "The original audio is authoritative; empty ASR, absent VAD, and model agreement "
    "are not proof."
)


def parsed_response(raw):
    """Keep a machine-readable copy without accepting prose as a finding."""
    content = raw.strip()
    fenced = re.findall(r"```(?:json)?\s*([\s\S]*?)```", content)
    if fenced and (len(fenced) != 1 or not fenced[0].strip()):
        raise ValueError("Audio review response has ambiguous JSON fences")
    if fenced:
        content = fenced[0].strip()
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
            or type(plan.get("max_calls")) is not int
            or plan["max_calls"] not in (2, 4, 6)
            or not isinstance(plan.get("bundles"), list)
            or not 1 <= len(plan["bundles"]) <= 3):
        raise ValueError("Use a bounded two-stage Gemini plan")
    independent_prompt(plan)

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
    if len(selected) * 2 > plan["max_calls"]:
        raise ValueError("Gemini plan exceeds its approved call count")

    return selected, total_ms


def independent_prompt(plan):
    """Allow a bounded acoustic question before any candidate is supplied."""
    focus = plan.get("independent_focus", "")
    if not isinstance(focus, str) or len(focus.encode("utf-8")) > 2000:
        raise ValueError("Independent acoustic focus must be text of at most 2000 bytes")
    return INDEPENDENT_PROMPT + ("\nAcoustic focus: " + focus.strip() if focus.strip() else "")


class EpisodeBudget:
    """Account for every attempted upload and model call across scene plans."""

    def __init__(self, authorization_path, plan, selected, full_episode=False):
        self.path = Path(authorization_path).resolve(strict=True)
        self.authorization = json.loads(self.path.read_text(encoding="utf-8"))
        self.sha256 = file_hash(self.path)
        self.ledger_path = self.path.parent / "gemini-usage-ledger.json"
        self.lock_path = self.path.parent / "gemini-usage-ledger.lock"
        scope = self.authorization.get("scope", {})
        limits = self.authorization.get("aggregate_hard_limits", {})
        required = ("attempted_model_calls", "audio_uploads",
                    "uploaded_audio_seconds_including_repeats",
                    "processed_audio_seconds_including_repeats", "input_prompt_bytes",
                    "estimated_charge_usd", "max_clip_seconds",
                    "max_output_tokens_per_call")
        if any(type(limits.get(key)) not in (int, float) or limits[key] <= 0
               for key in required):
            raise ValueError("Episode authorization needs positive aggregate limits")
        if full_episode and (type(limits.get("full_episode_audio_seconds")) not in
                             (int, float) or limits["full_episode_audio_seconds"] <= 0):
            raise ValueError("Episode authorization needs a full-audio duration limit")
        video = Path(scope.get("video", ""))
        if (self.authorization.get("status") != "approved"
                or not self.authorization.get("approval_source")
                or scope.get("provider") != "google-gemini"
                or scope.get("model") != plan["model"]
                or not video.is_file()
                or file_hash(video) != scope.get("video_sha256")
                or any(bundle["video_sha256"] != scope["video_sha256"]
                       for _, _, bundle, _ in selected)
                or any((bundle["end_ms"] - bundle["start_ms"]) >
                       round(limits["full_episode_audio_seconds" if full_episode
                                    else "max_clip_seconds"] * 1000)
                       for _, _, bundle, _ in selected)
                or type(plan.get("max_output_tokens")) is not int
                or type(limits.get("max_output_tokens_per_call")) is not int
                or plan["max_output_tokens"] > limits["max_output_tokens_per_call"]):
            raise ValueError("Episode authorization does not cover this video, model, or output cap")
        pricing = self.authorization.get("pricing", {})
        if (pricing.get("source") != "https://ai.google.dev/gemini-api/docs/pricing"
                or type(pricing.get("input_usd_per_million_tokens")) not in (int, float)
                or type(pricing.get("output_usd_per_million_tokens")) not in (int, float)
                or pricing["input_usd_per_million_tokens"] <= 0
                or pricing["output_usd_per_million_tokens"] <= 0):
            raise ValueError("Episode authorization needs recorded token pricing")
        self.limits = limits
        self.pricing = pricing

    def estimate(self, prompt_bytes, duration_ms, output_tokens):
        # Conservative pre-call reservation: twice Google's documented 32 audio
        # tokens/s, one text token/byte, and 1,000 tokens of request overhead.
        input_tokens = prompt_bytes + 1000 + math.ceil(duration_ms * 64 / 1000)
        return float((Decimal(input_tokens) * Decimal(str(
            self.pricing["input_usd_per_million_tokens"]))
            + Decimal(output_tokens) * Decimal(str(
                self.pricing["output_usd_per_million_tokens"]))) / 1_000_000)

    def _locked_change(self, event=None, usage_update=None):
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open("a+") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            if self.ledger_path.exists():
                ledger = json.loads(self.ledger_path.read_text(encoding="utf-8"))
                if ledger.get("authorization_sha256") != self.sha256:
                    raise ValueError("Episode authorization changed after usage began")
            else:
                ledger = {"authorization": str(self.path),
                          "authorization_sha256": self.sha256, "events": []}
            if usage_update is not None:
                event_id, usage = usage_update
                item = next((value for value in ledger["events"]
                             if value["id"] == event_id and value["kind"] == "model_call"), None)
                if item is None:
                    raise ValueError("Unknown model-call ledger event")
                item["usage"] = usage
                if all(isinstance(usage.get(key), int) for key in
                       ("total_input_tokens", "total_output_tokens", "total_thought_tokens")):
                    item["estimated_charge_usd"] = float((
                        Decimal(usage["total_input_tokens"]) * Decimal(str(
                            self.pricing["input_usd_per_million_tokens"]))
                        + Decimal(usage["total_output_tokens"]
                                  + usage["total_thought_tokens"]) * Decimal(str(
                                      self.pricing["output_usd_per_million_tokens"])))
                        / 1_000_000)
                item["usage_recorded_at_utc"] = datetime.now(timezone.utc).isoformat()
            if event is not None:
                uploads = [item for item in ledger["events"] if item["kind"] == "upload"]
                calls = [item for item in ledger["events"] if item["kind"] == "model_call"]
                upload_ms = sum(item["duration_ms"] for item in uploads)
                processed_ms = sum(item["duration_ms"] for item in calls)
                prompt_bytes = sum(item["prompt_bytes"] for item in calls)
                cost = sum(Decimal(str(item["estimated_charge_usd"])) for item in calls)
                next_uploads = len(uploads) + (event["kind"] == "upload")
                next_calls = len(calls) + (event["kind"] == "model_call")
                next_upload_ms = upload_ms + (event["duration_ms"] if event["kind"] == "upload" else 0)
                next_processed_ms = processed_ms + (event["duration_ms"] if event["kind"] == "model_call" else 0)
                next_prompt_bytes = prompt_bytes + event.get("prompt_bytes", 0)
                next_cost = cost + Decimal(str(event.get("estimated_charge_usd", 0)))
                full_uploads = sum(item["kind"] == "upload" and
                                   item.get("label") == "full-episode"
                                   for item in ledger["events"])
                full_calls = sum(item["kind"] == "model_call" and
                                 item.get("stage") == "full_episode_observation"
                                 for item in ledger["events"])
                if (next_uploads > self.limits["audio_uploads"]
                        or next_calls > self.limits["attempted_model_calls"]
                        or next_upload_ms > round(
                            self.limits["uploaded_audio_seconds_including_repeats"] * 1000)
                        or next_processed_ms > round(
                            self.limits["processed_audio_seconds_including_repeats"] * 1000)
                        or next_prompt_bytes > self.limits["input_prompt_bytes"]
                        or (event["kind"] == "upload" and
                            event.get("label") == "full-episode" and full_uploads >= 1)
                        or (event["kind"] == "model_call" and
                            event.get("stage") == "full_episode_observation" and
                            full_calls >= 1)
                        or next_cost > Decimal(str(self.limits["estimated_charge_usd"]))):
                    raise ValueError("Episode Gemini aggregate limit reached; no provider request made")
                event["id"] = len(ledger["events"]) + 1
                event["reserved_at_utc"] = datetime.now(timezone.utc).isoformat()
                ledger["events"].append(event)
            save_json(self.ledger_path, ledger)
            return event["id"] if event is not None else None

    def reserve_upload(self, plan_path, label, bundle_path, audio, duration_ms):
        return self._locked_change({
            "kind": "upload", "plan": str(plan_path),
            "plan_sha256": file_hash(plan_path), "label": label,
            "bundle_sha256": file_hash(bundle_path), "clip_sha256": file_hash(audio),
            "duration_ms": duration_ms})

    def reserve_call(self, plan_path, label, bundle_path, audio, duration_ms,
                     stage, prompt_bytes, max_output_tokens):
        return self._locked_change({
            "kind": "model_call", "plan": str(plan_path),
            "plan_sha256": file_hash(plan_path), "label": label,
            "bundle_sha256": file_hash(bundle_path), "clip_sha256": file_hash(audio),
            "duration_ms": duration_ms, "stage": stage,
            "prompt_bytes": prompt_bytes,
            "max_output_tokens": max_output_tokens,
            "estimated_charge_usd": self.estimate(
                prompt_bytes, duration_ms, max_output_tokens)})

    def record_usage(self, event_id, usage):
        if isinstance(usage, dict):
            self._locked_change(usage_update=(event_id, usage))


def two_stage_review(client, plan_path, plan, selected, budget=None):
    """Observe original audio first, then compare it with saved candidates."""
    output = plan_path.parent / "gemini-two-stage"
    output.mkdir(exist_ok=True)
    for label, bundle_path, bundle, audio in selected:
        duration_ms = bundle["end_ms"] - bundle["start_ms"]
        receipt = output / f"{label}.json"
        if receipt.exists():
            saved = json.loads(receipt.read_text(encoding="utf-8"))
            if budget is not None and (saved.get("authorization_sha256") != budget.sha256
                                       or saved.get("usage_ledger") != str(budget.ledger_path)):
                raise ValueError(f"Review receipt at {label} belongs to another authorization")
            if (saved.get("status") == "complete"
                    and saved.get("clip_sha256") == file_hash(audio)
                    and saved.get("independent_provider_status") == "completed"
                    and saved.get("comparison_provider_status") == "completed"
                    and saved.get("provider_file_deleted") is True):
                saved_prompt = Path(saved["independent_prompt"])
                if (saved_prompt.read_text(encoding="utf-8") != independent_prompt(plan)
                        or file_hash(saved_prompt) != saved.get("independent_prompt_sha256")):
                    raise ValueError(f"Independent question changed at {label}")
                continue
            if (saved.get("status") not in (
                    "independent_response_saved", "independent_complete")
                    or saved.get("provider_file_deleted") is not True
                    or saved.get("model_calls_attempted") != 1
                    or saved.get("clip_sha256") != file_hash(audio)
                    or saved.get("bundle_sha256") != file_hash(bundle_path)
                    or saved.get("video_sha256") != bundle["video_sha256"]
                    or saved.get("source_sha256") != bundle["source_sha256"]
                    or saved.get("target_sha256") != bundle["target_sha256"]):
                raise ValueError(f"Review interrupted at {label}; inspect its receipt")
            raw = Path(saved["independent_raw_response"])
            prompt = Path(saved["independent_prompt"])
            if (not raw.is_file() or not prompt.is_file()
                    or file_hash(raw) != saved.get("independent_raw_sha256")
                    or file_hash(prompt) != saved.get("independent_prompt_sha256")
                    or prompt.read_text(encoding="utf-8") != independent_prompt(plan)):
                raise ValueError(f"Independent response changed at {label}")
            record = saved
            record["independent_parsed"] = parsed_response(raw.read_text(encoding="utf-8"))
            record["upload_history"] = [{"remote_file_name": record["remote_file_name"],
                                         "provider_file_deleted": True}]
            record["audio_uploads_attempted"] = 2
            stages = ("comparison",)
        else:
            record = {
                "provider": "google-gemini", "model": plan["model"],
                "bundle": str(bundle_path), "bundle_sha256": file_hash(bundle_path),
                "video_sha256": bundle["video_sha256"],
                "source_sha256": bundle["source_sha256"],
                "target_sha256": bundle["target_sha256"],
                "start_ms": bundle["start_ms"], "end_ms": bundle["end_ms"],
                "clip_sha256": file_hash(audio), "status": "uploading",
                "audio_uploads_attempted": 1,
                "prompt_version": ("two-stage-audio-v3-focused"
                                   if plan.get("independent_focus", "").strip()
                                   else "two-stage-audio-v3"),
                "settings": {"generation_config": (
                    {"max_output_tokens": plan["max_output_tokens"]}
                    if "max_output_tokens" in plan else "provider_default")},
            }
            stages = ("independent", "comparison")
        if budget is not None:
            record["authorization"] = str(budget.path)
            record["authorization_sha256"] = budget.sha256
            record["usage_ledger"] = str(budget.ledger_path)
            event_id = budget.reserve_upload(
                plan_path, label, bundle_path, audio, duration_ms)
            record.setdefault("ledger_upload_event_ids", []).append(event_id)
        record["provider_file_deleted"] = False
        record["status"] = "uploading"
        save_json(receipt, record)
        uploaded = client.files.upload(file=str(audio))
        record["remote_file_name"] = uploaded.name
        record["status"] = "uploaded"
        save_json(receipt, record)

        try:
            for stage in stages:
                prompt = independent_prompt(plan) if stage == "independent" else (
                    COMPARISON_PROMPT + "\n" + json.dumps({
                        "independent_observation": record["independent_output"],
                        "candidate_timeline": bundle["timeline"],
                    }, ensure_ascii=False)
                )
                prompt_path = output / f"{label}-{stage}-prompt.txt"
                raw_path = output / f"{label}-{stage}-raw.txt"
                prompt_path.write_text(prompt, encoding="utf-8")
                record[f"{stage}_prompt"] = str(prompt_path)
                record[f"{stage}_prompt_sha256"] = file_hash(prompt_path)
                record[f"{stage}_prompt_bytes"] = len(prompt.encode("utf-8"))
                if budget is not None:
                    event_id = budget.reserve_call(
                        plan_path, label, bundle_path, audio, duration_ms,
                        stage, record[f"{stage}_prompt_bytes"],
                        plan["max_output_tokens"])
                    record.setdefault("ledger_model_call_event_ids", {})[stage] = event_id
                record["model_calls_attempted"] = record.get("model_calls_attempted", 0) + 1
                record["status"] = f"{stage}_requesting"
                save_json(receipt, record)
                request = {"model": plan["model"],
                           "input": [{"type": "text", "text": prompt},
                                     {"type": "audio", "uri": uploaded.uri,
                                      "mime_type": uploaded.mime_type}]}
                if "max_output_tokens" in plan:
                    request["generation_config"] = {
                        "max_output_tokens": plan["max_output_tokens"]}
                response = client.interactions.create(**request)
                raw_path.write_text(response.output_text or "", encoding="utf-8")
                record[f"{stage}_raw_response"] = str(raw_path)
                record[f"{stage}_raw_sha256"] = file_hash(raw_path)
                record[f"{stage}_response_id"] = response.id
                record[f"{stage}_output"] = response.output_text
                record[f"{stage}_provider_status"] = interaction_status(response)
                usage = getattr(response, "usage", None)
                if hasattr(usage, "model_dump"):
                    record[f"{stage}_usage"] = usage.model_dump(
                        mode="json", exclude_none=True)
                elif isinstance(usage, dict):
                    record[f"{stage}_usage"] = usage
                if budget is not None:
                    budget.record_usage(event_id, record.get(f"{stage}_usage"))
                record["status"] = f"{stage}_response_saved"
                save_json(receipt, record)
                if record[f"{stage}_provider_status"] != "completed":
                    record["status"] = f"{stage}_provider_incomplete"
                    save_json(receipt, record)
                    raise ValueError(
                        f"Gemini provider did not complete {stage} for {label}")
                if response.output_text:
                    record[f"{stage}_parsed"] = parsed_response(response.output_text)
                record["status"] = f"{stage}_complete"
                save_json(receipt, record)
                if not response.output_text:
                    raise ValueError(f"Gemini returned empty {stage} output for {label}")
        finally:
            try:
                client.files.delete(name=uploaded.name)
            except Exception as error:
                record["provider_file_deleted"] = False
                record["provider_file_deletion_error"] = str(error)
                save_json(receipt, record)
                raise
            else:
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
        budget = (EpisodeBudget(plan["authorization"], plan, selected)
                  if "authorization" in plan else None)
        print(json.dumps({"calls": len(selected) * 2,
                          "audio_seconds": round(total_ms / 1000, 3),
                          "authorization_valid": budget is not None,
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
            if budget is None:
                raise ValueError("Two-stage provider calls require an episode authorization file")
            from google import genai
            from google.genai import types
            # The SDK otherwise retries model calls after transient errors.
            # One attempt per request keeps the planned call count exact.
            client = genai.Client(http_options=types.HttpOptions(
                retry_options=types.HttpRetryOptions(attempts=1)))
            two_stage_review(client, args.plan, plan, selected, budget)
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
