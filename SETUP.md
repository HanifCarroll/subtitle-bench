# Subtitle Bench pilot environment

These are the versions observed on the 2026-09-28 Mac pilot, rather than a claim that other versions are compatible.

| Component | Observed version or revision | Used for |
| --- | --- | --- |
| macOS / hardware | macOS 27.0, Apple M1 Pro, 32 GiB RAM | Local trials and rendering |
| Python | 3.14.5 | Standard-library CLI and offline checks |
| FFmpeg / ffprobe | `ffmpeg-full` 8.1.2 with libass | Clip extraction and actual frame rendering |
| whisper.cpp | 1.9.1 | Existing baseline transcription |
| Ollama | 0.32.5 | Historical local semantic trials; not used for current text review |
| `mlx-audio` | 0.5.6 | Local Qwen3 ASR episode windows |
| Qwen3 ASR 1.7B 4-bit | `mlx-community/Qwen3-ASR-1.7B-4bit`, cached revision `78a389c776a5483b2d0d4ea5494e11012e0d6159` | Independent Turkish recognition |
| WhisperX | 3.8.6 | Corrected Turkish word alignment |
| Turkish aligner | `mpoyraz/wav2vec2-xls-r-300m-cv7-turkish`, cached `main` revision `708639f50559d7970f462e13ec64d3f059ca89f6` | WhisperX alignment; verify `DEFAULT_ALIGN_MODELS_HF['tr']` |
| `google-genai` | 2.23.0 | Bounded Gemini two-stage trial |
| VideoLingo | commit `11ca23e`, Apache-2.0 | Isolated local transcription-stage comparison |

The normal workbench and tests use the Python standard library. Keep model environments separate from the code repository and media workspace. Do not copy model weights, commercial subtitles, clips, provider responses, or credentials into Git. Before a new run, verify the executable and model versions in the chosen environment; the current default shell Python does **not** import WhisperX or `mlx-audio`.

```sh
python3 --version
ffmpeg -version
whisper-cli --help
ollama --version
python3 -m compileall -q scripts
python3 scripts/test-subtitle-workbench.py
python3 scripts/source-review.py check
python3 scripts/audit-speech-coverage.py --check
python3 scripts/test-google-second-opinion.py
python3 scripts/test-translate-subtitles.py
python3 scripts/test-layout-cues.py
python3 scripts/test-layout-audit.py
python3 scripts/test-semantic-review.py
python3 scripts/test-elevenlabs-scribe-trial.py
```

Use a Python environment containing `mlx-audio==0.5.6` for `subtitle-workbench.py audio-check` or `episode-check`. Use an environment containing `whisperx==3.8.6` for `align-turkish.py`. The scripts check the Turkish aligner name and record the model and media hashes. A different model revision is a new experiment, even with the same display name. Both models are local; neither is a listening receipt.

`gemini-audio-review.py` uses the private `google-genai==2.23.0` environment and a clip-limited plan. `elevenlabs-scribe-trial.py` uses Python's standard library; without `--key-file` it validates the three approved clips and makes no upload. A live trial requires an owner-only (`0600`) private file containing one `ELEVENLABS_API_KEY=...` line. Pass its **path**, never the key, and keep result receipts outside Git. This pilot completed three Scribe v2 calls on 68 seconds of audio and deleted all three remote transcripts after saving the local responses. It did not reveal a billed amount.

The current [experiment report](EXPERIMENTS-2026-09-28.md) names the real case paths and measured outcomes. [WORKBENCH.md](WORKBENCH.md) gives the operator sequence and release gate.
