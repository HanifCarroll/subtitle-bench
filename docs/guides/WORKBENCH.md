# One-episode subtitle workbench

Use `PROCESS.md` as the authoritative production sequence; this document gives command syntax and `scripts/subtitle-workbench.py` as the entry point for one video's source and English subtitles. It keeps the video and existing sidecars unchanged until `release --apply`. Case files, transcripts, decisions, reports, and backups stay outside the code repository.

The agent runs the process. Hanif does not need to listen to routine clips. Recognition and automated flags provide evidence; they can miss quiet speech, invent song words, or loop. The independent development endpoint is a frozen Turkish/English pair and an honest dry release outcome. Installation and normal viewing are a separate acceptance step. A queue entry or an unanswered ordinary dialogue question is not a completed pair.

## 1. Prepare the source draft

Inventory and hash the video. Reuse a completed independent draft and matching receipts when available. Default new initial Turkish recognition to `whisper-turbo` under the local-first hybrid policy:

```sh
python3 scripts/subtitle-workbench.py transcribe VIDEO.webm TRANSCRIPTION-CASE \
  --profile whisper-turbo

# Explicitly selected Gemini alternative; execution needs episode authorization.
python3 scripts/subtitle-workbench.py transcribe VIDEO.webm TRANSCRIPTION-CASE \
  --profile gemini-five-minute
python3 scripts/subtitle-workbench.py transcribe VIDEO.webm TRANSCRIPTION-CASE \
  --profile gemini-five-minute --authorization AUTHORIZATION.json --apply
```

Both tested profiles use 300-second cores and five-second overlap. Whisper starts one fresh CLI process per clip and uses large-v3-turbo without VAD. The Gemini initial profile is an explicitly selected alternative, not an automatic second full-episode transcript. It uses 32,768 output tokens per independent request; allow up to 310 seconds per clip in its existing episode budget. `run.json` records actual settings and hashes. The Gemini route needs a Python environment with `google-genai`; it never invokes the older full-audio script. Other explicit Whisper settings remain available for targeted evidence or historical reproduction.

The joined draft retains overlapping alternatives and seam evidence. Optional `join-clip-drafts.py MANIFEST CORE-OUTPUT --core-only` selects provisional midpoint ownership; inspect saved seams to settle duplicates and boundary-crossing utterances. Neither join accepts the final source wording.

## 2. Open a source case

```sh
python3 scripts/subtitle-workbench.py audit VIDEO.webm SOURCE.srt REVIEW-CASE \
  --language tr --coverage
```

Do not pass `--reference` or `--reference-timing-only` before the independent freeze. Those options remain for explicitly reference-assisted work after the comparison boundary. If a later reference fails cut or content checks, retain its separate report instead of feeding it into active repair queues. The case contains a working source SRT and a queue of long holds, repetition, overlaps, missing cue spans, and voice-detection questions.

## 3. Assess source coverage and recognition questions

Use saved recognition/coverage evidence first. When an independent local comparison is useful, run the same entry point in the local MLX environment. The Qwen3 ASR model is cached on this Mac; this command makes no upload. It transcribes 30-second windows of the original video and compares their words with the current source SRT. The transcript cache survives source edits, so later checks compare the repaired file without retranscribing the episode.

```sh
python3 scripts/subtitle-workbench.py episode-check REVIEW-CASE ENGLISH.srt \
  --source-language tr --target-language en --output CHECK-CASE
```

`episode-check` refreshes stale speech coverage, rebuilds the source queue, runs independent audio comparison, checks the English timeline, and writes a release dry run. Its `episode-check.json` gives issue counts and report paths. A release requires successful audio-window coverage through the video tail. Inspect `audio-check.json` for missing replies, small word changes, and unsupported subtitle additions even when a cue overlaps the audio. Repeated, empty, failed, or truncated model output remains a review question. Agreement does not prove a passage is correct.

When English is absent, the source-only audio command is available without a dummy English file. A later comprehensive bilingual checkpoint uses `episode-check`:

```sh
python3 scripts/subtitle-workbench.py audio-check REVIEW-CASE \
  --output CHECK-CASE/audio-check.json \
  --cache CHECK-CASE/audio-transcripts.json --language Turkish
```

