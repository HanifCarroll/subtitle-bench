#!/usr/bin/env python3
"""Separate one local SAM MLX clip after strict pretrained-weight validation."""

import argparse
import importlib.metadata
import json
import os
import resource
import runpy
import time
from pathlib import Path


SOURCE = runpy.run_path(str(Path(__file__).with_name("source-review.py")))
FILE_HASH, SAVE = SOURCE["FILE_HASH"], SOURCE["save_json"]


def require_complete_weights(parameters, weights):
    missing = sorted(parameters.keys() - weights.keys())
    extra = sorted(weights.keys() - parameters.keys())
    shapes = sorted(k for k in parameters.keys() & weights.keys()
                    if parameters[k].shape != weights[k].shape)
    if missing or extra or shapes:
        raise ValueError(f"Incomplete pretrained weights: missing={missing}, "
                         f"extra={extra}, shape_mismatch={shapes}")


def load_local_model(model_dir, text_encoder_dir):
    # 1. Use explicit local configurations; never fall back to default weights.
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    import mlx.core as mx
    import mlx.nn as nn
    from mlx.utils import tree_flatten
    from mlx_audio.sts.models.sam_audio import SAMAudio, SAMAudioConfig
    from mlx_audio.sts.models.sam_audio.processor import SAMAudioProcessor
    from mlx_audio.sts.models.sam_audio.text_encoder import T5Config, T5Encoder
    from transformers import AutoTokenizer, T5Config as HFT5Config

    began = time.monotonic()
    model_dir = model_dir.resolve(strict=True)
    text_encoder_dir = text_encoder_dir.resolve(strict=True)
    config = SAMAudioConfig.from_dict(json.loads((model_dir / "config.json").read_text()))
    model = SAMAudio(config)
    encoder = T5Encoder(T5Config.from_hf_config(HFT5Config.from_dict(
        json.loads((text_encoder_dir / "config.json").read_text()))))
    audit = {"components": {}}
    for name, module, path in (("sam", model, model_dir),
                               ("t5_encoder", encoder, text_encoder_dir)):
        raw = mx.load(str(path / "model.safetensors"))
        weights = module.sanitize(raw)
        if name == "t5_encoder":
            # SAM uses the encoder; the public T5 decoder/head are not executed.
            weights = {k: v for k, v in weights.items()
                       if k.startswith("encoder.") or k == "shared.weight"}
        parameters = dict(tree_flatten(module.parameters()))
        require_complete_weights(parameters, weights)
        # The base loader avoids SAM's permissive override and swallowed failures.
        nn.Module.load_weights(module, list(weights.items()), strict=True)
        mx.eval(module.parameters())
        loaded = dict(tree_flatten(module.parameters()))
        if any(not mx.array_equal(value, weights[key]).item()
               for key, value in loaded.items()):
            raise ValueError(f"{name}: loaded values differ from pretrained weights")
        module.eval()
        audit["components"][name] = {
            "checkpoint_tensors": len(raw), "loaded_parameters": len(loaded),
            "loaded_bytes": sum(v.nbytes for v in loaded.values()),
            "weights_sha256": FILE_HASH(path / "model.safetensors"),
            "complete_keys_shapes_values": True}
        del raw, weights, parameters, loaded
        mx.clear_cache()
    model.text_encoder.model = encoder
    model.text_encoder.tokenizer = AutoTokenizer.from_pretrained(
        str(text_encoder_dir), local_files_only=True)
    model.processor = SAMAudioProcessor(config.audio_codec.hop_length,
                                       config.audio_codec.sample_rate)
    features, mask = model.text_encoder(["speech"])
    mx.eval(features, mask)
    if not mx.all(mx.isfinite(features)).item():
        raise ValueError("Nonfinite pretrained text-encoder features")
    audit.update(load_seconds=time.monotonic() - began, text_features_finite=True)
    return model, audit


