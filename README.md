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

The latest [E023 bounded closeout](docs/reports/E023-FINALIZATION-2026-10-01.md#two-passage-development-closeout) closes development with supported repairs and honest wording uncertainty in a separate copy. Evidence reaches scene review and supported decisions reach both exports; exact obscured plea/police phrases remain unknown. The frozen pair and 26 render samples are preserved; native playback remains unverified and nothing was installed. This is reference-exposed development, not unseen-episode qualification. The [production checkpoint](docs/reports/E023-SOURCE-FIRST-PRODUCTION-2026-10-01.md) retains measured stages, and the [English-path comparison](docs/reports/ENGLISH-PATH-COMPARISON-2026-10-01.md) retains the provisional DeepSeek-plus-agent-review choice. Use the entry prompt above for one user-selected episode; no comparison campaign or new episode has started. Frozen qualification documents retain their recorded revisions.

The [October 2 local capability comparison](docs/reports/LOCAL-CAPABILITY-EXPANSION-2026-10-02.md) tests all feasible requested acoustic families on fixed E041 failures and controls. FireRed is useful for targeted activity routing; word recovery remains insufficient for another full local-only run. The public SAM MLX conversion loaded completely and was tested, but did not establish new word recovery and failed the isolated short-reply control. Meta's reference implementation remains untested. [Setup and operation notes](docs/guides/LOCAL-CAPABILITIES-SETUP.md) describe the isolated environments and small acoustic operations.

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
python3 scripts/test-local-acoustic-evidence.py
python3 scripts/test-agent-translate.py
python3 scripts/test-bind-gemini-review.py
python3 scripts/test-join-clip-drafts.py
python3 scripts/test-read-only-pair.py
python3 scripts/test-gemini-episode-budget.py
```