Do not require a fresh full Qwen run for every profile or section. Select evidence according to the question in PROCESS.md, record unavailable evidence, and reuse completed reports. The existing release check still reports any missing evidence required for installation.

Qwen windows are limited to 10–30 seconds: the tested runtime shares a token budget across internal chunks and can skip a longer input's tail after a loop. Actual generation-token exhaustion is recorded as truncated. Optional 8-bit Qwen retains its observed loop robustness at modest extra memory, without established recovery of outstanding meanings. For music/short-reply routing, [the local capability guide](LOCAL-CAPABILITIES-SETUP.md#firered-and-existing-scene-review) shows how to add hash-bound FireRed observations to the same scene timeline. Event labels do not approve words, silence, deletion, or cue trimming; the other tested new models remain outside production acceptance. Preserve the completed comparison and installed environments/caches; do not reopen tests or add tools by default.

## 4. Resolve issues as an agent

Start with a reported playback error, repeated run, long held cue, and long missing-cue span. Then inspect the independent audio questions and translation flags. For each material interval:

1. Extract original-audio evidence with `subtitle-workbench.py review REVIEW-CASE --issue-id ID`. Every interval issue, including a long held cue, is split into overlapping clips that cover the disputed interval and context. For a known interval, run `subtitle-workbench.py bundle REVIEW-CASE ENGLISH.srt START_MS END_MS --audio-report CHECK-CASE/audio-check.json --layout-report CASE/layout-audit.json --asr-manifest FOCUSED/manifest.json`. Pass `-` instead of `ENGLISH.srt` when the English track is still pending; the resulting bundle explicitly has no English evidence. Its JSON records clip intervals and hashes, nearby cues, saved ASR, and overlapping source, audio, and material timing questions in one scene. Add `--asr-manifest` only for each focused-window manifest with `windows` entries and `whisper_srt` paths; the full source-transcription `manifest.json` has a different format and must be omitted. This does not make a new model call. For a cue whose speaker, referent, object, action, setting, or visible text matters, add `--visual-cue-id CUE_NUMBER` (up to six source cue IDs). The bundle saves a scene overview and PNG frames 250 ms before, at the midpoint of, and 250 ms after each cue, with timestamps and hashes. Read those frames, then write a small JSON note with `reviewer`, `scene_overview`, and `observations` entries containing `cue_id`, sampled `timestamp_ms`, `category` (`speaker`, `referent`, `object_action`, `setting`, `on_screen_text`, or `no_visual_clue`), and a specific `observation`. Rerun the same bundle with `--visual-notes NOTES.json`; it binds the notes to sampled frames and cue IDs. The result remains `frames_only` until this step is done. Visuals can clarify the scene or burned-in captions; use original audio to decide exact spoken words.
2. Use existing focused local recognition for disputed words, VAD for activity/boundaries, optional separation for masking, and frames for scene context. Use saved independent recognition where useful. After an appropriate local attempt leaves a substantive question unresolved, choose targeted hosted review within approved scope; hosted tools may also save time when local work is demonstrably inefficient. Do not exhaust every local option or repeat unchanged/unproductive attempts. When both completed local ASR runs cover the interval and the agent can resolve it from their outputs and scene context, prepare a `local_asr_agent` receipt with `scripts/local-audio-review.py`; it binds the raw outputs and identifies the agent's assessment without claiming the agent heard audio. Do not use it to wave away a material recognition conflict or possible quiet speech. For audio-capable review, observe speech and uncertainty without the disputed wording, then compare competing transcripts and both tracks with scene context. Save raw and parsed findings, clip hashes, provider/model/settings, and offsets. Model timestamps do not replace Turkish forced alignment. Provider uploads and billable calls need applicable episode authorization.

   The local decision JSON has exactly `status` (`supported`, `corrected`, or `model_artifact`), `reviewer`, a specific `reason`, and `heard_original_audio` (normally `false`). Build the receipt after the current audio check:

   ```sh
   python3 scripts/local-audio-review.py VIDEO.webm REVIEW-CASE/working.tr.srt \
     START_MS END_MS TRANSCRIPTION-CASE CHECK-CASE/audio-check.json \
     LOCAL-DECISION.json CHECK-CASE/local-review-INTERVAL.json
   ```

   The command checks both runs' video and source hashes, covers the full disputed interval, saves the exact Whisper and Qwen outputs, and validates the receipt. Cite its result path in the paired source or audio decision. It records evidence provenance, not trusted transcription accuracy.

