#!/usr/bin/env python3
"""Bind a completed Gemini audio review to one current source interval, offline."""

import argparse
import hashlib
import json
import runpy
from pathlib import Path


SOURCE = runpy.run_path(str(Path(__file__).with_name("source-review.py")))


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def bind(receipt_path, case_directory, start_ms, end_ms, status,
         audible_outcome, reviewer, reason, output):
    if not 0 <= start_ms < end_ms or not reviewer.strip() or not reason.strip():
        raise ValueError("Give a valid interval, reviewer, and specific reason")
    if output.exists() or output.suffix.lower() != ".json":
        raise ValueError("Use a new JSON receipt path")

    provider = json.loads(receipt_path.read_text(encoding="utf-8"))
    case, working = SOURCE["load_case"](case_directory)
    if (provider.get("provider") != "google-gemini"
            or provider.get("status") != "complete"
            or provider.get("provider_file_deleted") is not True
            or provider.get("model_calls_attempted") != 2
            or provider.get("video_sha256") != case["video_sha256"]
            or not provider.get("start_ms") <= start_ms < end_ms <= provider.get("end_ms")):
        raise ValueError("Provider receipt is incomplete or outside this video interval")
    bundle_path = Path(provider["bundle"])
    if digest(bundle_path) != provider.get("bundle_sha256"):
        raise ValueError("Provider bundle changed")
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    if len(bundle.get("clips", [])) != 1:
        raise ValueError("Provider bundle must have one original-audio clip")
    clip = bundle["clips"][0]
    if (bundle.get("video_sha256") != case["video_sha256"]
            or bundle.get("source_sha256") != provider.get("source_sha256")
            or clip.get("audio_sha256") != provider.get("clip_sha256")
            or digest(Path(clip["audio_clip"])) != provider["clip_sha256"]):
        raise ValueError("Provider clip or compared candidate changed")

    stages = []
    for stage in ("independent", "comparison"):
        raw = Path(provider[f"{stage}_raw_response"])
        prompt = Path(provider[f"{stage}_prompt"])
        parsed = provider.get(f"{stage}_parsed")
        if (not raw.is_file() or not prompt.is_file()
                or digest(raw) != provider.get(f"{stage}_raw_sha256")
                or digest(prompt) != provider.get(f"{stage}_prompt_sha256")
                or not parsed or not provider.get(f"{stage}_response_id")):
            raise ValueError(f"Provider {stage} response is missing or changed")
        stages.append({
            "stage": stage, "method": "audio_capable_model",
            "model": provider["model"], "prompt_version": provider["prompt_version"],
            "assessment": json.dumps(parsed, ensure_ascii=False),
            "prompt": str(prompt), "prompt_sha256": digest(prompt),
            "raw_response": str(raw), "raw_response_sha256": digest(raw),
            "response_id": provider[f"{stage}_response_id"],
            "usage": provider.get(f"{stage}_usage"),
        })

    record = {
        "route": "provider_two_stage", "status": status,
        "audible_outcome": audible_outcome,
        "start_ms": start_ms, "end_ms": end_ms,
        "video_sha256": case["video_sha256"],
        "source_sha256": digest(working),
        "source_interval_sha256": SOURCE["source_interval_sha256"](
            SOURCE["READ_CUES"](working), start_ms, end_ms),
        "provider_compared_source_sha256": provider["source_sha256"],
        "provider_receipt": str(receipt_path),
        "provider_receipt_sha256": digest(receipt_path),
        "provider_audio_interval_ms": [provider["start_ms"], provider["end_ms"]],
        "reviewer": reviewer, "heard_original_audio": False,
        "reason": reason, "stages": stages,
        "note": "Agent choice bound to authentic saved provider responses; not independent ground truth.",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("provider_receipt", type=Path)
    parser.add_argument("case", type=Path)
    parser.add_argument("start_ms", type=int)
    parser.add_argument("end_ms", type=int)
    parser.add_argument("output", type=Path)
    parser.add_argument("--status", choices=("supported", "corrected", "model_artifact"),
                        required=True)
    parser.add_argument("--audible-outcome", choices=(
        "relevant_speech", "unintelligible_speech",
        "music_without_relevant_words", "nonverbal_sound", "silence"), required=True)
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--reason", required=True)
    args = parser.parse_args()
    result = bind(args.provider_receipt.resolve(strict=True),
                  args.case.resolve(strict=True), args.start_ms, args.end_ms,
                  args.status, args.audible_outcome, args.reviewer, args.reason,
                  args.output)
    print(json.dumps({"review_result": str(args.output.resolve()),
                      "status": result["status"],
                      "audible_outcome": result["audible_outcome"]}))


if __name__ == "__main__":
    main()
