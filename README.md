# Subtitle Bench

Subtitle Bench connects Turkish transcription, source repair and timing, a Turkish-ready checkpoint, bulk English, contextual review, and final layout/export/playback checks. Individual episodes are development or qualification cases. Run commands from the repository root with `python3 scripts/subtitle-workbench.py`.

## Start here

| Document | Purpose |
|---|---|
| [Current process](PROCESS.md) | Authoritative production order and provisional English choice. |
| [Agent entry prompt](docs/guides/DEVELOPMENT-AGENT-PROMPT.md) | Begin or resume production with a selectable Whisper/Gemini profile. |
| [Workbench guide](docs/guides/WORKBENCH.md) | Existing commands, checkpoints and release procedure. |
| [Pipeline overview](docs/guides/SUBTITLE-PIPELINE.md) | Tool connections and remaining limitations. |
| [Environment notes](docs/guides/SETUP.md) | Recorded local setup and model versions. |
| [Development reports](docs/reports/README.md) | Results, measurements and decisions, latest first. |
| [Qualification assessment](qualification/ASSESSMENT.md) | Separate frozen-run outcomes; campaign paused. |

The latest [E023 focused correction](docs/reports/E023-FINALIZATION-2026-10-01.md#focused-development-correction) traces five failures, surfaces saved evidence before source readiness, and repairs two source passages plus the English idiom in a separate development copy. That copy remains held on the plea and police scene. The earlier finalization reconciles release evidence and compares the exact frozen pair with aligned references. Full exports and 26 passing render samples are preserved, but four source questions and an English idiom keep content acceptance held. Native playback remains separately unverified. The [production checkpoint](docs/reports/E023-SOURCE-FIRST-PRODUCTION-2026-10-01.md) retains measured stage times and prior work. The earlier [English-path comparison](docs/reports/ENGLISH-PATH-COMPARISON-2026-10-01.md) completed a 10.5-minute development section. DeepSeek drafting plus mandatory agent review was faster in that run and is the provisional English path. The earlier [E023 downstream comparison](docs/reports/E023-DOWNSTREAM-COMPARISON-2026-10-01.md) left every full-episode pair incomplete. No new workflow freeze or held-out run has started. Frozen qualification documents and path/hash snapshots describe their recorded Git revisions, not the current production strategy or directory layout.

The code and procedure are versioned here. Episode videos, commercial subtitle files, model caches, audio clips, review cases, provider credentials, and installation backups remain in the local `~/Movies/Leyla ile Mecnun/Workflow` workspace. Pass their paths to the commands; do not copy them into this repository.

The [OpenSubtitles archive helpers](opensubtitles-archive/README.md) are versioned here too; their downloaded references and credentials stay in the local archive.

[Historical scripts and research notes](history/README.md) are kept separately from the current workbench. They are snapshots, not supported entry points.

The local checks need Python 3, FFmpeg, ffprobe, and the existing Silero model. `episode-check` also needs the local MLX audio environment with Qwen3 ASR. Transcription needs whisper.cpp. English generation supports DeepSeek Flash drafts with agent correction or direct agent translation, both with contextual review; any separate billable provider call or upload requires verified authorization. None of the portable tests make a provider call.

## Portable checks

```sh
python3 scripts/test-subtitle-workbench.py
python3 scripts/source-review.py check
python3 scripts/audit-speech-coverage.py --check
python3 scripts/test-google-second-opinion.py
python3 scripts/test-translate-subtitles.py
python3 scripts/test-layout-cues.py
python3 scripts/test-layout-audit.py
python3 scripts/test-semantic-review.py
python3 scripts/test-elevenlabs-scribe-trial.py
python3 scripts/test-production-paths.py
python3 scripts/test-local-audio-review.py
python3 scripts/test-finalization-evidence.py
python3 scripts/test-saved-scene-evidence.py
python3 scripts/test-agent-translate.py
python3 scripts/test-bind-gemini-review.py
python3 scripts/test-join-clip-drafts.py
python3 scripts/test-read-only-pair.py
python3 scripts/test-gemini-episode-budget.py
```
