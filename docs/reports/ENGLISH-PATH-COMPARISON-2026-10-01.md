# English-path comparison: completed development section

Recorded 2026-10-01. Use **DeepSeek Flash drafting followed by mandatory agent review and correction** provisionally. Both corrected paths met the same practical standard on this section; A reached reviewed English sooner in this observed run. Direct agent translation remains supported when provider calls are unapproved or unavailable. The current production sequence is [PROCESS.md](../../PROCESS.md).

| Measure | A: DeepSeek Flash + agent review | B: Direct agent + contextual check |
|---|---:|---:|
| Draft generation | 5.828 seconds | 209.289 seconds |
| Contextual review/correction | 318.375 seconds | 411.093 seconds |
| Total to reviewed English | **324.203 seconds (5m24s)** | 620.382 seconds (10m20s) |
| Cues with substantive errors found/repaired | 12 / 12 | 0 / 0 found in producer self-review |
| Minor wording corrections | 22 | 1 |
| Extra provider requests | 3 text-only requests | 0 |
| Provider usage | 6,274 input + 3,746 output = 10,020 tokens | Codex session usage unavailable |
| Provider cost estimate | US$0.0063774 at configured peak rates; US$0.0031887 off-peak | No extra provider call; Codex session cost unavailable |

Costs use actual returned usage and the [DeepSeek prices](https://api-docs.deepseek.com/quick_start/pricing/) recorded for the experiment; they are not billing receipts. The conservative peak estimate was below the approved US$0.25 cap. Observed request times were off-peak. The provider reported `deepseek-flash`.

Stage times include tool use, review bookkeeping and visual-context checks. B also includes conversation context restoration. They are not controlled uninterrupted-writing measurements. The shared post-draft reference check and final layout/render stages were recorded separately and excluded from both totals. One section, one run and the same reviewing agent support a provisional operational choice, not a general speed guarantee or independent accuracy qualification.

## Source and independence

- Input: the existing independently generated E023 overlapping five-minute Gemini Turkish draft, original cues 47–233 (187 units), selected time 05:13.423–15:43.360. The first cue was retimed to 05:13.200.
- Frozen Turkish SHA-256: `50902ae567ecaa3d4dcc3db87802934e3a80940a5017172542571d36f4b53e88`. Both paths used identical Turkish and terminology. Turkish did not change during English review.
- Only this 10.5-minute section was settled: 14 text repairs and 34 batched speech-boundary repairs, using saved independent recognition, four focused local recognition clips and 11 Turkish-only alignment windows. Full E023 remains incomplete.
- Original-audio hearing is not claimed. The source checkpoint records agent assessment from recognition, forced alignment and timestamped frames; this does not independently establish every spoken word.
- Independent A and B drafts were saved before the English reference was opened. A private freeze ledger binds their hashes and preserves the earlier pending state.

## Review and reference comparison

A's raw draft failed on actors, referents, idioms and concrete meaning. It reversed the actor relationship at original cue 158, invented a person at cue 96, changed the meaning of a number question at cue 129, confused reading with school attendance at cue 198, and assigned an occupational title to a polite street address at cue 222. All 12 affected cues were repaired; 22 more received minor corrections. Initial findings, authored corrections and final judgments were retained separately. Provider origin was never relabeled as agent authorship.

Neither reviewed path had an identified remaining material English error against the frozen Turkish and contextual reference check. Equivalent translations were accepted. The English reference itself altered causative meaning, lost a water-delivery callback, changed ownership and age contrasts, and omitted a resumed story fragment. Those defects were not copied. Private reference assessments retain the supported alternatives. The 4.458-second reference shift aids retrieval; it is not authority for words or final timing.

## Export, rendering and integration

Both candidates preserve 187 Turkish source units with explicit links and export **169 English display cues** using identical grouping decisions. English-only corrections survive re-export in the existing checkpoint without a Turkish rebase. Current hashes, exact provider coverage, retained provenance and the spending cap were checked on A's real run.

Sampled libass rendering passed **12 A frames and 10 B frames**, including early, middle, late and repair times. This is not native IINA playback or a full watch-through. Installed sidecars were preserved.

The [reusable entry prompt](../guides/DEVELOPMENT-AGENT-PROMPT.md) supports selectable `whisper-turbo` and `gemini-five-minute` profiles. The integration promotes the tested Gemini chunk runner, permits Turkish-only alignment/readiness, extends the existing DeepSeek translator with bounded contextual concurrency/resume, and retains reviewed corrections and provider provenance in the existing English checkpoint. Earlier instructions remain in [history](../../history/README.md).

All **16 portable checks**, compilation and Git whitespace checks passed at comparison time. Coverage includes input hashes, exact unit coverage, interrupted concurrent resume, provider drafts remaining unapproved, and corrections surviving re-export. Synthetic tests do not establish language accuracy. The promoted Gemini route received offline planning/parsing/incomplete-response/deletion checks; no new full transcription, recognizer survey, held-out qualification or installation was performed.

## Evidence availability

This is a publication edition of the private `english-path-comparison-2026-10-01/COMPARISON.md`, SHA-256 `87cfb2c52e72709cb85693b71548760ad1b373cfe6d7426e5735f6fd95cabdd9`. Raw API responses, subtitle tracks, terminology, cases, reference assessments, freeze ledgers and rendered frames remain outside Git. The hash identifies the source report; it does not make its private evidence available to a repository reader.
