# Video to source-language and English subtitles

## Goal

For one video, produce source-language subtitles that follow the spoken words, plus English subtitles when the source language is not English. The original audio is the authority. An external SRT, embedded track, old sidecar, Whisper draft, or model response is a candidate. Keep the video and inputs unchanged, record their origins and hashes, and work on case copies outside the code repository.

The agent owns inventory, local checks, issue resolution, translation review, installation, and player verification. Hanif does not need to listen to routine clips or choose between model guesses. Check current authorization and spending limits before any provider upload or billable call; do not assume old signup credit remains. Use local tools first and send only bounded, relevant clips when authorized. Model output is evidence, never a human hearing claim. The output is a watchable source/English pair, not an unresolved review queue.

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

For a material interval, use `subtitle-workbench.py bundle` to gather original playable clips and the nearby Turkish, English, reference, and saved ASR evidence on one video clock. `review` still selects and extracts a pending queue issue. When visual context could resolve a speaker, referent, object, action, setting, or visible text, add the source cue IDs to the bundle. Inspect its scene overview and timestamped frames before, during, and after each cue; attach agent-authored observations that name the cue, frame time, and what is visible. Frames do not prove exact spoken words. An agent compares focused local speech recognition, a cut-matched subtitle, and visible captions as appropriate. Demucs may help with a music-covered passage, but a separated stem cannot replace original audio. A targeted audio-capable provider can help when authorized; record the model, input clip hash, output, and any disagreement. The agent decides whether the interval contains intelligible words, unclear speech or singing, nonverbal sound, or silence. Put supported words in both tracks. For confirmed speech whose words remain unclear, use an honest timed description in both languages. A blank interval is appropriate only when there is no relevant speech. Use `insert-pair` for confirmed speech in a cue gap and `replace-pair` to correct or split existing Turkish and English cues together. Both use current file hashes, local evidence, and before/after copies. Re-run `episode-check` after edits.

Fix words before timing. Check offsets, drift, overlaps, early starts, and cues that stay visible after their speech. Do not stretch a line to fill a gap or cap it at seven seconds simply for reading speed. A long cue or voice-detection mismatch is a question; inspect the original interval before editing. Automated checks cannot establish that every word is right.

## 3. Build and check English

Start with the repaired source. Create a provisional utterance map with explicit source-to-English links, and align corrected Turkish words against the original audio with the verified WhisperX Turkish aligner. Alignment is timing evidence, not word verification. If a cut-matched English file exists, the agent compares its timing and meaning to the Turkish source. If English is absent or incomplete, the agent translates the corrected Turkish directly. The agent reviews **every** source-linked English unit, including apparently clean lines, and records each judgment with the current text and context. It repairs material errors, rechecks the candidate, and leaves uncertain meaning blocking. A saved model critique can be explicitly adjudicated without changing correct subtitles, but it does not replace direct agent review. The reviewed text must match the linked SRT. Different display cue counts and boundaries are allowed. Source content edits invalidate affected English meaning and alignment review; layout-only changes keep unchanged audio transcripts. See [WORKBENCH.md](WORKBENCH.md) for the `review`, `adjudicate`, and `layout-repair` commands.

## 4. Install, watch, repair

`episode-check` writes a current release dry run. `release --apply` needs matching video/source/target hashes, cue structure, complete audio-window coverage with questionable and empty results resolved, fresh speech coverage, current evidence-backed source and audio decisions, no English timing flags, complete semantic review with no unresolved finding, resolved material timing or unreliable-alignment findings, and a current libass rendering receipt. The rendering receipt covers early, middle, late, and logged paired-repair boundaries for both candidates. Presentation density warnings alone do not block. These checks do not prove every word. Release saves and verifies backups of both old sidecars, installs the new pair, verifies installed hashes, and rolls back both on failure. Native IINA track selection and playback are verified separately after installation; the release report starts with `native_playback_verified: false`. There is one release path.

Open the video in IINA. Check both subtitle languages at early, middle, late, and repaired scenes; reopen the video and verify selection/display again. Record what was actually observed. If watching exposes another problem, return to the interval, repair it, rerun the checks, and reinstall with a new backup. Keep the source and translation evidence, reports, installed hashes, and rollback files.

## Lessons from this series

- **Episode 38:** a cut-matched Turkish file covered dialogue missed by a Whisper clip join. It still needed an offset correction and disputed wording checks.
- **Episode 39:** a Whisper repetition hid much of the episode. The 22:45 dialogue lay inside a long cue-free span that the broad Silero pass missed. Later, “Ayyy!” was held across 42.47 seconds while other dialogue continued. The repaired installed pair shows it for 3.97 seconds and has 11 cues in both languages within the old interval. The current working pair has an additional candidate meaning repair and remains uninstalled under the stricter September 28 gate. The local case report under `Workflow/pilots/source-review/039/whole-file-repair/REPORT.md` and [iteration results](EXPERIMENTS-2026-09-28.md) record separate evidence and blockers.
- **Episode 40:** thousands of repeated cues hid dialogue. Short Whisper windows recovered much of it. A subtitle listing was not usable until the actual file was downloaded.
- **Speech and music:** Silero, FireRed, and Deepgram can miss quiet words or report words over music. Local detector and separation pilots under `Workflow/pilots/` show why no model result clears a passage by itself.
- **Translation:** A local context comparison under `Workflow/pilots/translation-context-spike-2026-09-27/` found that neither DeepSeek nor Google caught both senses of `şekerim` throughout a scene. Compare meaning against the corrected source, including provider agreements.
