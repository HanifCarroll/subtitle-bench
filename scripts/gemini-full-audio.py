#!/usr/bin/env python3
"""Save one hash-bound, full-episode Gemini audio observation for development."""

import argparse
import json
import runpy
import subprocess
from pathlib import Path


REVIEW = runpy.run_path(str(Path(__file__).with_name("gemini-audio-review.py")))
HASH = REVIEW["file_hash"]
SAVE = REVIEW["save_json"]
EpisodeBudget = REVIEW["EpisodeBudget"]
INTERACTION_STATUS = REVIEW["interaction_status"]

PROMPT = (
    "Listen to the entire original Turkish episode audio. Produce a compact, "
    "chronological observation of every relevant spoken or sung word, including "
    "short replies, overlap, quiet dialogue under music, and speech near chunk "
    "boundaries. Do not summarize, translate, or use any external subtitle. "
    "Write one line per utterance as HH:MM:SS.sss --> HH:MM:SS.sss | Turkish words. "
    "Use approximate times; exact alignment will be checked separately. "
    "For uncertain speech, give the audible alternatives and mark uncertainty. "
    "For a distinct stretch with music but no relevant words, nonverbal sound, or "
    "silence, label the acoustic outcome without inventing dialogue. "
    "Work through the episode in order and include its final scene. "
    "Only if you reached the audio's end, finish with END_OF_AUDIO and its time."
)


def audio_duration_ms(path):
    result = subprocess.run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(path),
    ], capture_output=True, text=True, check=True)
    return round(float(result.stdout.strip()) * 1000)


def prepare(plan_path, plan):
    if (plan.get("kind") != "full_episode_audio_observation"
            or plan.get("model") != "gemini-3.8-flash"
            or type(plan.get("max_output_tokens")) is not int
            or not 1 <= plan["max_output_tokens"] <= 65536
            or not isinstance(plan.get("authorization"), str)):
        raise ValueError("Use a bounded full-episode Gemini 3.8 Flash observation plan")
    video = Path(plan["video"]).resolve(strict=True)
    if HASH(video) != plan.get("video_sha256"):
        raise ValueError("Full-episode video hash changed")
    duration_ms = audio_duration_ms(video)
    if abs(duration_ms - plan.get("duration_ms", -1)) > 1000:
        raise ValueError("Full-episode duration differs from the plan")

    audio = plan_path.parent / "full-episode-audio.mp3"
    identity = plan_path.parent / "full-episode-audio.json"
    if audio.exists() or identity.exists():
        if not audio.is_file() or not identity.is_file():
            raise ValueError("Full-episode audio extraction is incomplete")
        saved = json.loads(identity.read_text(encoding="utf-8"))
        if (saved.get("video_sha256") != plan["video_sha256"]
                or saved.get("audio_sha256") != HASH(audio)
                or saved.get("audio_duration_ms") != audio_duration_ms(audio)):
            raise ValueError("Full-episode audio extraction changed")
    else:
        subprocess.run([
            "ffmpeg", "-v", "error", "-i", str(video), "-map", "0:a:0",
            "-vn", "-ac", "1", "-ar", "16000", "-c:a", "libmp3lame",
            "-b:a", "64k", str(audio),
        ], check=True)
        saved = {"video": str(video), "video_sha256": plan["video_sha256"],
                 "audio": str(audio), "audio_sha256": HASH(audio),
                 "audio_duration_ms": audio_duration_ms(audio),
                 "note": "Audio extracted from the complete original episode."}
        SAVE(identity, saved)
    if abs(saved["audio_duration_ms"] - duration_ms) > 1000:
        raise ValueError("Extracted audio does not cover the complete episode")
    selected = [("full-episode", plan_path,
                 {"video_sha256": plan["video_sha256"], "start_ms": 0,
                  "end_ms": saved["audio_duration_ms"]}, audio)]
    budget = EpisodeBudget(plan["authorization"], plan, selected, full_episode=True)
    return audio, saved, budget


