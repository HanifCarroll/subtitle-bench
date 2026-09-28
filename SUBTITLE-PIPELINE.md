# Video to source-language and English subtitles

## Goal

For one video, produce source-language subtitles that follow the spoken words, plus English subtitles when the source language is not English. The original audio is the authority. An external SRT, embedded track, old sidecar, Whisper draft, or model response is a candidate. Keep the video and inputs unchanged, record their origins and hashes, and work on case copies outside the code repository.

The agent owns inventory, local checks, issue resolution, translation review, installation, and player verification. Hanif does not need to listen to routine clips or choose between model guesses. Paid services still follow their authorization limits: Deepgram calls are authorized while covered by its $200 signup credit; Gemini and other paid calls need their own authorization. Use local tools first and send only bounded, relevant clips when authorized. Model output is evidence, never a human hearing claim. The output is a watchable source/English pair, not an unresolved review queue.

Use [WORKBENCH.md](WORKBENCH.md) for the one-entry-point commands.

## 1. Choose a source draft

| Material on disk | Action |
| --- | --- |
| Video only | Search for an actual cut-matched source subtitle. If none fits, use `subtitle-workbench.py transcribe` on overlapping original-audio clips. |
| Existing source subtitle | Check episode, cut, language, encoding, start/middle/end anchors, drift, and omissions. Use it as the base only if it fits. |
| Whisper draft | Audit the whole draft for loops, held cues, missing turns, and clip seams. Compare a cut-matched source file if available. |
| Both draft and source subtitle | Compare by time, not cue number. Choose the better base for each section and preserve both originals. |

An English file can show where dialogue may be missing, but it cannot establish exact Turkish words. Normalize non-UTF-8 inputs on copies and record the encoding. If there is no suitable source file, transcribe original audio as mono 16 kHz in roughly five-minute overlapping clips. Keep raw outputs and review each seam. Retry suspicious passages in roughly 30-second original-audio windows without VAD. Cap output to contain model loops. Do not separate the whole episode before the first pass.

## 2. Check source words across the full video

Run `subtitle-workbench.py audit`, then `episode-check`. The latter refreshes structural and speech coverage checks and compares the whole original audio with the source SRT using an independent local Qwen3 ASR pass. Fixed 30-second audio windows are cached by video and model settings, so source edits are compared again without retranscribing. This catches a spoken run hidden under a long, wrong subtitle where voice detection alone would say “covered.”

Prioritize repeated runs and held cues first, then subtitle-free spans, independent-ASR disagreements, reference disagreements, and short replies. The queue flags every subtitle-free span of at least 10 seconds, including the opening and ending, regardless of VAD output. Repeated ASR output is its own issue; the repetition may be real or generated. Its silence does not clear a gap; words over music can be wrong. Check opening, middle, ending, songs, and repaired scenes even if a detector is quiet.

For a material interval, use `subtitle-workbench.py bundle` to gather original playable clips and the nearby Turkish, English, reference, and saved ASR evidence on one video clock. `review` still selects and extracts a pending queue issue. An agent compares focused local models, a cut-matched subtitle, and visible captions as appropriate. Demucs may help with a music-covered passage, but a separated stem cannot replace original audio. A targeted audio-capable provider can help when authorized; record the model, input clip hash, output, and any disagreement. The agent decides whether the interval contains intelligible words, unclear speech or singing, nonverbal sound, or silence. Put supported words in both tracks. For confirmed speech whose words remain unclear, use an honest timed description in both languages. A blank interval is appropriate only when there is no relevant speech. Use `insert-pair` for confirmed speech in a cue gap and `replace-pair` to correct or split existing Turkish and English cues together. Both use current file hashes, local evidence, and before/after copies. Re-run `episode-check` after edits.

Fix words before timing. Check offsets, drift, overlaps, early starts, and cues that stay visible after their speech. Do not stretch a line to fill a gap or cap it at seven seconds simply for reading speed. A long cue or voice-detection mismatch is a question; inspect the original interval before editing. Automated checks cannot establish that every word is right.

## 3. Build and check English

Start with the repaired source. If a cut-matched English file exists, compare its timing and meaning to that source. If it is absent or substantially incomplete, create a DeepSeek draft with context, then run the separately authorized Google NMT cue-by-cue second opinion. Both providers can agree and still miss an idiom, name, song, or speaker turn. The agent reviews the one-minute source/English windows and fixes omissions, mistranslations, and repeated target text. Different cue counts and boundaries are allowed. If the source changes, update the affected English lines and rerun `episode-check`.

## 4. Install, watch, repair

`episode-check` writes a current release dry run. `release --apply` needs matching video/source/target hashes, cue structure, fresh speech coverage, a decision for every source and independent ASR question, no English timing flags, and no recorded unresolved issue still present. The agent also checks English meaning; the automated checks cannot prove it. Release saves and verifies backups of both old sidecars, installs the new pair, verifies installed hashes, and rolls back both on failure. There is one release path; no human-review or provisional release classes.

Open the video in IINA. Check both subtitle languages at early, middle, late, and repaired scenes; reopen the video and verify selection/display again. Record what was actually observed. If watching exposes another problem, return to the interval, repair it, rerun the checks, and reinstall with a new backup. Keep the source and translation evidence, reports, installed hashes, and rollback files.

## Lessons from this series

- **Episode 38:** a cut-matched Turkish file covered dialogue missed by a Whisper clip join. It still needed an offset correction and disputed wording checks.
- **Episode 39:** a Whisper repetition hid much of the episode. The 22:45 dialogue lay inside a long cue-free span that the broad Silero pass missed. Later, “Ayyy!” was held across about 41 seconds of speech. The long-cue check caught that structural defect; a local Qwen pass recovered the 22:45 dialogue but repeated syllables over music near 41:23. The full pass also found singing through the 63:34–63:57 cue gap; uncertain lyrics are now timed descriptions. The repaired pair is installed, all source and audio alerts have decisions. The local case report under `Workflow/pilots/source-review/039/whole-file-repair/REPORT.md` records the evidence and playback checks.
- **Episode 40:** thousands of repeated cues hid dialogue. Short Whisper windows recovered much of it. A subtitle listing was not usable until the actual file was downloaded.
- **Speech and music:** Silero, FireRed, and Deepgram can miss quiet words or report words over music. Local detector and separation pilots under `Workflow/pilots/` show why no model result clears a passage by itself.
- **Translation:** A local context comparison under `Workflow/pilots/translation-context-spike-2026-09-27/` found that neither DeepSeek nor Google caught both senses of `şekerim` throughout a scene. Compare meaning against the corrected source, including provider agreements.