Before spending or uploading, check existing episode authorization and its conservative remaining allowance. If needed, request one consolidated episode allowance covering necessary targeted audio recovery, scene reconstruction, and DeepSeek English generation. Save the approval, video/hash, providers/models, purposes, volume/call/output limits, and total spending cap privately. Allocate provider caps whose sum fits the episode allowance; count prior attempts, repeats, and reserved work. Choose scene clips within that scope without separate per-scene approval. Prior permissions for another episode, or audio-only permission, do not cover new English work.

The existing Gemini runner needs a provider-specific JSON referring to that same approval: `status: approved`, `approval_source`, `scope` (`provider: google-gemini`, `model: gemini-3.8-flash`, absolute `video`, `video_sha256`), current `pricing` (Google pricing URL and USD per million input/output tokens), and `aggregate_hard_limits` for attempted calls, uploads, uploaded seconds including repeats, processed seconds including repeats, prompt bytes, maximum clip seconds, output tokens per call, and its allocated estimated USD charge. Save it before `--apply`. DeepSeek uses the separately allocated `--max-estimated-usd` cap below. Gemini's ledger enforces its provider allocation; the agent accounts for combined episode spend from existing receipts. Do not infer a cross-provider budget check from either command.

If the user explicitly approves an episode without aggregate spending or volume limits, retain that exact approval and set `aggregate_usage_unlimited: true` in its private Gemini authorization. Only literal JSON `true` enables this exception. Keep the approved video/hash, model, purposes and current pricing. `aggregate_hard_limits` still requires `max_clip_seconds` and `max_output_tokens_per_call`; the existing 90-second scene and 8,192-token plan limits, scope checks, deletion receipts and complete usage ledger remain enforced. The exception removes aggregate cost, call, upload, audio-volume and prompt-byte ceilings; it does not authorize installation or a full-episode observation. For English within the same explicit unlimited approval, omit DeepSeek's optional `--max-estimated-usd` ceiling and retain every response/usage receipt. Bounded approval remains the default.

When measuring a complete run, record Codex plan usage and elapsed time separately from external provider spending. Do not assign API-rate dollar costs to Codex plan usage or add them to spending totals; a hypothetical API comparison requires an explicit user request and separate labeling. Distinguish provider usage estimates from reconciled invoices. Freeze the production ledger before reference evaluation, and account for preparation, comparison and later reporting separately.

Existing complete hosted recognition can also supply a `saved_asr_agent` review result without new provider calls. Keep the common current-video/source-interval hashes, interval and supported status. Its `observations` retain `method: hosted_asr`, model, original `raw_response` path/hash and `audio_path`; the validator reads coverage and input hashes from those original receipts. Use the existing distinct recognizers when available, not new calls to populate the format. Record `agent_assessment` with reviewer, a specific reason and `heard_original_audio: false`. Original hashed audio evidence must still cover the question. Missing coverage, stale media or material conflicts stay open; empty recognition is not a silence receipt.

Historical reproduction only: if an explicitly authorized experiment includes one single-request full-episode audio observation, also set `full_episode_audio_seconds` in the same authorization. Save a `full_episode_audio_observation` plan with `model: gemini-3.8-flash`, the exact `video`, `video_sha256`, `duration_ms`, `authorization` path, and `max_output_tokens` (at most 65,536). Run `python3 scripts/gemini-full-audio.py PLAN.json` to extract and hash-check audio without a provider call, then rerun it with `--apply` once. The output is an independent model observation of the audio, with raw response, usage, upload, and deletion receipts. Compare its beginning, middle, and tail with the existing source and local recognizers. Check for missing or truncated coverage; even a claimed end marker does not establish correctness. Use scene clips to resolve material disagreements. Do not copy its transcript into a release track wholesale.

