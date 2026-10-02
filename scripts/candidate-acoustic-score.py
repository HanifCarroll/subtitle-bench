#!/usr/bin/env python3
"""Experimental CTC evidence: freeze blind audio decoding before scoring text."""

import argparse
import importlib.metadata
import json
import math
import resource
import runpy
import time
import unicodedata
import wave
from pathlib import Path


SOURCE = runpy.run_path(str(Path(__file__).with_name("source-review.py")))
FILE_HASH, SAVE = SOURCE["FILE_HASH"], SOURCE["save_json"]
MODEL = "mpoyraz/wav2vec2-xls-r-300m-cv7-turkish"
REVISION = "708639f50559d7970f462e13ec64d3f059ca89f6"


def normalize(text):
    text = unicodedata.normalize("NFC", text).translate(str.maketrans("Iİ", "ıi")).lower()
    return " ".join("".join(c for c in text if c.isalnum() or c.isspace() or c == "'").split())


def logsum(values):
    largest = max(values)
    return largest if largest == -math.inf else largest + math.log(sum(math.exp(v - largest) for v in values))


def ctc_score(log_probs, tokens, blank=0):
    """Sum every CTC path for one candidate, including repeat/blank transitions."""
    if not log_probs or not tokens or blank in tokens:
        raise ValueError("Need nonempty frames and a nonblank candidate")
    width = len(log_probs[0])
    if (not 0 <= blank < width or any(type(t) is not int or not 0 <= t < width for t in tokens)
            or any(len(frame) != width or any(not math.isfinite(v) or v > 0 for v in frame)
                   for frame in log_probs)):
        raise ValueError("Invalid CTC token or frame log probability")
    # 1. Expand the candidate with blanks, then initialize the first frame.
    states = [blank]
    for token in tokens:
        states.extend((token, blank))
    previous = [-math.inf] * len(states)
    previous[0] = log_probs[0][blank]
    previous[1] = log_probs[0][states[1]]
    # 2. Sum valid stay/advance/repeat paths at each following frame.
    # ponytail: O(frames * candidate characters); bounded clips and ten short candidates only.
    for frame in log_probs[1:]:
        current = []
        for index, token in enumerate(states):
            paths = [previous[index]]
            if index:
                paths.append(previous[index - 1])
            if index > 1 and token != blank and token != states[index - 2]:
                paths.append(previous[index - 2])
            current.append(logsum(paths) + frame[token])
        previous = current
    return logsum(previous[-2:])


def observe(audio, output, video_sha256, start_ms, end_ms, device):
    # 1. Consume only the original clip; no candidate or vocabulary is accepted.
    audio = audio.resolve(strict=True)
    if output.exists() or output.with_suffix(".logits.npz").exists():
        raise ValueError("Use a new output path")
    if (not 0 <= start_ms < end_ms <= start_ms + 30_000
            or len(video_sha256) != 64 or any(c not in "0123456789abcdef" for c in video_sha256)):
        raise ValueError("Need a video SHA-256 and a positive interval of at most 30 seconds")
    with wave.open(str(audio)) as wav:
        if (wav.getframerate(), wav.getnchannels(), wav.getsampwidth()) != (16000, 1, 2):
            raise ValueError("Need mono 16 kHz PCM16 audio")
        samples = wav.readframes(wav.getnframes())
        duration = wav.getnframes() / 16000
    if abs(duration - (end_ms - start_ms) / 1000) > 0.1:
        raise ValueError("Clip duration differs from the interval")
    import numpy as np
    import torch
    from transformers import Wav2Vec2ForCTC, Wav2Vec2Processor

    # 2. Load the pinned cached model and decode without candidate forcing.
    torch.set_num_threads(4)
    began = time.monotonic()
    # Deliberately omit the model card's KenLM decoder; inspect acoustic evidence first.
    processor = Wav2Vec2Processor.from_pretrained(MODEL, revision=REVISION, local_files_only=True)
    model = Wav2Vec2ForCTC.from_pretrained(MODEL, revision=REVISION, local_files_only=True).to(device).eval()
    load_seconds = time.monotonic() - began
    waveform = np.frombuffer(samples, dtype="<i2").astype("float32") / 32768
    inputs = processor(waveform, sampling_rate=16000, return_tensors="pt")
    began = time.monotonic()
    with torch.inference_mode():
        logits = model(**{key: value.to(device) for key, value in inputs.items()}).logits.cpu().float()
    elapsed = time.monotonic() - began
    decode = processor.batch_decode(logits.argmax(dim=-1))[0]
    log_probs = logits.log_softmax(dim=-1)[0].numpy()
    # 3. Freeze raw acoustic frames with input identity before text comparison.
    output.parent.mkdir(parents=True, exist_ok=True)
    frames = output.with_suffix(".logits.npz")
    np.savez_compressed(frames, logits=logits.numpy(), log_probs=log_probs)
    receipt = {"status": "complete", "kind": "experimental_ctc_observation",
               "model": MODEL, "model_revision": REVISION, "device": device,
               "runtime": {p: importlib.metadata.version(p) for p in ("torch", "transformers")},
               "video_sha256": video_sha256, "start_ms": start_ms, "end_ms": end_ms,
               "audio_clip": str(audio), "audio_sha256": FILE_HASH(audio), "raw_response": decode,
               "frames": str(frames.resolve()), "frames_sha256": FILE_HASH(frames),
               "vocabulary": processor.tokenizer.get_vocab(), "blank": model.config.pad_token_id,
               "load_seconds": load_seconds, "elapsed_seconds": elapsed,
               "process_peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
               "note": "Greedy acoustic decode without an external language model; not text approval."}
    SAVE(output, receipt)
    return receipt


