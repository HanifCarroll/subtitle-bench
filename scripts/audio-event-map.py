#!/usr/bin/env python3
"""Save local FireRed speech/singing/music observations; never delete subtitles."""

import argparse
import importlib.metadata
import math
import resource
import runpy
import time
import wave
from pathlib import Path


SOURCE = runpy.run_path(str(Path(__file__).with_name("source-review.py")))
FILE_HASH, SAVE = SOURCE["FILE_HASH"], SOURCE["save_json"]


def event_rows(result, probabilities, start_ms, end_ms):
    """Map the detector's clip-relative events onto the original video clock."""
    rows = []
    for index, label in enumerate(("speech", "singing", "music")):
        for first, last in result["event2timestamps"].get(label, []):
            if (not math.isfinite(first) or not math.isfinite(last)
                    or not 0 <= first < last <= result["dur"] + 0.01):
                raise ValueError("Detector returned an invalid event interval")
            begin = start_ms + round(first * 1000)
            end = min(end_ms, start_ms + round(last * 1000))
            if begin >= end:
                raise ValueError("Event lies outside the requested clip")
            selected = probabilities[round(first * 100):round(last * 100)]
            confidence = (sum(frame[index] for frame in selected) / len(selected)
                          if selected else None)
            if confidence is not None and (not math.isfinite(confidence)
                                           or not 0 <= confidence <= 1):
                raise ValueError("Detector returned an invalid probability")
            rows.append({"kind": "audio_event", "start_ms": begin, "end_ms": end,
                         "label": label, "confidence": confidence,
                         "text": f"Detected {label}; activity evidence, not spoken words."})
    return rows


def run(audio, output, video_sha256, start_ms, end_ms, model_dir, revision):
    # 1. Validate the fixed clip and identify the actual checkpoint bytes.
    audio, model_dir = audio.resolve(strict=True), model_dir.resolve(strict=True)
    output = output.resolve()
    if output.exists() or not 0 <= start_ms < end_ms or end_ms - start_ms > 90_000:
        raise ValueError("Use a new output and an interval of at most 90 seconds")
    if len(video_sha256) != 64 or any(c not in "0123456789abcdef" for c in video_sha256):
        raise ValueError("Supply the original video's SHA-256")
    if not revision.strip():
        raise ValueError("Record the model revision")
    with wave.open(str(audio)) as wav:
        duration = wav.getnframes() / wav.getframerate()
        if (wav.getnchannels(), wav.getframerate(), wav.getsampwidth()) != (1, 16000, 2):
            raise ValueError("FireRed needs mono 16 kHz PCM16")
    if abs(duration - (end_ms - start_ms) / 1000) > 0.1:
        raise ValueError("Audio duration differs from the requested interval")
    checkpoint = {name: FILE_HASH(model_dir / name)
                  for name in ("model.pth.tar", "cmvn.ark")}

    # 2. Preserve both the model response and frame probabilities before review.
    from fireredvad import FireRedAed, FireRedAedConfig
    import numpy as np
    import torch

    torch.set_num_threads(4)
    began = time.monotonic()
    detector = FireRedAed.from_pretrained(str(model_dir), FireRedAedConfig(use_gpu=False))
    load_seconds = time.monotonic() - began
    began = time.monotonic()
    raw, probabilities = detector.detect(str(audio))
    elapsed = time.monotonic() - began
    frames = probabilities.tolist()
    rows = event_rows(raw, frames, start_ms, end_ms)
    output.parent.mkdir(parents=True, exist_ok=True)
    frame_path = output.with_suffix(".probabilities.npy")
    if frame_path.exists():
        raise ValueError("Frame output already exists")
    np.save(frame_path, probabilities.numpy())
    receipt = {"status": "complete", "kind": "local_acoustic_evidence",
               "model": "FireRedTeam/FireRedVAD/AED", "model_revision": revision,
               "checkpoint_sha256": checkpoint,
               "runtime": {p: importlib.metadata.version(p) for p in ("fireredvad", "torch")},
               "video_sha256": video_sha256, "start_ms": start_ms, "end_ms": end_ms,
               "audio_clip": str(audio), "audio_sha256": FILE_HASH(audio),
               "raw_response": raw, "probabilities": str(frame_path),
               "probabilities_sha256": FILE_HASH(frame_path), "observations": rows,
               "load_seconds": load_seconds, "elapsed_seconds": elapsed,
               "process_peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
               "note": "No event, absent detection, or confidence approves words or silence."}
    SAVE(output, receipt)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audio", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--video-sha256", required=True)
    parser.add_argument("--start-ms", type=int, required=True)
    parser.add_argument("--end-ms", type=int, required=True)
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--revision", required=True)
    args = parser.parse_args()
    result = run(args.audio, args.output, args.video_sha256, args.start_ms,
                 args.end_ms, args.model_dir, args.revision)
    print(f"Saved {len(result['observations'])} event intervals to {args.output}")


if __name__ == "__main__":
    main()