For each chosen scene, make a single-clip bundle with the current Turkish candidate and, if available, English: `python3 scripts/subtitle-workbench.py bundle REVIEW-CASE ENGLISH.srt START_MS END_MS --context 0 --output SCENE/bundle.json` (use `-` while English is pending). Keep each clip within the authorization's length limit; split a longer scene. Save a `two_stage_audio_review` plan with `model: gemini-3.8-flash`, `max_calls: 2`, `max_audio_seconds` equal to or greater than the clip duration and at most 90, `max_output_tokens` no higher than the authorized per-call cap, `authorization` pointing to the approved JSON, and one `bundles` entry containing its `id`, absolute `path`, `start_ms`, `end_ms`, and the bundle's `video_sha256`, `source_sha256`, and `target_sha256`. Run `python3 scripts/gemini-audio-review.py SCENE/plan.json` to check hashes and limits without uploading, then `python3 scripts/gemini-audio-review.py SCENE/plan.json --apply`. The script counts each upload and request before attempting it in the authorization's `gemini-usage-ledger.json`, records responses and usage, and saves provider-file deletion results. An interrupted first pass may resume only if its saved response and deletion receipt are intact and the aggregate budget has room. Reuse completed receipts; do not rerun unchanged requests.
After a completed two-stage call, bind the saved receipt to the **current** source interval before recording a decision: `python3 scripts/bind-gemini-review.py PROVIDER-RECEIPT.json REVIEW-CASE START_MS END_MS REVIEW-CASE/reviews/SCENE.json --status model_artifact --audible-outcome music_without_relevant_words --reviewer 'Codex agent' --reason 'Specific comparison of the original audio and candidate'`. The bridge verifies the saved prompt, response, clip, bundle, and deletion receipts and writes a source-interval hash. Choose status and acoustic outcome from the actual evidence; its example values are not defaults. A source edit needs a new interval binding to the current candidate, but does not need another provider call when the saved audio still covers it.

When a question spans separate completed clips, add `--additional-provider-receipt OTHER.json` for each applicable receipt. Their original audio must continuously cover the question. The binding retains each independent/comparison response and its provenance, and validates every raw response hash. This is an agent aggregation of saved reviews, not another provider observation or model agreement proof.

For a broadly corrupted scene, consider reconstructing coherent Turkish from the independent Gemini observation instead of patching many cues separately. Use these same bounded scene bundles and two-stage review, splitting longer scenes into contextual overlapping clips within the existing 90-second plan and authorization limits. Preserve the independent original-audio observation before comparing candidates; do not supply desired wording in that first pass. Check missing speech, repeated text, seams, and uncertain words across the scene. Register the saved evidence, record supported scene replacements through the existing source decisions below, and align accepted Turkish locally before routine English. Plausible model text alone does not justify a replacement. Do not automatically transcribe the whole episode again.

A plan may include `independent_focus`, a neutral acoustic question of at most 2,000 UTF-8 bytes, to clarify a specific ambiguity such as human voice versus instrumental melody. Do not include candidate words, desired answers or reference text. The exact first-pass prompt is saved and checked on resume; changing the question requires a new plan/output and consumes the applicable allowance. A focused response can still contradict the first observation and must be adjudicated.

