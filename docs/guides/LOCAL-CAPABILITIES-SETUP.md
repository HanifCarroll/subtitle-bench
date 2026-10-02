# Local acoustic environments and operations

The [October 2 comparison](../reports/LOCAL-CAPABILITY-EXPANSION-2026-10-02.md) records executed model revisions, disk requirements, controls, and decisions. FireRed is targeted activity evidence. Qwen 8-bit is retained as a targeted operational reliability option: reduced looping at modest extra memory, with no established recovery of important outstanding meanings. The CTC scorer failed calibration and remains experimental. Other installed configurations are diagnostic, not production defaults. The completed comparison and public SAM MLX follow-up are closed; preserve their outputs, environments, and caches. SAM MLX ran with complete pretrained weights, but is rejected for production word recovery. The official reference route remains untested.

All environments and models stay outside Git. Reuse an existing matching environment; reconstruct in a new directory when versions differ. Never recreate or upgrade a known-working environment in place. Full resolved package lists and private test drivers were saved with the experiment. These equivalent reconstruction commands pin tested top-level packages; a changed dependency resolution is a new configuration.

## Environments

Base: `~/.local/share/subtitle-bench/`. The initial four new environments and the later SAM environment use Python 3.11.14; preserved `env-mlx` uses 3.14.5.

| Environment | Tested packages | Purpose / allocated size |
|---|---|---|
| `env-mlx`, preserved | mlx-audio 0.5.6, MLX 0.32.3, transformers 5.17.0 | Qwen precision comparison |
| `env-whisperx`, preserved | WhisperX 3.8.6, torch/torchaudio 2.8.0, transformers 4.57.6 | Turkish timing |
| `env-firered` | FireRed code `c30ec49e8cc69642b0ee65362eba11b9d11c6e54` (package 0.0.2), torch/torchaudio 2.10.0 | AED/VAD; 0.454 GiB |
| `env-vlm` | mlx-vlm 0.7.4, mlx-audio 0.5.7, MLX 0.32.3, transformers 5.18.0 | Gemma/Omni/VibeVoice; 0.585 GiB |
| `env-separator` | audio-separator 0.47.0, torch 2.14.1, torchvision 0.29.1, onnxruntime 1.30.0 | BS-RoFormer, MPS; 1.034 GiB |
| `env-ctc` | omnilingual-asr 0.2.0, fairseq2/fairseq2n 0.6, torch/torchaudio 2.8.0, transformers 5.18.0, numpy 1.26.4 | Native CTC, scorer, conversion; 1.095 GiB |
| `env-sam-mlx` | mlx-audio 0.5.7 at `94c7716212b2228f178d2f9c7619a591fd1b0b78`, MLX/Metal 0.32.3, transformers 5.18.0, huggingface-hub 1.33.0, numpy 2.4.6, scipy 1.17.1, sentencepiece 0.2.2, soundfile 0.13.1 | Public SAM MLX/DACVAE and T5, offline inference; 0.433 GiB |

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

The initial screen retained about 31.74 GB of new model/build artifacts; the SAM follow-up adds 3.303 GB. Environments, source checkouts, clips, results, and backups need additional disk. Existing Omni/Qwen/aligner caches were reused. Do not delete caches or large files to make space without permission.

## SAM Small public MLX follow-up

