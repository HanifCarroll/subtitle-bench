# Subtitle workbench

Subtitle Bench develops and qualifies a reusable agent-operated subtitle-production process for unseen Turkish episodes. Start with [PROCESS.md](PROCESS.md) for the current strategy, [WORKBENCH.md](WORKBENCH.md) for commands, and [qualification/PROTOCOL.md](qualification/PROTOCOL.md) for held-out testing. Individual episodes are cases, not the project's deliverable. Run workbench commands from this repository with `python3 scripts/subtitle-workbench.py`.

The qualification campaign remains paused. The [recovery experiment results](RECOVERY-RESULTS-2026-09-29.md) follow the [earlier checkpoint](RECOVERY-CHECKPOINT-2026-09-29.md). A complete development episode must succeed before another workflow freeze or held-out run. [DEVELOPMENT-AGENT-PROMPT.md](DEVELOPMENT-AGENT-PROMPT.md) is the reusable entry prompt for that integration run.

The code and procedure are versioned here. Episode videos, commercial subtitle files, model caches, audio clips, review cases, provider credentials, and installation backups remain in the local `~/Movies/Leyla ile Mecnun/Workflow` workspace. Pass their paths to the commands; do not copy them into this repository.

The [OpenSubtitles archive helpers](opensubtitles-archive/README.md) are versioned here too; their downloaded references and credentials stay in the local archive.

[Historical scripts and research notes](history/README.md) are kept separately from the current workbench. They are snapshots, not supported entry points.

The local checks need Python 3, FFmpeg, ffprobe, and the existing Silero model. `episode-check` also needs the local MLX audio environment with Qwen3 ASR. Transcription needs whisper.cpp. The agent writes and reviews English directly; any separate billable provider call or upload requires verified authorization. None of the tests make a provider call. See [SETUP.md](SETUP.md) for the versions used in the current pilot and [EXPERIMENTS-2026-09-28.md](EXPERIMENTS-2026-09-28.md) for its results.

Run the portable checks:

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
python3 scripts/test-agent-translate.py
python3 scripts/test-bind-gemini-review.py
```