For an actual Turkish edit, write a `source-review.py record` decision with a current queue `issue_id`, `status: resolved`, `expected_working_sha256`, `reviewer`, a specific `reason`, original clip JSON paths in `evidence`, the bound `review_result` path, and either contiguous `replace_ids` plus timed `replacement` cues or `insert_after` plus timed `replacement` cues. An empty replacement removes an unsupported cue. Run `python3 scripts/source-review.py record REVIEW-CASE DECISION.json`; it retains before/after source copies. During initial production, batch these Turkish-only repairs and alignment before English exists. Check the affected source interval after edits; comprehensive source checks happen at a meaningful checkpoint. Once source work is complete, save the Turkish-ready checkpoint below and generate English in bulk. If a late source error is found during English review, `agent-translate.py batch-input` rebases the existing checkpoint, retaining unaffected text and invalidating changed cues with nearby context; retranslate and review that affected interval. A `reviewed` decision is for supported no-change only; never use it to close an unsupported source line.
3. Make a subtitle decision for confirmed speech. Use supported words when the evidence permits. Reserve `[Anlaşılmayan konuşma]` / `[Indistinct speech]` for confirmed speech whose words remain unrecoverable after targeted evidence and context review; count that span as unresolved content. Use `[Şarkı söylüyor]` / `[Singing]` only when that describes the audio. Use no cue only when evidence supports no relevant speech. Keep caption intervals timed to the audio; do not hold an old line across new speech.
4. Record the interval, evidence files, reviewer/model, reason, and current hashes. Use `insert-pair REVIEW-CASE ENGLISH.srt DECISION.json` to fill a confirmed source gap. Use `replace-pair REVIEW-CASE ENGLISH.srt DECISION.json` to replace or split existing cues in both tracks together. A replacement decision names `start_ms`, `end_ms`, both current file hashes, contiguous `replace_source_ids` and `replace_target_ids`, `reviewer`, `reason`, local `evidence` paths, and bilingual `cues` with `start_ms`, `end_ms`, `source_text`, and `target_text`. The two old cue ranges may have different boundaries; the new cues share one timeline. For an English meaning correction supported by the Turkish text and scene alone, set `question_type` to `translation_semantics` and add `text_evidence` entries with `kind`, `path`, and `sha256`. This form must preserve Turkish text and both cue timelines exactly; it does not require an audio-model call. Both commands reject stale hashes, blank text, and overlap, and save before/after copies for both tracks. Use `record` only for a source-only decision with no paired English change. Never claim an agent or model output was a human review.
5. Run `episode-check` at meaningful comprehensive bilingual checkpoints after batched edits. It refreshes stale coverage and translation reports, and reuses unchanged audio transcripts. For each current `audio-check.json` issue, save a decision JSON with its `start_ms`, `end_ms`, a `source_supported`, `model_artifact`, `repaired`, or `no_relevant_speech` disposition, reason, identified reviewer, local clip evidence paths, and a current audio review result from the local route above or authorized two-stage audio review. For `no_relevant_speech`, set `audible_outcome` to `silence`, `nonverbal_sound`, or `music_without_relevant_words`; this outcome requires an audio-capable review and cannot be inferred from empty ASR or absent VAD speech. Remove or retime any overlapping spoken-text cue first. Relevant but unintelligible speech remains unresolved and is recorded with `audible_outcome: unintelligible_speech` in an unresolved source decision. Run `subtitle-workbench.py audio-adjudicate CHECK-CASE/audio-check.json CHECK-CASE/audio-decisions.json DECISION.json`. This calculates the version 2 issue and source-interval hashes and validates the submitted entry independently. Other stale questions are reported but do not prevent saving valid progress. Superseded and disappeared-question decisions move to `history`; release still requires a current decision for every current question. Unrelated subtitle edits preserve valid decisions; a changed question or source interval invalidates its decision. Repeat until known speech has an appropriate cue in both tracks and every independent audio question has a decision.

Source decisions are bound to the relevant interval and evidence coverage. Recognition cache survives subtitle-only edits; a Turkish text change reruns affected alignment and English meaning review. The release command blocks pending source and audio questions, incomplete clip evidence, English timing flags, and unresolved semantic findings. The agent decides whether each flagged interval contains speech, silence, music, or a recognizer error.

If a targeted external review finds a material disagreement that the automatic audio scan missed, save it in `REVIEW-CASE/evidence-disagreements.json`. Closed decisions for saved conflicts also need `evidence_assessment: recognition_artifact|supported_alternative`; material unresolved questions use `material_unresolved` and stay open. Give each item a stable ID, original-video start/end milliseconds, a short summary, and paths plus SHA-256 hashes for the saved model receipts. The file also needs the video's SHA-256. `source-review.py queue REVIEW-CASE` adds these as ordinary source questions; release then requires an interval-covering audio review result and decision. Keep disputed model proposals as candidates until that review resolves them.