The original October 2 HEAD check returned `401 GatedRepo` for official weights. Preserve that historical receipt. The user subsequently authorized the public redistribution; approval of the original repository is **not** a blanket prerequisite for it. No protected repository or acceptance/contact-sharing form was used. A future official-reference test would separately require personal acceptance/access approval at [facebook/sam-audio-small](https://huggingface.co/facebook/sam-audio-small), then local authentication for that approved account. Never supply credentials in chat or use another person's account.

The [conversion card](https://huggingface.co/mlx-community/sam-audio-small/tree/4ca84acc5c47f64bb2acee448f835dfac65ed318) names Meta Small and mlx-audio 0.2.10, but does not pin its original base-weight revision. Its README's official-repository example must not be copied unchanged. Use the community snapshot/local path explicitly. The [SAM license](https://github.com/facebookresearch/sam-audio/blob/bb4c6999d2677c7402360e426afc01ddfad6dce0/LICENSE) still governs use and redistribution: keep the full agreement, supply it with redistributed materials, acknowledge SAM in published research, and retain its restrictions. The report acknowledges SAM Materials; the complete license and provenance are retained privately and beside the local model. Public availability does not waive these conditions.

For a **new isolated environment only**, reconstruct the tested runtime:

```sh
uv venv --python 3.11.14 "$bench_tools/env-sam-mlx"
uv pip install --python "$bench_tools/env-sam-mlx/bin/python" \
  'mlx-audio @ git+https://github.com/Blaizzy/mlx-audio.git@94c7716212b2228f178d2f9c7619a591fd1b0b78' \
  'mlx==0.32.3' 'transformers==5.18.0' 'huggingface-hub==1.33.0' \
  'numpy==2.4.6' 'scipy==1.17.1' 'sentencepiece==0.2.2' 'soundfile==0.13.1'
```

Download only these public pinned dependencies; no original Meta weights, judge, visual encoder, or automatic span predictor is required by the executed text-only path. This is not the complete reference SAM feature set. The resolved package lock remains with the private execution records.

```sh
"$bench_tools/env-sam-mlx/bin/python" - <<'PY'
from pathlib import Path
from urllib.request import urlopen
from huggingface_hub import snapshot_download
sam_path = snapshot_download(
    "mlx-community/sam-audio-small", token=False,
    revision="4ca84acc5c47f64bb2acee448f835dfac65ed318",
    allow_patterns=["config.json", "model.safetensors", "model.safetensors.index.json", "README.md"])
t5_path = snapshot_download(
    "google-t5/t5-base", token=False,
    revision="a9723ea7f1b39c1eae772870f3b547bf6ef7e6c1",
    allow_patterns=["config.json", "model.safetensors", "tokenizer.json", "spiece.model", "README.md"])
license_url = "https://raw.githubusercontent.com/facebookresearch/sam-audio/bb4c6999d2677c7402360e426afc01ddfad6dce0/LICENSE"
with urlopen(license_url, timeout=30) as response:
    Path(sam_path, "SAM-LICENSE.txt").write_bytes(response.read())
print(sam_path)
print(t5_path)
PY
```

Snapshots add about 3.303 GB: 2.409 GB SAM and 0.894 GB T5, including T5's unused decoder. Verify the report's weight/license hashes. Existing caches and working environments remain intact; no larger SAM variant is installed.

The ordinary upstream loader can swallow loading exceptions or permit missing parameters. `separate-audio-mlx.py` instead instantiates explicit local configs, checks every key/shape, uses strict base loading, and compares every loaded parameter with its checkpoint. This conversion passes with 555 SAM/DACVAE and 99 T5 encoder parameters. The T5 decoder/head are intentionally outside the executed path. Tokenizer/processor load locally; finite prompt features and exact runtime audio reception are checked before separation. Missing/failed/random weights stop execution and must not be classified as bad model quality.

```sh
sam_snapshot="$HOME/.cache/huggingface/hub/models--mlx-community--sam-audio-small/snapshots/4ca84acc5c47f64bb2acee448f835dfac65ed318"
t5_snapshot="$HOME/.cache/huggingface/hub/models--google-t5--t5-base/snapshots/a9723ea7f1b39c1eae772870f3b547bf6ef7e6c1"
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  "$bench_tools/env-sam-mlx/bin/python" scripts/separate-audio-mlx.py \
  /private/frozen.original.wav /private/new-sam-output \
  --model-dir "$sam_snapshot" --text-encoder-dir "$t5_snapshot" \
  --model-revision 4ca84acc5c47f64bb2acee448f835dfac65ed318 \
  --text-encoder-revision a9723ea7f1b39c1eae772870f3b547bf6ef7e6c1 \
  --description speech --video-sha256 ORIGINAL_VIDEO_SHA256 \
  --start-ms 300000 --end-ms 318000
```

The operation requires a new output directory. It preserves a mono 48 kHz float original and both raw/aligned target/residual views, with hashes, conversions, checkpoint audit, runtime, and memory. Only codec end padding is removed; keep existing extraction/audio offsets when mapping back to the video. It uses 10 s chunks/3 s overlap, seed 42, midpoint ODE/16 steps, and 50-frame decoding. **It applies no temporal anchors:** the upstream chunk loop ignores them, and this operation exposes no anchor option. The single-pass smoke also used no substantive anchor.

The executed smoke was the fixed 1.380 s reply; the four matched intervals were opening 0–30 s, song 565–605 s, late music 4128–4168 s, and cafe 300–318 s. Descriptions were `speech`, with `singing` for the song. The original stereo 44.1 kHz files remain intact. SAM's resampler is the pinned runtime's Kaiser polyphase implementation; ASR copies use FFmpeg 8.1.2 mono 16 kHz PCM16. No desired Turkish words or reference text entered generation. Freeze separation/recognizer outputs before any comparison.

Reuse original/Demucs/RoFormer Whisper results with identical four-interval settings: large-v3, fresh processes, four threads, beam/best-of five, temperature zero, same fallback. Qwen uses preserved mlx-audio 0.5.6, 4-bit, temperature zero, 512 tokens, batch one, no context, and at-most-30-second inputs. Reuse bounded originals; do not treat earlier 40 s separator-Qwen outputs as complete tail evidence. The only required new original recognition was the standalone reply, because no matching baseline existed. Token exhaustion remains unusable.

The matched run took 146.434 s for 127.979 s audio, with 5.755–5.771 GiB MLX peak. Contextual cafe separation preserves the supported reply, but isolated-reply separation changes a correct Whisper control. Masked words remain unsupported. This specific conversion/runtime is rejected for production word recovery; the reference implementation has no quality verdict. No useful recovery justified a new source/timing/direct-agent-English/export copy, prompt search, larger model, full episode, or broader capability search.

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

The frozen 8-bit comparison avoided two observed 4-bit loops at 3.659 versus 2.858 GiB MLX peak memory (about 0.80 GiB extra). Retain that robustness benefit for targeted use with the same guards. It does not establish an accuracy breakthrough, resolve the important outstanding meanings, or justify another benchmark/full production run. Preserve the measured outputs; no new inference is needed to apply this classification refinement.

## Checks

Run `python3 scripts/test-local-acoustic-evidence.py` without model environments for event identity/type/probability, CTC-path calculation, Qwen token/window regressions, and rejection of missing/extra/wrong-shaped pretrained weights. Run the complete [README suite](../../README.md#portable-checks) before committing an integration. Synthetic checks do not establish hearing accuracy; raw smoke/control results and scene-production evidence remain the basis for classification.