def score(observation, candidates_path, output):
    # 1. Verify the frozen blind observation before considering supplied wording.
    raw = json.loads(observation.read_text())
    if (output.exists() or raw.get("status") != "complete"
            or raw.get("kind") != "experimental_ctc_observation"
            or FILE_HASH(Path(raw["audio_clip"])) != raw["audio_sha256"]
            or FILE_HASH(Path(raw["frames"])) != raw["frames_sha256"]):
        raise ValueError("Need a new output and current frozen CTC observation")
    candidates = json.loads(candidates_path.read_text())
    if (not isinstance(candidates, list) or not 2 <= len(candidates) <= 10
            or any(not isinstance(c, dict) or not isinstance(c.get("id"), str)
                   or not c["id"] or not isinstance(c.get("text"), str)
                   or not 1 <= len(c["text"]) <= 300 for c in candidates)
            or len({c["id"] for c in candidates}) != len(candidates)):
        raise ValueError("Supply two to ten uniquely identified short candidates")
    import numpy as np
    with np.load(raw["frames"], allow_pickle=False) as archive:
        probabilities = archive["log_probs"].tolist()
    # 2. Score forced paths, retaining insufficient support rather than a winner.
    rows = []
    for candidate in candidates:
        text = normalize(candidate["text"])
        tokens = [raw["vocabulary"].get(c if c != " " else "|") for c in text]
        if not tokens or any(t is None or t == raw["blank"] for t in tokens):
            raise ValueError("Candidate is empty or outside the acoustic vocabulary")
        value = ctc_score(probabilities, tokens, raw["blank"])
        rows.append({**candidate, "normalized_text": text, "token_count": len(tokens),
                     "log_probability": value if math.isfinite(value) else None,
                     "per_frame": value / len(probabilities) if math.isfinite(value) else None,
                     "per_token": value / len(tokens) if math.isfinite(value) else None})
    result = {"kind": "experimental_ctc_scores", "observation": str(observation.resolve()),
              "observation_sha256": FILE_HASH(observation), "candidates_sha256": FILE_HASH(candidates_path),
              "unconstrained_decode": raw["raw_response"], "scores": rows,
              "outcome": "insufficient_acoustic_support", "available_outcomes": [c["id"] for c in candidates] + ["neither", "insufficient_acoustic_support"],
              "note": "Scores rank forced paths, not truth. No candidate is automatically accepted; crop and length calibration required."}
    SAVE(output, result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    first = commands.add_parser("observe")
    first.add_argument("audio", type=Path)
    first.add_argument("output", type=Path)
    first.add_argument("--video-sha256", required=True)
    first.add_argument("--start-ms", type=int, required=True)
    first.add_argument("--end-ms", type=int, required=True)
    first.add_argument("--device", choices=("cpu", "mps"), default="cpu")
    second = commands.add_parser("score")
    second.add_argument("observation", type=Path)
    second.add_argument("candidates", type=Path)
    second.add_argument("output", type=Path)
    args = parser.parse_args()
    result = (observe(args.audio, args.output, args.video_sha256, args.start_ms, args.end_ms, args.device)
              if args.command == "observe" else score(args.observation, args.candidates, args.output))
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
