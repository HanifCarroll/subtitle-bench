# E023 downstream comparison: incomplete development result

Recorded 2026-10-01. **None of the three branches settled Turkish before English production.** Each repaired selected scenes, froze an incomplete source checkpoint, and translated much of the remaining draft. A frozen snapshot is preserved evidence, not accepted source. No branch was installed or qualified.

The branches used the same 82m29.621s video, identical producer instructions, direct agent translation, and separate raw drafts. Video SHA-256: `33557ad80faf26400b22b338605288a1810748240a98964646afe5442e01b425`. All six SRTs and manifests were frozen read-only at 14:27:19 UTC before reference access. Producers received neither reference contents nor other branches' transcripts. Review intervals were declared before access. References were aligned by 4.458 seconds using 3,452 unique five-token anchors, with no material drift detected; they contain omissions and translation defects.

## Bounded partial production

| Measure | Whisper turbo, isolated 300s | Gemini 3.8 Flash, five-minute chunks | Scribe v2, saved single upload |
|---|---:|---:|---:|
| Raw source cues | 1,841 | 1,291 | 2,242 |
| Targeted source scenes | 20 | 20 | 20 |
| Logged repairs | 22 entries | 7 scenes; 20 duplicates removed | 10 scenes |
| Frozen source cues | 1,814 | 1,271 | 2,228 |
| Targeted local calls | 52 | 23 | 29 |
| Unique / processed local audio seconds | 1,141 / 1,773 | 627 / 689 | 575 / 651 |
| Turkish pass elapsed | 21m58s | 14m07s | 15m35s |
| English cues translated / deferred | 1,694 / 120 | 1,261 / 10 | 2,161 / 67 |
| Deferred temporal groups | 82 | 8 | 47 |
| Deferred cue display seconds | 265.14 | 26.029 | 94.862 |
| English imports | 19 | 13 | 25 |
| English, layout and QA elapsed | 20m49s | 17m01s | 33m18s |
| Reused primary + source + English stage sum | ~49m55s | ~34m42s | ~50m20s |
| Primary provider cost estimate | US$0 | US$0.436783 | US$0.302476 |

Primary elapsed was 7m09s, 3m34s and 1m27s respectively. These primary runs were reused, not repeated. Branches ran concurrently; summed stage times are not campaign calendar time. English time includes review, layout and export. No paid downstream/recovery call occurred. Estimates use the recorded [Gemini rates](https://ai.google.dev/gemini-api/docs/pricing) and [Scribe API rates](https://elevenlabs.io/pricing/api), without invoices.

Gemini's 17 complete primary requests used 129,083 input, 47,146 output and 43,513 thought tokens; all 17 files were deleted. Scribe's one primary transcript reported deletion; token usage was unavailable. Whisper used 17 local processes. Post-review Turkish reference word disagreement was approximately 20.0%, 14.5% and 14.6%; **these are not accuracy percentages**.

## Postfreeze findings

The coordinator compared immutable outputs, references, scene records and context without independent audio listening. Exact-word judgments remain provisional.

| Fixed scene | Finding |
|---|---|
| Opening, 1:48–2:30 | Whisper's music-loop hallucination was repaired. All cover first dialogue; an earlier claimed Gemini opening omission is not established. Scribe appears to lose negation in an eating exchange, inherited by English. |
| Phone negotiation, 12m | Scribe truncates a threat's consequence. Whisper's Turkish conditional is malformed although English reconstructs the likely sense; fluent English does not repair Turkish. |
| Overlapping fairy-tale dialogue, 16m | All garble or miss speech. Gemini translates a corrupted source confidently; Whisper omits a thought; Scribe defers it. No branch wins this unresolved scene. |
| Drumming, 26m | All preserve a spoken beat omitted by the English reference. Scribe adds an English detail unsupported by its Turkish. |
| Sofa bed and safe, 42m | Whisper loses a key statement and English omits it. Gemini/Scribe preserve it. The reference's English changes a spatial relationship. |
| Kidnapping call, 55m | Gemini retains two nested repeated cues across roughly 55:00–55:10: a confirmed source/export/display defect. A verb remains suspect in all candidates and needs audio adjudication. |
| Fight gag, 64m | Scribe best preserves the move name and short reply; Whisper loses the name and Gemini misreads the reply. This is a scene result, not whole-episode accuracy. |
| Mask exchange, 71m | All convey the main dialogue with acceptable natural equivalents. |
| Final exchange, 81:13–81:19 | Whisper repeats the question about 20 and 8 seconds early and has no English line. Gemini/Scribe preserve the main exchange. The English reference appears to change its actor. Remaining credits/music are not an established speech omission. |

Source defects dominated the sampled English defects. No episode-wide linguistic accuracy rate is supported.

## Timing and operational limits

All six SRTs parse and match manifests. Sample overlays showed visible subtitles without clipping: Whisper four Turkish/English pairs, Gemini 18 samples, Scribe seven final frames. No full audio alignment or native IINA playback was performed.

Whisper finished sequentially but retained 25 translated cues shorter than 300ms and 283 above 25 characters/second. Gemini retained 15 large source overlaps and 60 fast English cues, including duplicate phone-scene text. Scribe retained 645 English cues above 25 characters/second, 90 above 40, and five below 100ms after display adjustment. Native word timestamps did not ensure readable subtitles.

The user's Turkish ceiling was 30 minutes per branch. A coordinator-added 20-scene, 1,200-unique-second, 2,400-processed-second allowance stopped all source passes before that ceiling. This did not settle unreviewed ordinary dialogue. English then proceeded over incomplete Turkish; selected deferrals undercount the unfinished source work.

Coordination included five shared clarifications, a Whisper policy reminder, and a Scribe English resumption after a premature stop. No cue wording was supplied. Scribe needed a branch-specific display helper. Manifest creation to freeze took 51m41s, overlapping producer work; bookkeeping labor was not separately measured.

The Gemini adapter now rejects historical HTTP-success/local-parse results whose provider status is incomplete. The old receipt was preserved and two focused tests passed. This correction does not establish full-request completion.

## Decision

Gemini led this **bounded partial checkpoint**: fewest deferred English cues, shortest stage sum and fewer repairs, at a primary estimate below US$0.44. Known duplicates, dense timing and unreviewed Turkish prevent choosing it as a validated production default. Scribe remained plausible for targeted checking, but that cost-benefit was not tested. No full dual-transcript policy is justified.

The central failure was advancing from incomplete Turkish to English. [The current process](../../PROCESS.md) now requires substantive source work and a source-ready checkpoint first. The later [small English-path comparison](ENGLISH-PATH-COMPARISON-2026-10-01.md) tests translation on a settled section; it does not finish E023. No additional episode, provider call, tuning run or installation followed this comparison automatically.

## Evidence availability

Publication edition of private `downstream-023-2026-10-01/coordinator/result.md`, SHA-256 `0234795a3c05a51a175dc8af5446f471d25f09f24acbcf02e7729eac9694d05c`. Raw subtitle/model text, references, manifests, scene records, rendered frames and provider receipts remain outside Git.
