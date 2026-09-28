# Subtitle workbench

Subtitle Bench contains the agent-operated subtitle workflow. Start with [WORKBENCH.md](WORKBENCH.md) for commands and [SUBTITLE-PIPELINE.md](SUBTITLE-PIPELINE.md) for the review procedure. Run commands from this repository with `python3 scripts/subtitle-workbench.py`.

The code and procedure are versioned here. Episode videos, commercial subtitle files, model caches, audio clips, review cases, provider credentials, and installation backups remain in the local `~/Movies/Leyla ile Mecnun/Workflow` workspace. Pass their paths to the commands; do not copy them into this repository.

The [OpenSubtitles archive helpers](opensubtitles-archive/README.md) are versioned here too; their downloaded references and credentials stay in the local archive.

[Historical scripts and research notes](history/README.md) are kept separately from the current workbench. They are snapshots, not supported entry points.

The local checks need Python 3, FFmpeg, ffprobe, and the existing Silero model. `episode-check` also needs the local MLX audio environment with Qwen3 ASR. Transcription needs whisper.cpp. Translation and targeted provider review are separate, billable actions and require authorization before `--run` or a live request. None of the tests make a provider call.

Run the portable checks:

```sh
python3 scripts/test-subtitle-workbench.py
python3 scripts/source-review.py check
python3 scripts/audit-speech-coverage.py --check
python3 scripts/test-google-second-opinion.py
```