def run(audio, output, model_dir, text_encoder_dir, description,
        model_revision, text_encoder_revision, video_sha256, start_ms, end_ms):
    # 2. Validate and preserve the input before any separation or review.
    audio, output = audio.resolve(strict=True), output.resolve()
    if output.exists() or not 0 <= start_ms < end_ms or end_ms - start_ms > 90_000:
        raise ValueError("Use a new output directory and a clip of at most 90 seconds")
    if len(video_sha256) != 64 or any(c not in "0123456789abcdef" for c in video_sha256):
        raise ValueError("Supply the original video's SHA-256")
    if not description.strip() or not model_revision.strip() or not text_encoder_revision.strip():
        raise ValueError("Record a neutral sound description and both model revisions")
    import numpy as np
    import soundfile as sf

    original, original_rate = sf.read(audio, dtype="float32", always_2d=True)
    if (original.shape[1] not in (1, 2) or not np.isfinite(original).all()
            or abs(len(original) / original_rate - (end_ms - start_ms) / 1000) > 0.1):
        raise ValueError("Invalid audio channels, values, or clip interval")
    model, audit = load_local_model(model_dir, text_encoder_dir)
    import mlx.core as mx
    from mlx_audio.utils import resample_audio

    batch = model.processor(descriptions=[description], audios=[str(audio)])
    received = np.array(batch.audios)[0, 0]
    expected = resample_audio(original.mean(axis=-1), original_rate, model.sample_rate)
    if (received.shape != expected.shape or not np.allclose(received, expected, atol=1e-7)
            or not np.isfinite(received).all() or not np.any(received)):
        raise ValueError("Runtime audio differs from the decoded/resampled original")
    output.mkdir(parents=True)
    sf.write(output / "original.wav", received, model.sample_rate, subtype="FLOAT")
    receipt = {"status": "input_verified", "video_sha256": video_sha256,
        "start_ms": start_ms, "end_ms": end_ms, "audio_clip": str(audio),
        "audio_sha256": FILE_HASH(audio), "model_dir": str(model_dir.resolve()),
        "model_revision": model_revision, "text_encoder_dir": str(text_encoder_dir.resolve()),
        "text_encoder_revision": text_encoder_revision, "pretrained_load": audit,
        "description": description, "anchors_applied": False,
        "method": "separate_long", "chunk_seconds": 10.0, "overlap_seconds": 3.0,
        "ode": {"method": "midpoint", "step_size": 2 / 32},
        "decode_chunk_frames": 50, "seed": 42,
        "input_sample_rate": original_rate, "input_samples": len(original),
        "model_sample_rate": model.sample_rate, "model_samples": len(received),
        "runtime_input_verified": True,
        "runtime": {p: importlib.metadata.version(p) for p in
                    ("mlx-audio", "mlx", "transformers", "soundfile")}}
    SAVE(output / "input.json", receipt)

    # 3. Chunked separation does not apply temporal anchors. Keep both raw stems.
    mx.reset_peak_memory()
    began = time.monotonic()
    try:
        result = model.separate_long(batch.audios, [description], chunk_seconds=10.0,
            overlap_seconds=3.0, ode_decode_chunk_size=50, seed=42)
        mx.eval(result.target, result.residual)
        elapsed = time.monotonic() - began
        views = {}
        for name, values in (("target", result.target[0]), ("residual", result.residual[0])):
            values = np.array(values).squeeze()
            if values.ndim != 1 or len(values) < len(received) or not np.isfinite(values).all():
                raise ValueError("Invalid separated waveform")
            sf.write(output / f"{name}.raw.wav", values, model.sample_rate, subtype="FLOAT")
            # Only codec padding at the end is removed; no time shift or normalization.
            sf.write(output / f"{name}.wav", values[:len(received)],
                     model.sample_rate, subtype="FLOAT")
            views[name] = {"raw_samples": len(values), "aligned_samples": len(received),
                          "padding_removed_samples": len(values) - len(received)}
        receipt.update(status="complete", views=views, elapsed_seconds=elapsed,
            mlx_peak_bytes=mx.get_peak_memory(),
            process_peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            files={p.name: FILE_HASH(p) for p in sorted(output.glob("*.wav"))},
            note="Separated audio is evidence; it does not establish spoken words or silence.")
        SAVE(output / "result.json", receipt)
    except Exception as error:
        receipt.update(status="execution_failure", error=str(error), quality_result=False,
                       elapsed_seconds=time.monotonic() - began)
        SAVE(output / "failure.json", receipt)
        raise
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audio", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--text-encoder-dir", type=Path, required=True)
    parser.add_argument("--description", required=True)
    parser.add_argument("--model-revision", required=True)
    parser.add_argument("--text-encoder-revision", required=True)
    parser.add_argument("--video-sha256", required=True)
    parser.add_argument("--start-ms", type=int, required=True)
    parser.add_argument("--end-ms", type=int, required=True)
    args = parser.parse_args()
    result = run(**vars(args))
    print(f"Saved local target/residual: {result['elapsed_seconds']:.2f} s; "
          f"MLX peak {result['mlx_peak_bytes'] / 2**30:.2f} GiB")


if __name__ == "__main__":
    main()
