# Subtitle pipeline

[PROCESS.md](../../PROCESS.md) is the authoritative production sequence:

Turkish transcription → Turkish repair and speech timing → Turkish ready → bulk English → contextual English review → final layout, export, and playback checks.

Use [DEVELOPMENT-AGENT-PROMPT.md](DEVELOPMENT-AGENT-PROMPT.md) to begin or resume production and [WORKBENCH.md](WORKBENCH.md) for existing tool commands. The policy is local-first hybrid, with `whisper-turbo` as the initial Turkish default. Reuse independent drafts and useful existing local recognition, activity detection, separation, frames, and alignment. After an appropriate local attempt leaves a substantive question unresolved, use authorized targeted hosted audio review; broad corruption may call for Gemini scene reconstruction. Do not exhaust local options, repeat unproductive attempts, or automatically generate a second full-episode transcript.

Finish Turkish wording and usable timing before routine English. DeepSeek Flash drafting plus agent review remains the provisional English path; direct agent translation is available when provider calls are unapproved or unavailable. English-only corrections persist in the existing checkpoint. Keep alignment, layout, export, and rendering local. Check existing authorization before spending, or obtain one consolidated episode allowance for necessary audio recovery and English generation, with scenes chosen within its scope.

Earlier source-first, per-scene repair/render, and recognizer experiments are historical records in dated reports and [history](../../history/README.md). The completed local-only comparison does not impose a permanent restriction. Retain its useful Qwen window/token fixes, optional 8-bit loop robustness, targeted FireRed evidence, environments, and caches; do not reopen the comparison or add tools by default. Qualification remains separate and paused. No new episode, full-episode experiment, provider request, or installation is authorized by this document.
