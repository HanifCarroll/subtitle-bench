# Subtitle Bench iteration: 2026-09-28

This report separates executable checks, model observations, and a listening receipt. Private evidence is under `/Users/hanifcarroll/Movies/Leyla ile Mecnun/Workflow/pilots/subtitle-bench-next-2026-09-28/` (called `PILOT` below). The Episode 39 working pair is under `/Users/hanifcarroll/Movies/Leyla ile Mecnun/Workflow/pilots/source-review/039/whole-file-repair/`. Episode media and complete subtitle tracks are not in this repository.

## Baseline and implemented changes

The initial Episode 39 long hold and context-sensitive translation reports described real failures, but the installed Episode 39 pair had already been repaired before this iteration. The old “Ayyy!” cue ran from 41:18.790 to 42:01.260 (42.47 seconds). The current working pair gives it 3.97 seconds and has 11 Turkish and 11 English cues, including subsequent dialogue, within the old interval. The installed English track also contains a later independent meaning review; its current SHA-256 is `1083e4745a9c8a3609ea6bb1cce0f4e34c82ad069d3f4e61022e8e19e3a1c467`. The current working pair has a further cue 757 correction and is **not installed**.

Confirmed workbench gaps were fixed with offline regressions:

| Gap | Current behavior |
| --- | --- |
| Long non-gap issue gave only a short excerpt | `review` and `bundle` split every disputed interval into overlapping clips covering the complete interval plus context. |
| Evidence existence could close a larger issue | Decisions check original-video interval coverage, clip hashes, and a saved review result. |
| Partial ASR scan could satisfy release | Release requires contiguous, successful full-video windows through the final tail; empty, failed, or truncated windows are not accepted as coverage. |
| Audio comparison missed short replies, small changes, and subtitle additions | Both recognition-to-subtitle and subtitle-to-recognition directions now flag bounded, reviewable disagreements. The calibration reduced an unusable 153-of-164-window draft to 37 questions; this is fewer flags, **not a measured accuracy gain**. |
| English audit accepted slight overlap as counterpart | Meaningful overlap, many-source-to-one-target, long English cues, and configurable reading-speed flags now surface. Speed never deletes speech. |
| No cue lead/tail check from corrected Turkish | `layout-audit.py` compares both display languages against current, video-bound Turkish word timing. Flags are diagnostic and never shorten a cue automatically. |
| Equal cue-count assumptions in generation and second opinion | An explicit utterance map allows source-linked JSON translation drafts and Google comparisons across independent English cue boundaries. `layout-cues.py` renders separate SRT drafts from linked source and English units. |
| Semantic review was optional | Release now requires a current source-referenced assessment for every utterance, plus resolution of material and uncertain findings. Missing or malformed model fields remain uncertain. |
| Playback was an instruction only | `playback-check.py` renders real video frames with libass for both tracks and detects subtitle pixels at early, middle, late, and chosen repair points. It does not establish IINA playback. |

The hash-bound utterance map is a provisional bootstrap from existing cues. It records stable source IDs, separate English translation IDs and display cue IDs, explicit source links, and alignment status. A Turkish content change invalidates affected alignment and English assessment; unchanged audio transcripts remain cached. A layout-only change does not require retranscription. These checks make uncertainty visible; they do not turn automated recognition into proof of every word.

## Real software trials

All three shared provider-comparison clips came from original media: Episode 39 at 41:18–42:01 (43 seconds), Episode 39 at 22:44–22:52 (8 seconds), and Episode 38 at 15:28–15:45 (17 seconds). Clip/video hashes and offsets are in `PILOT/e39-ayyy-bundle.json`, `e39-reply-bundle.json`, and `e38-sugar-bundle.json`. The user authorized at most 90 seconds of clips per provider and US$5 combined for Gemini and ElevenLabs. Gemini received 68 unique uploaded seconds and processed each clip twice for 136 audio-input seconds across its six calls; ElevenLabs processed 68 seconds once. Charges were not visible, and no additional provider call was made after these trials.

