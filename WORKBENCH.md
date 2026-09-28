# One-episode subtitle workbench

Use `scripts/subtitle-workbench.py` from this repository as the entry point for one video's source and English subtitles. It keeps the video and existing sidecars unchanged until `release --apply`. Case files, transcripts, decisions, reports, and backups stay outside the code repository.

The agent runs the process. Hanif does not need to listen to routine clips. Recognition and automated flags provide evidence; they can miss quiet speech, invent song words, or loop. The endpoint is an installed Turkish/English pair that can be watched. A queue entry or an unanswered lyric question is not an endpoint. A reported playback problem returns to the repair loop below.

## 1. Prepare the source draft

Inventory the video, its language, and actual subtitle files on disk. Check each candidate's episode, cut, encoding, and timing. Use a cut-matched source subtitle as the working draft when it fits. Otherwise, make a local Whisper draft from the original audio:

```sh
python3 scripts/subtitle-workbench.py transcribe VIDEO.webm TRANSCRIPTION-CASE \
  --language tr --model /path/to/ggml-large-v3-turbo.bin
```

This retains raw overlapping clips and seam evidence. The joined draft is a candidate. Keep input origin and hashes. An English subtitle cannot establish the exact Turkish words.

## 2. Open a source case

```sh
python3 scripts/subtitle-workbench.py audit VIDEO.webm SOURCE.srt REVIEW-CASE \
  --language tr --coverage
```

Use `--reference OTHER.srt` for a cut-matched source-language comparison. Use `--reference-timing-only --reference-offset-ms OFFSET` for a checked English file. If an input is not UTF-8, specify its encoding; the original is preserved. The case contains a working source SRT and a queue of long holds, repetition, overlaps, missing cue spans, voice-detection questions, and reference disagreements.

## 3. Check the whole episode

Run the same entry point in the local MLX environment. The Qwen3 ASR model is cached on this Mac; this command makes no upload. It transcribes 30-second windows of the original video and compares their words with the current source SRT. The transcript cache survives source edits, so later checks compare the repaired file without retranscribing the episode.

```sh
python3 scripts/subtitle-workbench.py episode-check REVIEW-CASE ENGLISH.srt \
  --source-language tr --target-language en --output CHECK-CASE
```

`episode-check` refreshes stale speech coverage, rebuilds the source queue, runs the independent audio comparison, checks the English timeline, and writes a release dry run. Its `episode-check.json` gives issue counts and report paths. Inspect `audio-check.json` for missing or wrong lines even when an existing subtitle covers the audio. A `repeated_asr_output` flag marks a repeated model transcript; the repetition may be real or generated, so check it before using those words. Empty or agreeing model output never proves the subtitle is correct.

If local MLX is unavailable, install or restore its pinned environment before completing this stage. Do not silently skip the independent audio check.

## 4. Resolve issues as an agent

Start with a reported playback error, repeated run, long held cue, and long missing-cue span. Then inspect the independent audio questions and translation flags. For each material interval:

