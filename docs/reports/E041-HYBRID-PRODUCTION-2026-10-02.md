# E041 hybrid production continuation — October 2, 2026

**Status: incomplete, awaiting the requested episode allowance.** The separate hybrid case has useful supported source corrections, but Turkish is not ready for translation and no English pair has been generated. This checkpoint records authorized preparation and saved-evidence work. Hosted recovery has not started.

The continuation follows [PROCESS.md](../../PROCESS.md). It reuses the existing 1,590-cue Whisper draft, supported repairs, original local observations and alignment. Initial transcription, recognition and separation were not repeated. The completed [local capability comparison](LOCAL-CAPABILITY-EXPANSION-2026-10-02.md), installed environments, model caches and playback sidecars remain preserved. Reference subtitles were not opened or included in production evidence.

## Work completed

- Created a private hybrid working case separate from the local-only production baseline and capability-test cases.
- Recorded nine named source decisions from saved evidence, including two supported word/spelling repairs and seven boundary trims from complete saved word alignments. Both occurrences of a supported repeated utterance were retained.
- Recompared all 152 saved Qwen windows against the working source without inference. The original cache settings were retained.
- Verified all 76 alignment windows were reusable when the case was copied. After the supported edits, 72 remain current; the four affected windows await the batch alignment checkpoint.
- Prepared and validated 36 bounded original-audio review clips. If all are needed, they require 36 uploads and 72 two-stage calls, covering 33 minutes 23.461 seconds of uploaded audio and 66 minutes 46.922 seconds processed across both stages. Preparation made no provider requests.

Saved recognition and agent text comparison support the narrow repairs; the agent did not claim to have heard the original audio. Alignment supplies timing evidence, not proof of supplied words. Prepared Gemini reviews use an independent audio observation before candidate comparison. Each future output still needs a source decision; no automatic acceptance is planned.

## Remaining source work

Sixteen original material hold groups remain unresolved, including the opening, masked singing, short replies, foreign-language dialogue, bank scene, names and wordplay, music transitions, overlapping police dialogue and closing fragments. Other saved coverage and seam questions are grouped with their surrounding scenes. Broadly corrupted scenes have bounded reconstruction clips with overlap.

Four inherited cue overlaps remain. Speech-coverage findings are preserved but are stale after timing changes; fresh coverage assessment is required at the substantive source checkpoint. A smaller active queue after those edits is not evidence of improved coverage. No source-ready checkpoint, bulk English, final layout, rendering, release or installation has been performed.

## Proposed consolidated E041 allowance

Approval is pending. The total ceiling is **US$5**, allocated as follows; subcaps sum to the ceiling.

| Provider and purpose | Subcap | Hard limits |
|---|---:|---|
| Gemini 3.8 Flash, targeted audio recovery and scene reconstruction | US$4 | 80 attempted model calls; 40 uploads; 40 minutes uploaded and 80 minutes processed, including repeats; clips at most 90 seconds; 8,192 output tokens per call; 1,500,000 prompt bytes |
| DeepSeek Flash, contextual English after Turkish readiness | US$1 | 60 attempted batches; at most four concurrent; 6,000-token input budget; 8,192 output tokens per call |

Failed attempts and pending reservations consume the applicable limits. Fixed provider allocations prevent combined spending from exceeding the episode ceiling. Reuse completed receipts before spending again; there are no automatic retries. The proposal covers neither a second full-episode transcript nor sidecar installation.

The proposal uses the checked [Google pricing](https://ai.google.dev/gemini-api/docs/pricing) and conservative peak [DeepSeek pricing](https://api-docs.deepseek.com/quick_start/pricing/). Recorded reservation rates are US$0.75 input/US$3.75 output per million Gemini tokens and US$0.30 input/US$1.20 output per million DeepSeek tokens. Actual usage and estimated charges will be reported separately from reservations and are not invoices.

## Continuation time, cost and checks

| Stage through this checkpoint | Observed result |
|---|---|
| Preparation and saved-source checking | 26 minutes 56 seconds wall time, 17:43:52–18:10:48 UTC; includes overlapping preparation and the pending-approval interval |
| Hosted Turkish recovery | Not started; zero model calls and uploads |
| English generation and review | Not started; Turkish incomplete |
| Local finalization | Not started |
| Additional hosted charge | US$0 |

This time belongs to the continuation only. Earlier transcription, local recovery, capability experiments and their timings are excluded. The preparatory interval is not an uninterrupted production-speed benchmark.

All 19 portable checks in README passed. Hash verification found no changes in 302 protected baseline/comparison files, including both installed sidecars. Those tests establish software behavior and preservation, not complete linguistic accuracy. The partial source remains unsuitable for a complete viewing release.

The private checkpoint is `checkpoint-before-hosted.json`, SHA-256 `70c5ca98b558536d96b9239e4352fabf32118d316f9050b4fe411c356996e4a3`. Media, subtitle text, clips, model observations, decisions and authorization records remain outside Git. Once the allowance is approved, continue scene decisions, batch Turkish edits/alignment, substantive readiness, concurrent DeepSeek drafting, contextual agent review and local finalization. Installation remains unauthorized.
