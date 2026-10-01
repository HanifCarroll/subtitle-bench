#!/usr/bin/env python3
"""Align corrected Turkish utterances to original video audio with WhisperX."""

import argparse
import hashlib
import importlib.metadata
import json
import runpy
import subprocess
import tempfile
import time
from pathlib import Path


SEMANTIC = runpy.run_path(str(Path(__file__).with_name("semantic-review.py")))


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as content:
        for block in iter(lambda: content.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def duration_ms(video):
    result = subprocess.run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=nokey=1:noprint_wrappers=1", str(video),
    ], check=True, capture_output=True, text=True)
    return round(float(result.stdout.strip()) * 1000)


def windows(units, video_duration_ms, core_ms=60_000):
    """Assign each utterance to one core while retaining audio context."""
    if not 10_000 <= core_ms <= 120_000:
        raise ValueError("Alignment core must be between 10 and 120 seconds")
    for start in range(0, video_duration_ms, core_ms):
        end = min(start + core_ms, video_duration_ms)
        selected = [unit for unit in units
                    if start <= (unit["start_ms"] + unit["end_ms"]) // 2 < end]
        if not selected:
            continue
        audio_start = max(0, min(start - 2000,
                                 min(unit["start_ms"] for unit in selected) - 500))
        audio_end = min(video_duration_ms, max(end + 2000,
                              max(unit["end_ms"] for unit in selected) + 500))
        yield start, end, audio_start, audio_end, selected


def alignment_input(selected, start_ms, end_ms, video_sha256, model):
    return SEMANTIC["fingerprint"]({
        "video_sha256": video_sha256, "model": model,
        "audio_start_ms": start_ms, "audio_end_ms": end_ms,
        "utterances": [{"id": unit["id"], "text": unit["text"],
                        "start_ms": unit["start_ms"], "end_ms": unit["end_ms"]}
                       for unit in selected],
    })


def summarize_words(segment, unit, audio_start_ms):
    """Expose missing and suspicious alignment without changing subtitle text."""
    words = []
    unaligned = []
    suspicious = []
    for raw in segment.get("words", []):
        word = {"text": raw.get("word", ""), "score": raw.get("score")}
        if "start" not in raw or "end" not in raw:
            unaligned.append(word["text"])
        else:
            word["start_ms"] = audio_start_ms + round(raw["start"] * 1000)
            word["end_ms"] = audio_start_ms + round(raw["end"] * 1000)
            if (word["end_ms"] - word["start_ms"] > 2000
                    or word["start_ms"] < unit["start_ms"] - 700
                    or word["end_ms"] > unit["end_ms"] + 700):
                suspicious.append(word["text"])
        words.append(word)
    status = ("failed" if not words else "partial" if unaligned
              else "suspicious" if suspicious else "aligned")
    return {"id": unit["id"], "source_cue_ids": unit["cue_ids"],
            "text": unit["text"], "word_timings": words,
            "unaligned_words": unaligned, "suspicious_words": suspicious,
            "status": status}


def source_data(path):
    """Accept current Turkish SRT before English, or validate a bilingual map."""
    if path.suffix.lower() == ".srt":
        cues = SEMANTIC["read_cues"](path)
        if not cues:
            raise ValueError("Turkish source is empty")
        return {"source": str(path.resolve()), "source_sha256": digest(path),
                "utterances": [
                    {"id": f"u{cue['id']:06d}-{cue['start']:09d}",
                     "text": cue["text"], "start_ms": cue["start"],
                     "end_ms": cue["end"], "cue_ids": [cue["id"]]}
                    for cue in cues]}
    manifest = json.loads(path.read_text(encoding="utf-8"))
    SEMANTIC["validate"](manifest, Path(manifest["source"]), Path(manifest["target"]))
    return manifest


def align(video, manifest_path, output, core_ms=60_000, dry_run=False):
    """Resume per-window alignment; subtitle changes rerun only affected windows."""

    # 1. Verify immutable media and current Turkish text before loading a model.

    video = video.resolve(strict=True)
    manifest = source_data(manifest_path)
    source = Path(manifest["source"])
    video_sha256 = digest(video)
    duration = duration_ms(video)
    jobs = list(windows(manifest["utterances"], duration, core_ms))
    model_name = "mpoyraz/wav2vec2-xls-r-300m-cv7-turkish"
    model_revision = "708639f50559d7970f462e13ec64d3f059ca89f6"
    model_identity = f"{model_name}@{model_revision}"
    plan = []
    for core_start, core_end, audio_start, audio_end, selected in jobs:
        path = output / f"{core_start:09d}-{core_end:09d}.json"
        identity = alignment_input(selected, audio_start, audio_end,
                                   video_sha256, model_identity)
        saved = json.loads(path.read_text()) if path.is_file() else {}
        legacy_identity = alignment_input(selected, audio_start, audio_end,
                                          video_sha256, model_name)
        legacy_cached = (saved.get("model") == model_name
                         and not saved.get("model_revision")
                         and saved.get("input_sha256") == legacy_identity)
        cached = saved.get("input_sha256") == identity or legacy_cached
        plan.append((path, identity, audio_start, audio_end, selected, cached,
                     legacy_cached))
    if dry_run:
        return {"windows": len(plan), "cached": sum(job[5] for job in plan),
                "legacy_revision_unrecorded": sum(job[6] for job in plan),
                "model": model_name, "model_revision": model_revision,
                "video_sha256": video_sha256}

    # 2. Load the verified Turkish aligner once and process only stale windows.

    missing = [job for job in plan if not job[5]]
    if not missing:
        return {"windows": len(plan), "cached": len(plan), "aligned": 0,
                "legacy_revision_unrecorded": sum(job[6] for job in plan)}
    import whisperx
    from huggingface_hub import snapshot_download
    from whisperx.alignment import DEFAULT_ALIGN_MODELS_HF
    if DEFAULT_ALIGN_MODELS_HF.get("tr") != model_name:
        raise ValueError("Installed WhisperX selects a different Turkish aligner")
    snapshot = snapshot_download(model_name, revision=model_revision,
                                 local_files_only=True)
    model, metadata = whisperx.load_align_model(
        language_code="tr", device="cpu", model_name=snapshot,
        model_cache_only=True,
    )
    output.mkdir(parents=True, exist_ok=True)
    for path, identity, audio_start, audio_end, selected, _, _ in missing:
        with tempfile.TemporaryDirectory(prefix="subtitle-align-") as directory:
            audio = Path(directory) / "original.wav"
            subprocess.run([
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-ss", f"{audio_start / 1000:.3f}",
                "-t", f"{(audio_end - audio_start) / 1000:.3f}",
                "-i", str(video), "-vn", "-ac", "1", "-ar", "16000",
                "-c:a", "pcm_s16le", str(audio),
            ], check=True, capture_output=True)
            segments = [{"start": (unit["start_ms"] - audio_start) / 1000,
                         "end": (unit["end_ms"] - audio_start) / 1000,
                         "text": unit["text"]} for unit in selected]
            started = time.monotonic()
            samples = whisperx.load_audio(str(audio))
            aligned_units = []
            for segment, unit in zip(segments, selected):
                try:
                    aligned = whisperx.align([segment], model, metadata, samples, "cpu")
                    words = [word for sentence in aligned["segments"]
                             for word in sentence.get("words", [])]
                    aligned_units.append(summarize_words({"words": words}, unit,
                                                        audio_start))
                except Exception as error:
                    aligned_units.append({"id": unit["id"], "text": unit["text"],
                                          "source_cue_ids": unit["cue_ids"],
                                          "word_timings": [], "unaligned_words": [],
                                          "suspicious_words": [], "status": "failed",
                                          "error": str(error)})
            if digest(source) != manifest["source_sha256"]:
                raise ValueError("Turkish source changed during alignment; preserve and resume current windows")
            report = {"video": str(video), "video_sha256": video_sha256,
                      "source_sha256": manifest["source_sha256"], "manifest": str(manifest_path),
                      "model": model_name, "model_revision": model_revision,
                      "whisperx_version": importlib.metadata.version("whisperx"),
                      "device": "cpu", "audio_start_ms": audio_start,
                      "audio_end_ms": audio_end, "audio_sha256": digest(audio),
                      "input_sha256": identity,
                      "seconds": round(time.monotonic() - started, 3),
                      "utterances": aligned_units,
                      "note": "Forced timing does not establish that supplied words were spoken."}
            SEMANTIC["save_json"](path, report)
            print(json.dumps({"window": path.name, "utterances": len(selected),
                              "seconds": report["seconds"]}), flush=True)
    return {"windows": len(plan), "cached": len(plan) - len(missing),
            "aligned": len(missing),
            "legacy_revision_unrecorded": sum(job[6] for job in plan)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path)
    parser.add_argument("manifest", type=Path, help="current Turkish SRT or bilingual utterance map")
    parser.add_argument("output", type=Path)
    parser.add_argument("--window-seconds", type=int, default=60)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    print(json.dumps(align(args.video, args.manifest, args.output,
                           args.window_seconds * 1000, args.dry_run)))


if __name__ == "__main__":
    main()
