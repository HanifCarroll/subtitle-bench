# One-episode subtitle workbench

Use `PROCESS.md` for the current production strategy and `scripts/subtitle-workbench.py` as the entry point for one video's source and English subtitles. It keeps the video and existing sidecars unchanged until `release --apply`. Case files, transcripts, decisions, reports, and backups stay outside the code repository.

The agent runs the process. Hanif does not need to listen to routine clips. Recognition and automated flags provide evidence; they can miss quiet speech, invent song words, or loop. The endpoint is an installed Turkish/English pair that can be watched. A queue entry or an unanswered lyric question is not an endpoint. A reported playback problem returns to the repair loop below.

## 1. Prepare the source draft

Inventory the video, its language, and actual subtitle files on disk. Check each candidate's episode, cut, encoding, and timing. Use `reference-source.py` with an independent video-clock transcript to propose a cut alignment, then check original audio before using the source subtitle as the working draft. Otherwise, make a local Whisper large-v3 draft from the original audio in 30-second cores:

```sh
python3 scripts/subtitle-workbench.py transcribe VIDEO.webm TRANSCRIPTION-CASE \
  --language tr --model /path/to/ggml-large-v3.bin \
  --chunk-seconds 30 --overlap-seconds 2
```

This retains raw overlapping clips and seam evidence. The joined draft is a candidate. Keep input origin and hashes. An English subtitle cannot establish the exact Turkish words.

## 2. Open a source case

```sh
python3 scripts/subtitle-workbench.py audit VIDEO.webm SOURCE.srt REVIEW-CASE \
  --language tr --coverage
```

Use `--reference OTHER.srt` only for a source candidate that passed cut and content checks. If the candidate failed those checks, retain its separate report and audit the ASR draft without it. Use `--reference-timing-only --reference-offset-ms OFFSET` for a checked English file. If an input is not UTF-8, specify its encoding; the original is preserved. The case contains a working source SRT and a queue of long holds, repetition, overlaps, missing cue spans, voice-detection questions, and reference disagreements.

## 3. Check the whole episode

Run the same entry point in the local MLX environment. The Qwen3 ASR model is cached on this Mac; this command makes no upload. It transcribes 30-second windows of the original video and compares their words with the current source SRT. The transcript cache survives source edits, so later checks compare the repaired file without retranscribing the episode.

```sh
python3 scripts/subtitle-workbench.py episode-check REVIEW-CASE ENGLISH.srt \
  --source-language tr --target-language en --output CHECK-CASE
```

`episode-check` refreshes stale speech coverage, rebuilds the source queue, runs independent audio comparison, checks the English timeline, and writes a release dry run. Its `episode-check.json` gives issue counts and report paths. A release requires successful audio-window coverage through the video tail. Inspect `audio-check.json` for missing replies, small word changes, and unsupported subtitle additions even when a cue overlaps the audio. Repeated, empty, failed, or truncated model output remains a review question. Agreement does not prove a passage is correct.

When English is absent, run the same independent audio stage before translating, then run `episode-check` after exporting the agent's English draft:

```sh
python3 scripts/subtitle-workbench.py audio-check REVIEW-CASE \
  --output CHECK-CASE/audio-check.json \
  --cache CHECK-CASE/audio-transcripts.json --language Turkish
```

If local MLX is unavailable, install or restore its pinned environment before completing this stage. Do not silently skip the independent audio check.

## 4. Resolve issues as an agent

Start with a reported playback error, repeated run, long held cue, and long missing-cue span. Then inspect the independent audio questions and translation flags. For each material interval:

