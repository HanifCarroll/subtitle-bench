# First E023 production-strategy comparison: incomplete

Recorded 2026-10-01. **All three branches stopped with incomplete Turkish and no English.** Scribe was the provisional primary recommendation at this point; later [chunking](E023-CHUNKING-2026-10-01.md), [downstream results](E023-DOWNSTREAM-COMPARISON-2026-10-01.md) and [PROCESS.md](../../PROCESS.md) supersede that recommendation. This was development, not qualification or release.

Video duration was 82m29.621s, SHA-256 `33557ad80faf26400b22b338605288a1810748240a98964646afe5442e01b425`. Independent outputs were frozen before the references were opened. The local turbo model file SHA-256 was `1fc70f774d38eb169993ac391eea357ef47c88757ef72ee5943879b7e8e2bc69`; provider model revisions were not recorded.

## Results at freeze

| Measure | Whisper turbo | Gemini single full-audio request | Scribe v2 single upload |
|---|---|---|---|
| Raw result | 1,814 cues, full duration | 349 parsed segments; stops at 27:16 | 2,242 cues, full duration |
| Primary elapsed | 374.4s, including two technical restarts | 253.7s failed WAV + 227.6s MP3 retry | 87.2s |
| Recovery | Five loop repairs; eight escalated scenes | No recovery of missing ~55 minutes | 17 patch operations, 14 scene groups, 20 escalations |
| Reference word disagreement | 28.8% raw → 21.0% repaired | 14.0% only on returned portion | 14.8% → 14.5% |
| Timing findings | Eight overlaps; 14 cues >8s; three ≤100ms | Phrase-start residual p90 3.62s on partial text | No overlaps or cues >8s; 25 cues ≤100ms |
| Completion | Partial source; no final alignment or English | Partial source; no English | Partial source; no English |

Disagreement is a window-selection signal, not linguistic accuracy. The Gemini result omitted most of the episode and cannot be ranked as a full transcript.

## Recovery work and costs

| Measure | Whisper branch | Gemini branch | Scribe branch |
|---|---:|---:|---:|
| Escalated scenes | 8 | 0 | 20 |
| Unique targeted audio seconds | 484.6 | 0 | 610 |
| Paid attempts | 20 targeted | 2 full attempts | 31 targeted, including three pre-upload failures |
| Processed / reserved seconds | 659.6 processed | 9,899.2 processed | 873 reserved |
| Local processed audio seconds | 604.6 | 0 | 385 |
| Provider elapsed | 92.7s targeted | 481.3s full attempts | 380.1s including primary |
| Known-successful cost estimate | US$0.045 targeted | US$0.339 successful retry | US$0.406 including primary |

Known-successful estimates totaled about US$0.790 against a conservative US$2.011 reservation and US$5 cap. Failed Gemini billing was unknown; no invoice was available. Four targeted Scribe HTTP-404 deletions were unverified. Gemini and Scribe primary artifacts reported deletion; three pre-upload failures created no artifact.

Branch calendar elapsed was about 78m, 14.3m and 51.1m, overlapping each other rather than measuring active labor. Checker/agent labor was not separately instrumented. Interventions included two Whisper zero-duration normalizations and a patch helper, Gemini transport/parser fixes, and three Scribe pre-upload failures caused by the wrong Python environment. No user cue wording was supplied. Whisper stopped after eight escalations with 12 of the earlier 20-scene allowance unused; Scribe exhausted it.

## Postfreeze review and limits

The Turkish reference was normalized from CP1254 after freeze. Its offset was 4.458s from 3,452 anchors, with ten-minute bins around 4.43–4.50s; English used the same shift. References were evidence rather than authority. Dialogue near 25 minutes may reflect a cut mismatch; this was not verified. The English reference's final question appears to assign the wrong actor.

Opening hallucination and several negation/idiom errors were repaired, but music/action loops, overlapping fairy-tale dialogue, names, shouts, nicknames and referents remained unresolved. Residual Scribe questions included roughly 9:01, 18:11, 43:38 and 67:01; Whisper retained questions across 3–17 minutes and around 43 and 66 minutes. A provisional reading near 81:14 was not independently established by listening.

The observed Scribe advantage combined faster primary output, native timestamps and lower reference disagreement. It did not demonstrate a settled source, English, full rendering, native playback or autonomous end-to-end completion. Subsequent reports changed the practical recommendation; this report preserves the earlier checkpoint without claiming a winner qualified for production.

## Evidence availability

Publication edition of private `production-strategy-023-2026-10-01/coordinator/postfreeze-assessment.md`, SHA-256 `bb0ab82013f8ec6d0b64b22d14af4d887bc7f1dd1b0b6b1a5ceb9bcae68c1890`. Media, reference tracks, raw/model transcripts, repair records and provider receipts remain outside Git.
