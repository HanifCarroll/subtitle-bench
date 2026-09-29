#!/usr/bin/env python3
"""Build a source-bound review receipt from existing Whisper and Qwen runs."""

import argparse
import json
import runpy
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parent
SOURCE = runpy.run_path(str(SCRIPTS / "source-review.py"))
TIMING = runpy.run_path(str(SCRIPTS / "subtitle-timing.py"))


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")


def covering(items, start_ms, end_ms, first, last):
    selected = sorted((item for item in items
                       if item[first] < end_ms and item[last] > start_ms),
                      key=lambda item: item[first])
    cursor = start_ms
    for item in selected:
        if item[first] > cursor:
            raise ValueError("Recognition receipts leave an interval uncovered")
        cursor = max(cursor, item[last])
    if cursor < end_ms:
        raise ValueError("Recognition receipts end before the disputed interval")
    return selected


def create(video, source, start_ms, end_ms, transcription, audio_report,
           decision_path, output):
    # 1. Verify both recognizers ran on this video and cover the requested span.

    video, source = video.resolve(strict=True), source.resolve(strict=True)
    output = output.resolve()
    if not 0 <= start_ms < end_ms or output.exists():
        raise ValueError("Use a positive interval and a new output path")
    video_hash = SOURCE["FILE_HASH"](video)
    source_hash = SOURCE["FILE_HASH"](source)
    run = json.loads((transcription / "run.json").read_text(encoding="utf-8"))
    manifest = json.loads((transcription / "manifest.json").read_text(encoding="utf-8"))
    if (run.get("video_sha256") != video_hash
            or Path(manifest.get("video", "")).resolve() != Path(run.get("video", "")).resolve()
            or run.get("language") != "tr"
            or not run.get("model_sha256")
            or not Path(run.get("model", "")).is_file()
            or SOURCE["FILE_HASH"](Path(run["model"])) != run["model_sha256"]):
        raise ValueError("Whisper run is not bound to this Turkish video")
    joined_receipt = transcription / "joined/manifest.sha256"
    if (not joined_receipt.is_file()
            or joined_receipt.read_text(encoding="utf-8").strip()
            != SOURCE["FILE_HASH"](transcription / "manifest.json")):
        raise ValueError("Whisper manifest differs from its joined draft")
    whisper_clips = covering(manifest["clips"], start_ms, end_ms,
                             "core_start_ms", "core_end_ms")
    whisper_data = []
    for clip in whisper_clips:
        srt = Path(clip["srt"]).resolve(strict=True)
        completion = srt.with_suffix(".complete.json")
        saved = json.loads(completion.read_text(encoding="utf-8"))
        expected_clip = {key: clip[key] for key in
                         ("offset_ms", "core_start_ms", "core_end_ms")}
        if (saved.get("srt_sha256") != SOURCE["FILE_HASH"](srt)
                or any(saved.get("clip", {}).get(key) != value
                       for key, value in expected_clip.items())):
            raise ValueError("Whisper clip differs from its completion receipt")
        whisper_data.append({
            **clip, "srt_sha256": SOURCE["FILE_HASH"](srt),
            "text": srt.read_text(encoding="utf-8"),
        })

    audio_report = audio_report.resolve(strict=True)
    qwen = json.loads(audio_report.read_text(encoding="utf-8"))
    if (qwen.get("video_sha256") != video_hash
            or qwen.get("source_sha256") != source_hash
            or qwen.get("language", "").lower() not in ("tr", "turkish")
            or not qwen.get("model") or not qwen.get("model_revision")):
        raise ValueError("Qwen report is stale or belongs to another source")
    qwen_windows = covering(qwen["windows"], start_ms, end_ms,
                            "start_ms", "end_ms")
    if any(item.get("status") != "complete" or not item.get("text", "").strip()
           for item in qwen_windows):
        raise ValueError("Qwen report has an unusable window in this interval")

    # 2. Save the exact model outputs and the agent's separate assessment.

    decision = json.loads(decision_path.read_text(encoding="utf-8"))
    if set(decision) != {"status", "reviewer", "reason", "heard_original_audio"}:
        raise ValueError("Agent decision needs status, reviewer, reason, hearing disclosure")
    output.parent.mkdir(parents=True, exist_ok=True)
    whisper_path = output.with_name(output.stem + ".whisper.json")
    qwen_path = output.with_name(output.stem + ".qwen.json")
    if whisper_path.exists() or qwen_path.exists():
        raise ValueError("Evidence output already exists")
    save(whisper_path, {
        "video_sha256": video_hash, "run_sha256": SOURCE["FILE_HASH"](transcription / "run.json"),
        "manifest_sha256": SOURCE["FILE_HASH"](transcription / "manifest.json"),
        "clips": whisper_data,
    })
    save(qwen_path, {
        "video_sha256": video_hash, "audio_report_sha256": SOURCE["FILE_HASH"](audio_report),
        "windows": qwen_windows,
    })
    result = {
        "route": "local_asr_agent", "video_sha256": video_hash,
        "source_interval_sha256": SOURCE["source_interval_sha256"](
            TIMING["read_cues"](source), start_ms, end_ms
        ),
        "start_ms": start_ms, "end_ms": end_ms, "status": decision["status"],
        "observations": [
            {"method": "local_asr", "model": "Whisper large-v3",
             "model_version": run["model_sha256"], "video_sha256": video_hash,
             "start_ms": whisper_clips[0]["core_start_ms"],
             "end_ms": whisper_clips[-1]["core_end_ms"],
             "raw_response": str(whisper_path),
             "raw_response_sha256": SOURCE["FILE_HASH"](whisper_path)},
            {"method": "local_asr", "model": qwen["model"],
             "model_version": qwen["model_revision"], "video_sha256": video_hash,
             "start_ms": qwen_windows[0]["start_ms"],
             "end_ms": qwen_windows[-1]["end_ms"],
             "raw_response": str(qwen_path),
             "raw_response_sha256": SOURCE["FILE_HASH"](qwen_path)},
        ],
        "agent_assessment": {key: decision[key] for key in
                             ("reviewer", "reason", "heard_original_audio")},
        "note": "Two local ASR outputs and agent text comparison; not independent accuracy proof.",
    }
    save(output, result)
    blockers = SOURCE["review_result_blockers"](
        output.parent, str(output), start_ms, end_ms,
        video_hash, source_hash, result["source_interval_sha256"]
    )
    if blockers:
        for path in (output, whisper_path, qwen_path):
            path.unlink(missing_ok=True)
        raise ValueError("; ".join(blockers))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path)
    parser.add_argument("source", type=Path)
    parser.add_argument("start_ms", type=int)
    parser.add_argument("end_ms", type=int)
    parser.add_argument("transcription", type=Path, help="completed Whisper run directory")
    parser.add_argument("audio_report", type=Path, help="current Qwen audio-check JSON")
    parser.add_argument("decision", type=Path, help="agent-authored assessment JSON")
    parser.add_argument("output", type=Path, help="new review receipt JSON")
    args = parser.parse_args()
    result = create(args.video, args.source, args.start_ms, args.end_ms,
                    args.transcription, args.audio_report, args.decision, args.output)
    print(json.dumps({"receipt": str(args.output.resolve()),
                      "route": result["route"], "status": result["status"]}))


if __name__ == "__main__":
    main()
