#!/usr/bin/env python3
"""Run a bounded Scribe v2 recognition comparison on approved private clips."""

import argparse
import hashlib
import json
import os
import re
import stat
import urllib.error
import urllib.request
import uuid
from pathlib import Path


ENDPOINT = "https://api.elevenlabs.io/v1/speech-to-text"
MODEL = "scribe_v2"
SETTINGS = {"model_id": MODEL, "language_code": "tr", "no_verbatim": "false",
            "tag_audio_events": "true", "diarize": "true",
            "timestamps_granularity": "word", "temperature": "0"}


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def save_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8")
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def checked_plan(path):
    """Recheck every approved clip against its immutable video and audio hashes."""
    plan = json.loads(path.read_text(encoding="utf-8"))
    if (plan.get("model") != MODEL or plan.get("max_calls") != 3
            or plan.get("max_audio_seconds") != 90
            or plan.get("max_cost_usd") != 5
            or len(plan.get("bundles", [])) != 3):
        raise ValueError("Scribe plan must match the three approved clips and caps")
    total_ms = 0
    jobs = []
    for item in plan["bundles"]:
        bundle = json.loads(Path(item["path"]).read_text(encoding="utf-8"))
        if (bundle["start_ms"] != item["start_ms"]
                or bundle["end_ms"] != item["end_ms"]
                or bundle["video_sha256"] != item["video_sha256"]
                or len(bundle["clips"]) != 1):
            raise ValueError("Clip plan differs from its evidence bundle")
        clip = bundle["clips"][0]
        audio = Path(clip["audio_clip"])
        if (clip["video_start_ms"] != item["start_ms"]
                or clip["video_end_ms"] != item["end_ms"]
                or clip["audio_sha256"] != digest(audio)):
            raise ValueError("Approved audio clip changed")
        total_ms += item["end_ms"] - item["start_ms"]
        jobs.append({"id": item["id"], "audio": audio,
                     "audio_sha256": clip["audio_sha256"],
                     "video_sha256": bundle["video_sha256"],
                     "start_ms": item["start_ms"], "end_ms": item["end_ms"]})
    if total_ms > 90_000 or len({item["id"] for item in jobs}) != len(jobs):
        raise ValueError("Scribe plan exceeds the approved audio volume")
    return jobs, total_ms


def private_key(path):
    if not path.is_file() or stat.S_IMODE(path.stat().st_mode) != 0o600:
        raise ValueError("Scribe credential file must exist with mode 0600")
    lines = path.read_text(encoding="utf-8").splitlines()
    matches = [line.split("=", 1)[1] for line in lines
               if line.startswith("ELEVENLABS_API_KEY=")]
    if len(matches) != 1 or not matches[0].strip():
        raise ValueError("Private Scribe credential file lacks one API key")
    return matches[0].strip()


def multipart_body(audio, boundary):
    """Keep the credential out of shell arguments and request body."""
    parts = []
    for name, value in SETTINGS.items():
        parts.append((f"--{boundary}\r\nContent-Disposition: form-data; "
                      f'name="{name}"\r\n\r\n{value}\r\n').encode())
    parts.append((f"--{boundary}\r\nContent-Disposition: form-data; "
                  f'name="file"; filename="clip.wav"\r\n'
                  "Content-Type: audio/wav\r\n\r\n").encode())
    parts.append(audio.read_bytes())
    parts.append(f"\r\n--{boundary}--\r\n".encode())
    return b"".join(parts)


def recognize(audio, key):
    boundary = uuid.uuid4().hex
    request = urllib.request.Request(
        ENDPOINT, data=multipart_body(audio, boundary),
        headers={"xi-api-key": key,
                 "Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            result = json.load(response)
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"Scribe request failed: HTTP {error.code}") from None
    if not isinstance(result.get("text"), str) or not isinstance(result.get("words"), list):
        raise ValueError("Scribe response lacks text or word timings")
    return result


def delete_transcript(transcription_id, key):
    """Remove the provider copy after the local response has been saved."""
    if not isinstance(transcription_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", transcription_id):
        return {"status": "unavailable"}

    request = urllib.request.Request(
        f"{ENDPOINT}/transcripts/{transcription_id}",
        headers={"xi-api-key": key}, method="DELETE",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            if response.status not in (200, 204):
                return {"status": "failed", "http_status": response.status}
    except urllib.error.HTTPError as error:
        return {"status": "failed", "http_status": error.code}
    except urllib.error.URLError:
        return {"status": "failed", "error": "network"}

    return {"status": "deleted"}


def run(plan_path, output, key_file=None):
    jobs, total_ms = checked_plan(plan_path)
    if key_file is None:
        return {"model": MODEL, "calls": len(jobs), "audio_seconds": total_ms / 1000,
                "maximum_authorized_cost_usd": 5, "status": "dry_run"}
    key = private_key(key_file)
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    completed = 0
    cleanup_statuses = []
    for job in jobs:
        receipt_path = output / f"{job['id']}.json"
        identity = hashlib.sha256(json.dumps({"job": {key: value for key, value in
            job.items() if key != "audio"}, "settings": SETTINGS},
            sort_keys=True).encode()).hexdigest()
        if receipt_path.exists():
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            if (receipt.get("status") != "complete"
                    or receipt.get("input_sha256") != identity):
                raise ValueError("Existing Scribe receipt has different inputs")
        else:
            result = recognize(job["audio"], key)
            receipt = {"status": "complete", "model": MODEL,
                       "settings": SETTINGS, "input_sha256": identity,
                       "video_sha256": job["video_sha256"],
                       "audio_sha256": job["audio_sha256"],
                       "start_ms": job["start_ms"], "end_ms": job["end_ms"],
                       "raw_response": result,
                       "note": "Recognition and model timestamps are evidence, not proof of speech or final alignment."}
            save_json(receipt_path, receipt)

        if "remote_cleanup" not in receipt or receipt["remote_cleanup"]["status"] == "failed":
            transcript_id = receipt["raw_response"].get("transcription_id")
            receipt["remote_cleanup"] = delete_transcript(transcript_id, key)
            save_json(receipt_path, receipt)

        cleanup_statuses.append(receipt["remote_cleanup"]["status"])
        completed += 1
    return {"model": MODEL, "calls_completed": completed,
            "audio_seconds": total_ms / 1000, "receipts": str(output),
            "remote_cleanup": cleanup_statuses}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--key-file", type=Path,
                        help="mode-0600 private file; omit for a no-upload dry run")
    args = parser.parse_args()
    print(json.dumps(run(args.plan, args.output, args.key_file)))


if __name__ == "__main__":
    main()
