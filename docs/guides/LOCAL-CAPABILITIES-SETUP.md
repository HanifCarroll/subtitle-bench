# Local acoustic environments and operations

The [October 2 comparison](../reports/LOCAL-CAPABILITY-EXPANSION-2026-10-02.md) records executed model revisions, disk requirements, controls, and decisions. FireRed is targeted activity evidence. The CTC scorer failed calibration and remains experimental. The other installed configurations are diagnostic, not production defaults. SAM is blocked pending manual access acceptance.

All environments and models stay outside Git. Reuse an existing matching environment; reconstruct in a new directory when versions differ. Never recreate or upgrade a known-working environment in place. Full resolved package lists and private test drivers were saved with the experiment. These equivalent reconstruction commands pin tested top-level packages; a changed dependency resolution is a new configuration.

## Environments

Base: `~/.local/share/subtitle-bench/`. The four new environments use Python 3.11.14; preserved `env-mlx` uses 3.14.5.

| Environment | Tested packages | Purpose / allocated size |
|---|---|---|
| `env-mlx`, preserved | mlx-audio 0.5.6, MLX 0.32.3, transformers 5.17.0 | Qwen precision comparison |
| `env-whisperx`, preserved | WhisperX 3.8.6, torch/torchaudio 2.8.0, transformers 4.57.6 | Turkish timing |
| `env-firered` | FireRed code `c30ec49e8cc69642b0ee65362eba11b9d11c6e54` (package 0.0.2), torch/torchaudio 2.10.0 | AED/VAD; 0.454 GiB |
| `env-vlm` | mlx-vlm 0.7.4, mlx-audio 0.5.7, MLX 0.32.3, transformers 5.18.0 | Gemma/Omni/VibeVoice; 0.585 GiB |
| `env-separator` | audio-separator 0.47.0, torch 2.14.1, torchvision 0.29.1, onnxruntime 1.30.0 | BS-RoFormer, MPS; 1.034 GiB |
| `env-ctc` | omnilingual-asr 0.2.0, fairseq2/fairseq2n 0.6, torch/torchaudio 2.8.0, transformers 5.18.0, numpy 1.26.4 | Native CTC, scorer, conversion; 1.095 GiB |

Demucs retains its existing `source-separation-2026-09-27/.venv` in the private media workspace. FFmpeg 8.1.2 and whisper.cpp 1.9.1 remain system tools.

For a fresh installation only:

```sh
bench_tools="$HOME/.local/share/subtitle-bench"
git clone https://github.com/FireRedTeam/FireRedVAD "$bench_tools/FireRedVAD"
git -C "$bench_tools/FireRedVAD" checkout c30ec49e8cc69642b0ee65362eba11b9d11c6e54
uv venv --python 3.11.14 "$bench_tools/env-firered"
uv pip install --python "$bench_tools/env-firered/bin/python" \
  "$bench_tools/FireRedVAD" 'torch==2.10.0' 'torchaudio==2.10.0'

uv venv --python 3.11.14 "$bench_tools/env-vlm"
uv pip install --python "$bench_tools/env-vlm/bin/python" \
  'mlx-vlm==0.7.4' 'mlx-audio==0.5.7' 'mlx==0.32.3' 'transformers==5.18.0'

uv venv --python 3.11.14 "$bench_tools/env-separator"
uv pip install --python "$bench_tools/env-separator/bin/python" \
  'audio-separator==0.47.0' 'torch==2.14.1' 'torchvision==0.29.1' 'onnxruntime==1.30.0'

uv venv --python 3.11.14 "$bench_tools/env-ctc"
uv pip install --python "$bench_tools/env-ctc/bin/python" \
  'omnilingual-asr==0.2.0' 'fairseq2==0.6' 'fairseq2n==0.6' \
  'torch==2.8.0' 'torchaudio==2.8.0' 'transformers==5.18.0' 'numpy==1.26.4'
```

The initial separator torch 2.10 pin conflicted with its Mac/MPS requirement; 2.14.1 works. Omnilingual's fairseq2 wheel requires matching torch/torchaudio 2.8; resolver-selected torchaudio 2.11 was incompatible. Both failures were repaired inside new environments.

## Downloads and access

Hugging Face snapshots use `~/.cache/huggingface/hub/`. Pin both repository and revision from the report. For example:

```sh
"$bench_tools/env-firered/bin/hf" download FireRedTeam/FireRedVAD \
  --revision 7990aaccc6b7aec1e527743bd30201f2c4a03b8c --include 'AED/*' 'VAD/*'
```

Native Omnilingual uses official URLs `https://dl.fbaipublicfiles.com/mms/omniASR-CTC-300M-v2.pt` and `https://dl.fbaipublicfiles.com/mms/omniASR-CTC-1B-v2.pt`. Verify the report's checkpoint hashes. The inspected official repository is `81f51e224ce9e74b02cc2a3eaf21b2d91d743455`; the tested `ASRInferencePipeline` is CPU FP32, four threads, no language model/hotwords. `tur_Latn` is documented; native CTC itself has no language conditioning. Inputs were at most 30 seconds, below its 40-second limit. Logits were preserved before text assessment.