def observe(client, plan_path, plan, audio, audio_identity, budget):
    receipt_path = plan_path.parent / "full-episode-observation.json"
    if receipt_path.exists():
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        if (receipt.get("status") == "complete"
                and receipt.get("audio_sha256") == HASH(audio)
                and receipt.get("authorization_sha256") == budget.sha256
                and receipt.get("provider_file_deleted") is True):
            return receipt
        raise ValueError("Full-episode observation was interrupted; inspect receipt")

    duration_ms = audio_identity["audio_duration_ms"]
    record = {"provider": "google-gemini", "model": plan["model"],
              "video_sha256": plan["video_sha256"],
              "audio": str(audio), "audio_sha256": HASH(audio),
              "audio_duration_ms": duration_ms,
              "audio_identity": str(plan_path.parent / "full-episode-audio.json"),
              "authorization": str(budget.path),
              "authorization_sha256": budget.sha256,
              "usage_ledger": str(budget.ledger_path),
              "prompt_version": "full-episode-observation-v1",
              "max_output_tokens": plan["max_output_tokens"],
              "status": "uploading", "provider_file_deleted": False}
    record["ledger_upload_event_id"] = budget.reserve_upload(
        plan_path, "full-episode", plan_path, audio, duration_ms)
    SAVE(receipt_path, record)
    uploaded = client.files.upload(file=str(audio))
    record["remote_file_name"] = uploaded.name
    record["status"] = "uploaded"
    SAVE(receipt_path, record)
    try:
        prompt_path = plan_path.parent / "full-episode-prompt.txt"
        raw_path = plan_path.parent / "full-episode-raw.txt"
        prompt_path.write_text(PROMPT, encoding="utf-8")
        prompt_bytes = len(PROMPT.encode("utf-8"))
        record["prompt"] = str(prompt_path)
        record["prompt_sha256"] = HASH(prompt_path)
        record["prompt_bytes"] = prompt_bytes
        event_id = budget.reserve_call(
            plan_path, "full-episode", plan_path, audio, duration_ms,
            "full_episode_observation", prompt_bytes, plan["max_output_tokens"])
        record["ledger_model_call_event_id"] = event_id
        record["status"] = "requesting"
        SAVE(receipt_path, record)
        response = client.interactions.create(
            model=plan["model"],
            input=[{"type": "text", "text": PROMPT},
                   {"type": "audio", "uri": uploaded.uri,
                    "mime_type": uploaded.mime_type}],
            generation_config={"max_output_tokens": plan["max_output_tokens"]},
        )
        raw_path.write_text(response.output_text or "", encoding="utf-8")
        record["raw_response"] = str(raw_path)
        record["raw_sha256"] = HASH(raw_path)
        record["response_id"] = response.id
        record["provider_status"] = INTERACTION_STATUS(response)
        if hasattr(response, "model_dump"):
            response_path = plan_path.parent / "full-episode-response.json"
            SAVE(response_path, response.model_dump(mode="json", exclude_none=True))
            record["response_metadata"] = str(response_path)
            record["response_metadata_sha256"] = HASH(response_path)
        usage = getattr(response, "usage", None)
        if hasattr(usage, "model_dump"):
            record["usage"] = usage.model_dump(mode="json", exclude_none=True)
        elif isinstance(usage, dict):
            record["usage"] = usage
        budget.record_usage(event_id, record.get("usage"))
        record["status"] = "response_saved"
        SAVE(receipt_path, record)
        if record["provider_status"] != "completed":
            record["status"] = "provider_incomplete"
            SAVE(receipt_path, record)
            raise ValueError("Gemini provider did not complete full-episode output")
        if not response.output_text:
            raise ValueError("Gemini returned empty full-episode output")
    finally:
        try:
            client.files.delete(name=uploaded.name)
        except Exception as error:
            record["provider_file_deletion_error"] = str(error)
            SAVE(receipt_path, record)
            raise
        else:
            record["provider_file_deleted"] = True
            SAVE(receipt_path, record)

    record["status"] = "complete"
    record["claimed_end_marker_present"] = "END_OF_AUDIO" in response.output_text
    record["note"] = "A model observation, not a checked transcript or timing track."
    SAVE(receipt_path, record)
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("--apply", action="store_true",
                        help="upload audio and make one billable model request")
    args = parser.parse_args()
    plan_path = args.plan.resolve(strict=True)
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    audio, identity, budget = prepare(plan_path, plan)
    print(json.dumps({"audio": str(audio), "audio_sha256": identity["audio_sha256"],
                      "audio_seconds": identity["audio_duration_ms"] / 1000,
                      "apply": args.apply}))
    if not args.apply:
        return
    from google import genai
    from google.genai import types
    client = genai.Client(http_options=types.HttpOptions(
        retry_options=types.HttpRetryOptions(attempts=1)))
    receipt = observe(client, plan_path, plan, audio, identity, budget)
    print(json.dumps({"receipt": str(plan_path.parent / "full-episode-observation.json"),
                      "status": receipt["status"],
                      "provider_file_deleted": receipt["provider_file_deleted"]}))


if __name__ == "__main__":
    main()