1. Extract original-audio evidence with `subtitle-workbench.py review REVIEW-CASE --issue-id ID`. Long gaps are split into overlapping clips that cover the whole gap. For a known interval, run `subtitle-workbench.py bundle REVIEW-CASE ENGLISH.srt START_MS END_MS --audio-report CHECK-CASE/audio-check.json --asr-manifest FOCUSED/manifest.json`. Its JSON gathers playable original clips, nearby Turkish/English/reference cues, saved ASR on the video clock, current hashes, and issues. ASR window timing is coarse. Add `--asr-manifest` again for each relevant focused result; no new model call is made.
2. Compare the clip with local Whisper without VAD, Qwen, a cut-matched subtitle, and visible video captions where useful. Use an audio-capable agent or a separately authorized targeted provider call for difficult wording. A model's silence does not clear a gap. The current Deepgram signup credit authorizes covered calls; Gemini authorization is clip-specific.
3. Make a subtitle decision for confirmed speech. Use supported words when the evidence permits. If words remain unreliable, caption what is audible without inventing them, such as `[Şarkı söylüyor]` / `[Singing]` or `[Anlaşılmayan konuşma]` / `[Indistinct speech]`. Use no cue only when the evidence supports no relevant speech. Keep caption intervals timed to the audio; do not hold an old line across new speech.
4. Record the interval, evidence files, reviewer/model, reason, and current hashes. Use `insert-pair REVIEW-CASE ENGLISH.srt DECISION.json` to fill a confirmed source gap. Use `replace-pair REVIEW-CASE ENGLISH.srt DECISION.json` to replace or split existing cues in both tracks together. A replacement decision names `start_ms`, `end_ms`, both current file hashes, contiguous `replace_source_ids` and `replace_target_ids`, `reviewer`, `reason`, local `evidence` paths, and bilingual `cues` with `start_ms`, `end_ms`, `source_text`, and `target_text`. The two old cue ranges may have different boundaries; the new cues share one timeline. Both commands reject stale hashes, blank text, and overlap, and save before/after copies for both tracks. Use `record` only for a source-only decision with no paired English change. Never claim an agent or model output was a human review.
5. Re-run `episode-check` after edits. It refreshes stale coverage and translation reports, and reuses unchanged audio transcripts. For every `audio-check.json` issue, save an entry in `CHECK-CASE/audio-decisions.json` with the current audio report hash, current source hash, its `start_ms` and `end_ms`, a `source_supported`, `model_artifact`, or `repaired` disposition, a reason, an identified reviewer, and paths to local evidence. Repeat until known speech has an appropriate cue in both tracks and every independent audio question has a decision.

Source decisions are hash-bound. A reviewed no-speech interval remains reviewed after an unrelated subtitle edit if its exact time span is unchanged. The release command blocks every pending source question, every independent audio question without a matching decision, every English timing flag, and any recorded unresolved issue still present. These checks catch known failures; they do not prove every word. The agent decides whether each flagged interval contains speech, silence, music, or a recognizer error.

## 5. Check English and install

Translate from the repaired source when no usable English file exists. `subtitle-workbench.py translate SOURCE.srt DRAFT.en.srt --source-language tr` first prints the input size; add `--run` only for an authorized DeepSeek call. `subtitle-workbench.py translation-second-opinion SOURCE.srt DRAFT.en.srt GOOGLE-REPORT.json --source-language tr` first prints the Google request size; after authorization, add `--run --max-source-characters N` with the printed full count as the minimum cap. An existing English file still needs time and meaning comparison against the corrected source. `episode-check` flags missing counterparts and repeated English runs. An agent checks meaning in its one-minute windows and repairs mistranslations before release.

`episode-check` writes `release-check.json`. `installation_checks_passed` is a structural gate, not the finish signal. Install when confirmed speech is represented in both languages, material audio and source questions have decisions, and the agent has checked English meaning against the repaired source:

```sh
python3 scripts/subtitle-workbench.py release VIDEO.webm \
  REVIEW-CASE/working.tr.srt ENGLISH.srt --source-language tr --target-language en \
  --case REVIEW-CASE --translation-report CHECK-CASE/translation-audit.json \
  --audio-report CHECK-CASE/audio-check.json \
  --audio-decisions CHECK-CASE/audio-decisions.json \
  --output CHECK-CASE/install.json --apply --backup-dir NEW-BACKUP-DIRECTORY
```

The command verifies the current video, source and English hashes, cue structure, speech scan, coverage decisions, independent audio decisions, and recorded unresolved issues. It backs up both old sidecars, verifies the backups, installs both candidates, checks installed hashes, and rolls back on failure. Open the video in IINA and check both languages at the reported early, middle, late, and repaired intervals. Save the observed player result and hashes. If the episode shows a problem during watching, repair the relevant interval and rerun the checks. There are no separate release classes or human-review labels.