RoFormer file/config: `$bench_tools/models/roformer/model_bs_roformer_ep_317_sdr_12.9755.ckpt` and matching YAML. The inspected [audio-separator](https://github.com/nomadkaraoke/python-audio-separator) revision is `45127bd2504819373f4108df08ca100fe4c23e81`. Its tested `Separator` uses MPS, one model, default settings, and WAV/PCM16 output. Code licensing does not establish the separate weight license.

Turkish Whisper conversion uses whisper.cpp 1.9.1 source `f049fff95a089aa9969deb009cdd4892b3e74916`, `models/convert-h5-to-ggml.py`, the pinned fine-tune snapshot, and mel assets from OpenAI Whisper `86098128c0b4f24f0e2aa2994de830614b474227`. The converter's default is FP16. Output: `$bench_tools/models/whisper-turkish/ggml-model.bin`, 1.625 GB in addition to 3.240 GB downloaded. Matched original/fine-tuned decoding uses fresh whisper.cpp processes, four threads, beam/best-of five, temperature zero and identical default fallback; raw full JSON/SRT remain private.

About 31.74 GB of new model/build artifacts were retained. Environments, source checkouts, clips, results, and backups need additional disk. Existing Omni/Qwen/aligner caches were reused. Do not delete caches or large files to make space without permission.

SAM action: sign in at [facebook/sam-audio-small](https://huggingface.co/facebook/sam-audio-small), review/accept the SAM license/contact-sharing terms, request access and wait for approval, then authenticate locally with `hf auth login`. Never paste the token into chat. Public MLX conversions are not an access-control workaround. No SAM weights were downloaded.

## FireRed and existing scene review

Use an original mono 16 kHz PCM16 clip, exact video-relative interval, original video SHA-256, and new output paths. The helper saves raw detector output, hashed frame probabilities, and typed observations; it rejects duration/interval/probability errors and overwritten outputs.

```sh
"$bench_tools/env-firered/bin/python" scripts/audio-event-map.py \
  /private/scene.original.wav /private/scene.events.json \
  --video-sha256 ORIGINAL_VIDEO_SHA256 --start-ms 120000 --end-ms 150000 \
  --model-dir "$HOME/.cache/huggingface/hub/models--FireRedTeam--FireRedVAD/snapshots/7990aaccc6b7aec1e527743bd30201f2c4a03b8c/AED" \
  --revision 7990aaccc6b7aec1e527743bd30201f2c4a03b8c
```

Add one entry to the existing case's `saved_evidence` list:

```json
{
  "path": "/private/scene.events.json",
  "sha256": "SHA256_OF_RECEIPT",
  "start_ms": 120000,
  "end_ms": 150000,
  "model": "FireRedTeam/FireRedVAD/AED"
}
```

Run the normal scene `bundle`. Source-review validates video identity, receipt/clip/frame hashes, intervals, model revision, and observation kinds. Speech/singing/music may overlap. Empty events do not establish silence. Event rows enter the timeline without becoming ASR words, automatic gap decisions, deletion, or cue trimming. A revision label is provenance, not a signature or accuracy guarantee.

## Rejected CTC experiment

`observe` accepts only audio/identity, loads the already-cached Turkish wav2vec2 revision, and freezes blind greedy decoding/logits. `score` then validates frozen files, normalizes Turkish I/İ, rejects out-of-vocabulary text, and reports summed CTC-path scores per frame and per token. No language model is added.

```sh
"$bench_tools/env-ctc/bin/python" scripts/candidate-acoustic-score.py observe \
  /private/reply.original.wav /private/reply.observation.json \
  --video-sha256 ORIGINAL_VIDEO_SHA256 --start-ms 307190 --end-ms 308570
"$bench_tools/env-ctc/bin/python" scripts/candidate-acoustic-score.py score \
  /private/reply.observation.json /private/candidates.json /private/reply.scores.json
```

Candidates are two to ten unique `{ "id": "reading_a", "text": "candidate" }` entries, each at most 300 characters, supplied only after blind observation. Clips are at most 30 seconds; default device is CPU. Preserve `neither` or `insufficient_acoustic_support` in the agent assessment. The tool defaults to insufficient support and never writes source decisions. **Do not connect ranking to readiness or repair acceptance: calibration failed.**

## Diagnostic audio paths and runner audit

Gemma/Omni use MLX-VLM 0.7.4 `load`, `apply_chat_template(..., num_audios=1)`, and `generate(..., audio=[wav], temperature=0, max_tokens=768)`, with thinking disabled. The fixed neutral prompt requests speech/singing/music, original-language audible words, uncertainty, and turns. E4B's documented ASR prompt was additionally tested. The second Omni configuration appends `Listening to the layers, I hear:`; it is a distinct configuration. Candidate comparison follows frozen neutral observation. Failed controls prevent any production audio-language-review integration.

VibeVoice uses the pinned **long-form** ASR through mlx-audio 0.5.7, temperature zero, 2,048 tokens, prefill step 1,024, no context/hotwords. Input is resampled internally to 24 kHz. Loading the pinned local snapshot avoids the observed direct-id metadata-file fetch failure. Raw structured JSON precedes parsed turns; speaker labels remain proposals.

Qwen precision comparison uses preserved mlx-audio 0.5.6, identical at-most-30-second originals, temperature zero, 512 tokens, batch size one, no context; classroom language is automatic and others Turkish. The runtime shares a token budget across internal chunks, so a loop can leave a longer input's tail unprocessed. Workbench `audio-check` now allows 10–30-second windows and records actual generated-token counts. Token exhaustion is unusable even when text looks short.

## Checks

Run `python3 scripts/test-local-acoustic-evidence.py` without model environments for event identity/type/probability, CTC-path calculation, and Qwen token/window regressions. Run the complete [README suite](../../README.md#portable-checks) before committing an integration. Synthetic checks do not establish hearing accuracy; raw smoke/control results and scene-production evidence remain the basis for classification.