Register relevant saved native Scribe receipts, focused Gemini review receipts, or video-clock ASR SRTs in `CASE/case.json` before scene review. Each `saved_evidence` entry names `path`, `sha256`, `start_ms`, `end_ms`; SRT entries also name `model`. Scope registration to applicable evidence. Inspection and bundles display these in the same scene view, and the source queue includes focused proposals and saved speech in subtitle gaps. This is an adapter to the current case, not a second decision ledger. Resolve each question on its evidence; recognizer disagreement alone does not prove the candidate wrong.

## 5. Align Turkish and record readiness before English

```sh
python3 scripts/align-turkish.py VIDEO.webm WORKING.tr.srt CASE/alignment
python3 scripts/source-review.py ready WORKING.tr.srt CASE/source-ready-decision.json CASE/turkish-ready.json
python3 scripts/source-review.py check-ready WORKING.tr.srt CASE/turkish-ready.json
```

The ready decision names the current `source_sha256`, source-review `case` directory, identified `reviewer`, specific `reason`, local `evidence` paths, and `remaining_source_work: []`. Set `coverage_assessed`, `material_defects_repaired`, `speech_timing_usable`, and `ordinary_dialogue_review_complete` to true only when substantively complete. Record supported alternatives or genuinely unrecoverable speech in the reason/evidence. The small checkpoint binds this agent decision to current source/evidence hashes; it is not an automatic accuracy gate. Unfinished ordinary dialogue means incomplete source, not partial English by default.

`align-turkish.py` accepts Turkish SRT without English and uses the same source IDs as later semantic preparation. Its window cache survives unchanged words/times when English is added. If earlier edits only renumber an unchanged window's cues, the script verifies its original media, model, words, audio range and cue boundaries against the saved input hash, then rebinds IDs without inference. Changed words or boundaries still require alignment. A bilingual map still validates both linked tracks. Inspect saved word timings and batch timing repairs; forced alignment cannot establish wording.

## 6. Generate bulk English, then review meaning

Provisional English path: DeepSeek drafting after applicable episode authorization, followed by agent review and correction. Finish Turkish wording and usable timing first:

```sh
python3 scripts/subtitle-workbench.py translate WORKING.tr.srt CASE/deepseek.en.srt \
  --source-language tr --ready CASE/turkish-ready.json --glossary CASE/terminology.txt \
  --batch-size 80 --input-token-budget 6000 --max-output-tokens 8192 --concurrency 4 \
  --max-estimated-usd APPROVED_ENGLISH_USD
# The command above plans. Add --run to make authorized calls.
python3 scripts/agent-translate.py import-provider WORKING.tr.srt CASE/english-progress.json \
  CASE/deepseek.en.translation.json
```

Input batches contain four surrounding source cues on each side. The input token budget uses UTF-8 bytes as a conservative bound without another dependency; dense cues may make smaller batches. Raw provider responses live beside the draft in `.batches/`; prompt/settings and source hashes identify resumable work. Successful responses checkpoint serially even when another batch fails. Incomplete requests are not silently retried. Keep provider receipts/progress unchanged; import into the existing agent checkpoint for reviewed corrections. The `provider_draft` provenance remains distinct from agent authorship, and import/export never creates semantic approval.

Use the English allocation from the consolidated episode allowance and verified current pricing. The command's cost ceiling covers this draft's conservative estimate; account for other attempted or repeated provider work before scheduling it. For direct agent translation when provider calls are unapproved or unavailable, use `batch-input` / `apply` or `import` below with the same source context and terminology. Then run the same contextual meaning check as for a provider draft.

English-only correction:

```sh
python3 scripts/agent-translate.py correct WORKING.tr.srt CASE/english-progress.json CASE/english-correction.json
python3 scripts/agent-translate.py export WORKING.tr.srt CASE/english-progress.json CASE/reviewed.en.srt
```

The correction JSON has current `source_sha256`, current `progress_sha256` (SHA-256 of the checkpoint), identified `reviewer`, specific `reason`, and corrected `translations` rows (`cue_id`, `text`). It updates the existing checkpoint and retains prior English in history; Turkish need not change. Re-export to a new path to preserve previous drafts. Never replay an old batch over corrected English. After a paired semantic edit, record its source-linked English changes here before re-exporting.

## 7. Link utterances, review English, and finish layout