| Trial | Actual result | Decision |
| --- | --- | --- |
| WhisperX 3.8.6 Turkish aligner | On an ordinary Episode 39 scene, short reply, and long-hold repair: 2/21, 4/15, and 11/53 cues/words respectively; no unaligned words. Alignment took 0.858, 0.896, and 2.728 seconds after model load. Full Episode 39: 78 one-minute sections, 1,437 units; 1,412 aligned, 22 suspicious, 3 failed; 378.48 seconds total alignment time. Changing cue 757 left 77/78 sections reusable. | **Adopt** after source correction as timing evidence; investigate suspicious words. Aligned words may still be wrong. |
| Gemini audio understanding (`gemini-3.8-flash`) | Three unique clips totaling 68 seconds were uploaded; six model calls reused them for independent observation and then subtitle/transcript comparison (136 audio-input seconds across calls). Raw prompts, responses, hashes, parsed findings, and successful remote-file deletion are in `PILOT/gemini-two-stage/`. Both stages supported a cue 757 phrase; a backed-up bilingual candidate repair was applied to the working pair. It disagreed with local Whisper on cue 749 and cue 758, and raised a questionable short-reply correction. | **Adopt only as targeted escalation**, not automatic adjudication. Provider bill was not independently visible; do not claim zero cost. |
| Local GEMBA-MQM-style review | Qwen3.5 27B flagged the actual Episode 38 Google endearment error, DeepSeek blood-sugar error, and old Episode 39 face-idiom error while leaving two clean controls alone. One proposed blood-sugar repair was wrong. A 4B comparison flagged all three bad candidates but falsely flagged both clean controls and proposed wrong repairs. Case files: `PILOT/mqm/` and `PILOT/mqm-4b/`. | **Use 27B findings as review questions**; reject 4B as final adjudicator. No numeric score is a release decision. |
| ElevenLabs Scribe v2 | Three approved live calls processed 68 seconds of Turkish audio with word timestamps, diarization, audio-event tags, and `no_verbatim=false`. Receipts are in `PILOT/scribe-v2/`; `PILOT/scribe-comparison.json` records the case comparison. The [transcript deletion API](https://elevenlabs.io/docs/api-reference/speech-to-text/delete) returned success for all three stored provider transcripts after the local responses were saved. Scribe recovered the short `İyi` / `Bir şeyim yok` replies and the later `Şekerim çok düştü benim`. On Episode 39 cue 757 it recognized `duygusuzluk yapma`, conflicting with Gemini and the current working `duygu sömürüsü yapma` candidate. It also disagreed with Gemini at cues 749 and 758. No actual charge was visible. | **Adopt as independent targeted recognition evidence**, never automatic repair or timing authority. The three material disagreements are now pending in the Episode 39 source queue. |
| VideoLingo commit `11ca23e` | Config and code inspected before running. An isolated local Qwen ASR `transcribe_window` stage was run on the same three clips (`PILOT/videolingo-local-stage.json`). The long-hold clip degenerated on three recognition attempts. The short reply completed with noisy words; Episode 38 completed but misrecognized the blood-sugar word. The full translation/segmentation/timing pipeline was **not** run. [Qwen's language table](https://github.com/QwenLM/Qwen3-ASR) supports Turkish ASR but does not list Turkish for Qwen3 ForcedAligner, VideoLingo's default aligner. | **Reject default full pipeline for Turkish** on current evidence; borrow no stage yet. Local stage failure is not a full-pipeline quality score. |
| Subtitle Edit 5.2 | Existing copied-media pilot already verified inspection, cue editing, and warning export; repeated here only by reviewing that receipt. Paired retiming dirtied a reference in memory, and warning output was noisy. | **Optional editor**, not a speech/meaning oracle. |
| ffsubsync | No cut-matched reference with a demonstrated global offset or drift was present in Episode 39; the tool is not installed on this host. | **Defer** until such a reference exists. It cannot repair a single held cue or mistranslation. |
| COMET / COMETKiwi, stable-ts | No model/version/resource combination was validated for a useful Turkish-to-English independent gate in this pilot. stable-ts was archived in May 2026. | **Defer** estimators; do not add stable-ts as a new core dependency. |

VideoLingo is Apache-2.0 and was inspected for focused ideas; no source code was copied into Subtitle Bench. Its [technical overview](https://docs.videolingo.io/en-US/docs/tech) and [default configuration](https://github.com/Huanshere/VideoLingo/blob/main/config.yaml) describe the pipeline and provider settings. WhisperX is BSD-2-Clause; no implementation was copied. [ElevenLabs pricing](https://elevenlabs.io/pricing/api) is tier and date dependent, so the user cap is enforced by clip volume and call count rather than a claimed observed charge.

## Case results and attempted Episode 39 completion

`PILOT/regression-cases.json` contains 25 real passages: nine established **text or structural** reference cases and 16 provisional audio/model questions. It explicitly does not claim 25 trusted word-level ground truths. The established set includes the old long hold, following dialogue, the actual Episode 38 “şekerim” endearment versus blood-sugar contexts, and the repaired face idiom. Synthetic regressions additionally exercise a missing three-word reply, negation, unsupported addition, one English cue for three source utterances, a partial audio scan, incomplete clip coverage, and stale review after source edits.

The Episode 39 working pair currently has 1,437 cues per language. One targeted cue 757 repair is backed up under the source case's `decisions/20260928T214122565659/`. Its source SHA-256 is `d52b76b44fdf93e80313335538e0da924acb4d995fd5c9050a439ff38fcf22de` and English SHA-256 is `d0de1ec4a25143f54d6be16953f7e60aa975694bdcbf2d0c52c9bc104e7cdb12`. The repair remains candidate evidence. Scribe now contradicts its material phrase; no model consensus or listening annotation resolves it. `REVIEW-CASE/evidence-disagreements.json` carries this and the two neighboring disagreements as hash-bound queue inputs.

The full cached Qwen episode recheck used 164 thirty-second windows and surfaced 37 questions: 18 repeated ASR outputs, 11 possible missing or wrong subtitle spans, five possible unsupported subtitle spans, and three empty ASR outputs. VAD coverage found 11 uncovered speech intervals and 23 possible cues without speech; these are flags, not verified errors. A new translation audit found nine English cues longer than eight seconds and 222 presentation-speed flags. `PILOT/e39-layout-audit-verified.json` checked 1,437 video-bound alignment units and raised 750 source/English timing and density questions. Two long cues have roughly 5.9- and 4.8-second lead-ins suggested by alignment; the “Ayyy!” vocalization was also falsely suggested to end early by single-word alignment, so none was cut automatically. The local 27B semantic run completed only 24/1,437 source units; three findings are uncertain and need agent adjudication. Full review at the observed pace is hours of additional work.

The latest exact release dry run is `PILOT/e39-release-check-after-scribe.json`. It blocks installation for: 1,413 unreviewed English meaning units; three uncertain meanings; audio decisions that predate the 37-question comparison; opening-interval evidence that does not cover the disputed span or include a review result; the three Scribe/Gemini source disagreements; and nine English timing questions. A partial or stale report cannot override these. The candidate is **not installed**. The installed Turkish and English sidecars remain at hashes `823493e7bdfe7915a46f67a697e663414cc3c5e8c1cc678c23e01694458d8f1e` and `1083e4745a9c8a3609ea6bb1cce0f4e34c82ad069d3f4e61022e8e19e3a1c467` respectively. Their current IINA reload state was not observed.

`PILOT/e39-render-current/playback-check.json` binds the candidate hashes above and reports 16/16 successful libass subtitle-frame checks across early/middle/late samples and five targeted times, including the long-hold repair and cue 757. The PNGs visibly show rendered Turkish and English separately. This is a renderer check, **not** an IINA native playback check.

Episode 38 was not used to tune the Episode 39 thresholds. Its full local `episode-check` covered 5,141.661 seconds in 172 audio windows (160 complete, nine questionable repeated outputs, three empty); no video interval was skipped. It raised 24 audio questions: nine repeated, nine possible missing/wrong, three possible additions, and three empty outputs. Its source queue has 73 questions (31 subtitle gaps, 41 VAD gaps, one possible subtitle without speech), including six severe issues. The English structural audit checked 1,606 cues per language with zero structural flags and 145 presentation-speed flags. Its real 17-second sugar scene also received the Gemini, MQM, VideoLingo, and Scribe trials. `PILOT/e38-full-check/release-check.json` blocks installation because semantic review and audio decisions are absent and source questions remain; no Episode 38 sidecar was changed. This is a complete **scan**, not a completed episode repair.

## Reproduce the checks

Run the offline suite in [README.md](README.md). With the private case paths above, the main real-media steps were:

```sh
python3 scripts/semantic-review.py check PILOT/e39-utterances.json PILOT/e39-semantic-reviews \
  --glossary PILOT/evidence-glossary.json
python3 scripts/align-turkish.py EP39.webm PILOT/e39-utterances.json PILOT/e39-alignment --dry-run
python3 scripts/layout-audit.py EP39.webm PILOT/e39-utterances.json \
  PILOT/e39-alignment PILOT/e39-layout-audit-verified.json
python3 scripts/subtitle-workbench.py translation-audit WORKING.tr.srt WORKING.en.srt \
  --output PILOT/e39-translation-audit.json
python3 scripts/playback-check.py EP39.webm WORKING.tr.srt WORKING.en.srt \
  PILOT/e39-render-current --at-ms 2479500 --at-ms 2483500 \
  --at-ms 2513000 --at-ms 3562500 --at-ms 1367000
python3 scripts/elevenlabs-scribe-trial.py PILOT/scribe-trial-plan.json PILOT/scribe-v2 \
  --key-file /Users/hanifcarroll/.config/subtitle-workflow/.env
```

`PILOT`, `EP39.webm`, and `WORKING.*.srt` stand for the absolute private paths named above; they are labels, not shell variables. A new rendering run needs a new output directory. Release uses the complete `release` command in [WORKBENCH.md](WORKBENCH.md) and omits `--apply` for a dry run.