1. Extract original-audio evidence with `subtitle-workbench.py review REVIEW-CASE --issue-id ID`. Every interval issue, including a long held cue, is split into overlapping clips that cover the disputed interval and context. For a known interval, run `subtitle-workbench.py bundle REVIEW-CASE ENGLISH.srt START_MS END_MS --audio-report CHECK-CASE/audio-check.json --layout-report CASE/layout-audit.json --asr-manifest FOCUSED/manifest.json`. Pass `-` instead of `ENGLISH.srt` when the English track is still pending; the resulting bundle explicitly has no English evidence. Its JSON records clip intervals and hashes, nearby cues, saved ASR, and overlapping source, audio, and material timing questions in one scene. Add `--asr-manifest` only for each focused-window manifest with `windows` entries and `whisper_srt` paths; the full source-transcription `manifest.json` has a different format and must be omitted. This does not make a new model call. For a cue whose speaker, referent, object, action, setting, or visible text matters, add `--visual-cue-id CUE_NUMBER` (up to six source cue IDs). The bundle saves a scene overview and PNG frames 250 ms before, at the midpoint of, and 250 ms after each cue, with timestamps and hashes. Read those frames, then write a small JSON note with `reviewer`, `scene_overview`, and `observations` entries containing `cue_id`, sampled `timestamp_ms`, `category` (`speaker`, `referent`, `object_action`, `setting`, `on_screen_text`, or `no_visual_clue`), and a specific `observation`. Rerun the same bundle with `--visual-notes NOTES.json`; it binds the notes to sampled frames and cue IDs. The result remains `frames_only` until this step is done. Visuals can clarify the scene or burned-in captions; use original audio to decide exact spoken words.
2. Compare original audio with local Whisper without VAD, Qwen, and a cut-matched subtitle where useful. When both completed local ASR runs cover the interval and the agent can resolve it from their outputs and scene context, prepare a `local_asr_agent` receipt with `scripts/local-audio-review.py`; it binds the raw outputs and identifies the agent's assessment without claiming the agent heard audio. Do not use it to wave away a material recognition conflict or possible quiet speech. For audio-capable review, observe speech and uncertainty without the disputed wording, then compare competing transcripts and both tracks with scene context. Save raw and parsed findings, clip hashes, provider/model/settings, and offsets. Model timestamps do not replace Turkish forced alignment. Provider uploads and billable calls need bounded approval.

   The local decision JSON has exactly `status` (`supported`, `corrected`, or `model_artifact`), `reviewer`, a specific `reason`, and `heard_original_audio` (normally `false`). Build the receipt after the current audio check:

   ```sh
   python3 scripts/local-audio-review.py VIDEO.webm REVIEW-CASE/working.tr.srt \
     START_MS END_MS TRANSCRIPTION-CASE CHECK-CASE/audio-check.json \
     LOCAL-DECISION.json CHECK-CASE/local-review-INTERVAL.json
   ```

   The command checks both runs' video and source hashes, covers the full disputed interval, saves the exact Whisper and Qwen outputs, and validates the receipt. Cite its result path in the paired source or audio decision. It records evidence provenance, not trusted transcription accuracy.

Before a new episode's paid audio review, group overlapping questions by scene and save the exact clip intervals and current candidate hashes. Request one episode-specific approval that counts uploaded audio once, audio processed across both passes, comparison text, model calls, and a spending cap using current provider prices. Keep each `gemini-audio-review.py` two-stage plan within its 90-second and six-call limits; set `max_output_tokens` when bounding cost. Save usage receipts, stop at the approved limits, delete provider copies after each clip, and reuse completed receipts instead of rerunning unchanged requests.
3. Make a subtitle decision for confirmed speech. Use supported words when the evidence permits. If words remain unreliable, caption what is audible without inventing them, such as `[Şarkı söylüyor]` / `[Singing]` or `[Anlaşılmayan konuşma]` / `[Indistinct speech]`. Use no cue only when the evidence supports no relevant speech. Keep caption intervals timed to the audio; do not hold an old line across new speech.
4. Record the interval, evidence files, reviewer/model, reason, and current hashes. Use `insert-pair REVIEW-CASE ENGLISH.srt DECISION.json` to fill a confirmed source gap. Use `replace-pair REVIEW-CASE ENGLISH.srt DECISION.json` to replace or split existing cues in both tracks together. A replacement decision names `start_ms`, `end_ms`, both current file hashes, contiguous `replace_source_ids` and `replace_target_ids`, `reviewer`, `reason`, local `evidence` paths, and bilingual `cues` with `start_ms`, `end_ms`, `source_text`, and `target_text`. The two old cue ranges may have different boundaries; the new cues share one timeline. For an English meaning correction supported by the Turkish text and scene alone, set `question_type` to `translation_semantics` and add `text_evidence` entries with `kind`, `path`, and `sha256`. This form must preserve Turkish text and both cue timelines exactly; it does not require an audio-model call. Both commands reject stale hashes, blank text, and overlap, and save before/after copies for both tracks. Use `record` only for a source-only decision with no paired English change. Never claim an agent or model output was a human review.
5. Re-run `episode-check` after edits. It refreshes stale coverage and translation reports, and reuses unchanged audio transcripts. For each current `audio-check.json` issue, save a decision JSON with its `start_ms`, `end_ms`, a `source_supported`, `model_artifact`, `repaired`, or `no_relevant_speech` disposition, reason, identified reviewer, local clip evidence paths, and a current audio review result from the local route above or authorized two-stage audio review. For `no_relevant_speech`, set `audible_outcome` to `silence`, `nonverbal_sound`, or `music_without_relevant_words`; this outcome requires an audio-capable review and cannot be inferred from empty ASR or absent VAD speech. Remove or retime any overlapping spoken-text cue first. Relevant but unintelligible speech remains unresolved and is recorded with `audible_outcome: unintelligible_speech` in an unresolved source decision. Run `subtitle-workbench.py audio-adjudicate CHECK-CASE/audio-check.json CHECK-CASE/audio-decisions.json DECISION.json`. This calculates the version 2 issue and source-interval hashes and validates the submitted entry independently. Other stale questions are reported but do not prevent saving valid progress. Superseded and disappeared-question decisions move to `history`; release still requires a current decision for every current question. Unrelated subtitle edits preserve valid decisions; a changed question or source interval invalidates its decision. Repeat until known speech has an appropriate cue in both tracks and every independent audio question has a decision.