Prepare a provisional source/English utterance map after bulk generation. Cue timing only suggests links; inspect and confirm them against dialogue. The map gives stable source IDs, English translations with explicit source IDs, and separate display cue IDs. It supports unequal Turkish and English cue counts.

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

`align-turkish.py` uses WhisperX 3.8.6 and its verified Turkish model. It saves one minute at a time, including failed, unaligned, and suspicious words. It aligns corrected Turkish against original audio; English inherits timing through source links. `layout-audit.py` checks both cue languages against current word timing for possible early starts, lingering tails, missing word timing, dialogue gaps, and density. Run final layout/render checks after contextual English review. Its flags are review questions; a vocalization can continue long after a single aligned word. A supplied wrong word can still receive an alignment.

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

For a supported timing repair, use `subtitle-workbench.py layout-repair REVIEW-CASE ENGLISH.srt DECISION.json`. It accepts separate `source_cues` and `target_cues` arrays with `start_ms`, `end_ms`, and `text`, so the languages can have different boundaries or cue counts. The decision also names current `semantic_manifest`, `layout_report`, `alignment_source_ids`, `accepted_words` from that alignment, an `alignment_reason`, the existing paired-repair hashes, and original-audio evidence. A two-stage review result is checked if supplied, but is not required for a text-preserving timing repair with current accepted alignment. It preserves all words in each language, verifies that each new cue overlaps accepted word timing, and saves both before/after tracks. Reprepare the map and rerun affected reviews, alignment, and layout after batched edits. Save comprehensive episode and rendering checks for the final checkpoint. A forced aligner alone does not establish the words.

For the direct-agent path, start from Turkish-ready source. Run `python3 scripts/agent-translate.py batch-input WORKING.tr.srt CASE/agent-translation-progress.json 1 --batch-size 12`. Author JSON with `batch_number`, the returned `input_sha256`, identified `reviewer`, and `translations` containing every selected `cue_id` once with English `text`. Save it with `python3 scripts/agent-translate.py apply WORKING.tr.srt CASE/agent-translation-progress.json CASE/english-batch-0001.json`. For an authored set of any size, `agent-translate.py import SOURCE PROGRESS ROWS.json` accepts `{ "source_sha256": "<current Turkish hash>", "reviewer": "agent name", "translations": [{ "cue_id": 1, "text": "English line" }] }`. It rejects stale source hashes, duplicate IDs, and silent replacement of existing English. Export complete coverage with `agent-translate.py export SOURCE PROGRESS OUTPUT.en.srt`, then prepare the semantic map for contextual review. Use `layout-cues.py` for separate Turkish/English display SRTs with explicit source links and independent cue counts.

A late genuine source error reopens its affected interval. Repair it before finishing English; the existing rebase retains unaffected translations and invalidates the changed cue plus two neighbors. Legacy `defer_reason` rows and `export ... working.partial.en.srt --partial` remain available to inspect interrupted historical work, never as the normal source-ready progression or a release.

## 8. Check rendering and install

Keep alignment, layout, export, and rendering local. Generate English from the Turkish-ready source using the selected DeepSeek or direct-agent path, then review it contextually. Existing English needs the same source-referenced agent review. Reading-speed and cue-duration flags are presentation pressure, not permission to omit speech. Duration alone does not block installation; current alignment findings still require resolution.

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

A legitimate `many_source_cues_one_target` display split can use optional `--translation-decisions GROUPING.json`. Save current `source_sha256`, `target_sha256`, `semantic_manifest_sha256`, reviewer, and `findings` with each exact finding ID/fingerprint (`finding_sha256`), `disposition: independent_display_grouping`, and a specific reason checked against neighboring linked cues. The raw warnings remain visible; all other timing kinds still block, and current semantic/layout review remains required. This input cannot excuse missing meaning.

The command verifies video, subtitle and report hashes, cue structure, speech coverage, source and audio decisions, English timing, and current semantic review. It backs up both installed sidecars, verifies the backups, installs both candidates, checks installed hashes, and rolls back on failure. Open the video in IINA and check both languages at early, middle, late, and repaired intervals. Save observed player state and hashes. A playback finding reopens the affected interval; rerun comprehensive final checks before another installation.