Source decisions are bound to the relevant interval and evidence coverage. Recognition cache survives subtitle-only edits; a Turkish text change reruns affected alignment and English meaning review. The release command blocks pending source and audio questions, incomplete clip evidence, English timing flags, and unresolved semantic findings. The agent decides whether each flagged interval contains speech, silence, music, or a recognizer error.

If a targeted external review finds a material disagreement that the automatic audio scan missed, save it in `REVIEW-CASE/evidence-disagreements.json`. Give each item a stable ID, original-video start/end milliseconds, a short summary, and paths plus SHA-256 hashes for the saved model receipts. The file also needs the video's SHA-256. `source-review.py queue REVIEW-CASE` adds these as ordinary source questions; release then requires an interval-covering audio review result and decision. Keep disputed model proposals as candidates until that review resolves them.

## 5. Link utterances, align Turkish, and review English

Prepare a provisional source/English utterance map after source repairs. Cue timing only suggests links; inspect and confirm them against dialogue. The map gives stable source IDs, English translations with explicit source IDs, and separate display cue IDs. It supports unequal Turkish and English cue counts.

```sh
python3 scripts/semantic-review.py prepare WORKING.tr.srt WORKING.en.srt CASE/utterances.json
python3 scripts/align-turkish.py VIDEO.webm CASE/utterances.json CASE/alignment
python3 scripts/layout-audit.py VIDEO.webm CASE/utterances.json \
  CASE/alignment CASE/layout-audit.json
python3 scripts/semantic-review.py review-input CASE/utterances.json 1 \
  --batch-size 12 --glossary CASE/evidence-glossary.json
python3 scripts/semantic-review.py review CASE/utterances.json CASE/semantic-reviews \
  --agent-input CASE/agent-decisions/batch-0001.json \
  --batch-size 12 --glossary CASE/evidence-glossary.json
python3 scripts/semantic-review.py check CASE/utterances.json CASE/semantic-reviews \
  --batch-size 12 --glossary CASE/evidence-glossary.json
```

`align-turkish.py` uses WhisperX 3.8.6 and its verified Turkish model. It saves one minute at a time, including failed, unaligned, and suspicious words. It aligns corrected Turkish against original audio; English inherits timing through source links. `layout-audit.py` checks both cue languages against current word timing for possible early starts, lingering tails, missing word timing, dialogue gaps, and density. Its flags are review questions; a vocalization can continue long after a single aligned word. A supplied wrong word can still receive an alignment.

The agent reads each Turkish utterance, its linked English, and nearby dialogue directly from `review-input`. Copy that command's `review_input_sha256` into the authored response. For one batch, write `batch_number`, identified `reviewer`, explicit `correct_ids`, and `findings` with `source_id`, `verdict` (`material_error` or `uncertain`), and a specific `reason`. Every source ID must appear exactly once. `semantic-review.py review --agent-input` rejects an absent or stale fingerprint before saving judgments; `check` rejects missing, stale, or unresolved batches. Repeat for every batch. Earlier local text-model responses remain preserved as historical critique evidence, but they do not satisfy the release review gate. Local speech-recognition output may inform a disputed Turkish word; it does not decide English meaning for the agent.

For a two-unit batch, the authored file looks like this:

```json
{"batch_number":1,"reviewer":"Codex agent","review_input_sha256":"<SHA-256 from review-input>","correct_ids":["u000001-000123000"],"findings":[{"source_id":"u000002-000130020","verdict":"uncertain","reason":"The Turkish wording is disputed in the original-audio evidence."}]}
```

The utterance map's Turkish and English text must match the linked SRTs exactly apart from whitespace at cue and line boundaries. A manifest-only edit cannot approve a subtitle that still says something else. Keep the old semantic batch when repairing a translation; run `prepare --previous OLD-MAP` on the changed candidate, then record fresh agent judgments for affected batches and run `check`. The new batch must assess the delivered wording. `layout-cues.py` exports drafts only from a map that matches its linked inputs.

For a saved historical model finding, `adjudicate` can preserve the raw finding with `supported_as_written`, `repaired_rechecked`, or `unresolved`; the agent's complete direct review still controls release. A source-recognition decision needs original-audio evidence. The command retains the raw model response:

```sh
python3 scripts/semantic-review.py adjudicate CASE/utterances.json \
  CASE/semantic-reviews CASE/semantic-decision.json \
  --model qwen3.5:27b --batch-size 12 --glossary CASE/evidence-glossary.json
```

For material timing or unreliable-alignment flags, save a timing decision with `finding` (`language:id:kind`) or `findings` for one overlapping scene, `disposition` (`false_positive`, `accepted_exception`, `alternate_timing_evidence`, or `unresolved`), reviewer, reason, and hashed evidence. Material early/lingering or cross-dialogue exceptions require an original-audio clip. Density and smaller lead/tail flags remain presentation warnings. A decision expires when its cue, word timing, or cited evidence changes:

```sh
python3 scripts/layout-audit.py adjudicate VIDEO.webm CASE/utterances.json \
  CASE/layout-audit.json CASE/timing-decisions.json CASE/timing-decision.json
```

For a supported timing repair, use `subtitle-workbench.py layout-repair REVIEW-CASE ENGLISH.srt DECISION.json`. It accepts separate `source_cues` and `target_cues` arrays with `start_ms`, `end_ms`, and `text`, so the languages can have different boundaries or cue counts. The decision also names current `semantic_manifest`, `layout_report`, `alignment_source_ids`, `accepted_words` from that alignment, an `alignment_reason`, the existing paired-repair hashes, and original-audio evidence. A two-stage review result is checked if supplied, but is not required for a text-preserving timing repair with current accepted alignment. It preserves all words in each language, verifies that each new cue overlaps accepted word timing, and saves both before/after tracks. Reprepare the map and rerun affected reviews, alignment, layout, rendering, and episode checks after the edit. A forced aligner alone does not establish the words.

When English is absent, translate settled Turkish directly in source-bound batches. Start with `python3 scripts/agent-translate.py batch-input WORKING.tr.srt CASE/agent-translation-progress.json 1 --batch-size 12`. For each batch, author JSON with `batch_number`, the returned `input_sha256`, identified `reviewer`, and `translations` containing every selected `cue_id` once. Give a settled cue English `text`; give a disputed cue a specific `defer_reason` instead. Run `python3 scripts/agent-translate.py apply WORKING.tr.srt CASE/agent-translation-progress.json CASE/english-batch-0001.json`; continue other batches without translating the disputed source. `export ... CASE/working.partial.en.srt --partial` writes only settled cues and a manifest of excluded source IDs for inspection, never release. After the source is repaired, rerun `batch-input` for affected batches: the checkpoint retains unambiguous unchanged translations and invalidates the changed cue plus two neighbors on each side. Resolve deferrals, then run `export ... CASE/working.en.srt` for a complete draft. `semantic-review.py prepare` then creates explicit links for direct English review. `layout-cues.py` can later render separate Turkish/English display SRTs, preserving every linked utterance and reporting provisional links. It does not mark words accepted or install files.

## 6. Check rendering and install

Translate from the repaired source directly when no usable English file exists. Existing English needs the same source-referenced agent review. Reading-speed and cue-duration flags are presentation pressure, not permission to omit speech. Duration alone does not block installation; current alignment findings still require resolution.

Run headless rendering on separate candidates at early, middle, late, and repaired boundary samples. It saves real PNG frames and a report; successful libass rendering is not an IINA playback receipt.

```sh
python3 scripts/playback-check.py VIDEO.webm WORKING.tr.srt WORKING.en.srt \
  CASE/render-check --at-ms REPAIR_TIME_MS
```

`episode-check` writes `release-check.json`. Install only after complete current audio coverage, semantic review, interval evidence, timing decisions, and bilingual content checks pass:

```sh
python3 scripts/subtitle-workbench.py release VIDEO.webm \
  REVIEW-CASE/working.tr.srt ENGLISH.srt --source-language tr --target-language en \
  --case REVIEW-CASE --translation-report CHECK-CASE/translation-audit.json \
  --audio-report CHECK-CASE/audio-check.json \
  --audio-decisions CHECK-CASE/audio-decisions.json \
  --semantic-manifest CASE/utterances.json \
  --semantic-reviews CASE/semantic-reviews \
  --layout-report CASE/layout-audit.json \
  --timing-decisions CASE/timing-decisions.json \
  --render-report CASE/render-check/playback-check.json \
  --glossary CASE/evidence-glossary.json \
  --output CHECK-CASE/install.json --apply --backup-dir NEW-BACKUP-DIRECTORY
```

The command verifies video, subtitle and report hashes, cue structure, speech coverage, source and audio decisions, English timing, and current semantic review. It backs up both installed sidecars, verifies the backups, installs both candidates, checks installed hashes, and rolls back on failure. Open the video in IINA and check both languages at early, middle, late, and repaired intervals. Save observed player state and hashes. Any playback problem returns to the repair loop.
