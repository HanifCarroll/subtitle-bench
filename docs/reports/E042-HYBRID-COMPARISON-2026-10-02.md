# E042 full hybrid production and reference comparison — October 2, 2026

The full creation trial and comparison are complete. The reference pair is preferable for viewing after correcting its roughly five-second offset from the local video. Generated English has specific meaning advantages, but the generated pair still has source mistakes, awkward phrasing and substantially more fast captions. It is a development result with release holds, not a qualified unseen-episode process.

## Design and production

The 85m52s video was the only production source. Both archived reference tracks were hash-verified by metadata but their contents stayed sealed until the generated pair was frozen at 22:56:02 UTC. Reference text was first opened at 22:56:50 UTC. Neither frozen track was subsequently repaired to match the reference.

| Stage | Elapsed | Recorded output |
|---|---:|---|
| Fresh local Whisper turbo | 7m26s | 18 clips, 1,956 initial Turkish cues |
| Turkish review, recovery, alignment and joins | 64m05s | Full source read; 172 independent Qwen windows; targeted original-audio Gemini work; all 17 joins reviewed |
| English and final checks | 26m48s | DeepSeek draft in 34.4s; full contextual agent review; display, semantic and render receipts |
| Production through freeze | 98m18s | 1,816 Turkish / 1,816 English cues |

Agent review changed wording in 221 unique English cues, covering meaning and style, and added 97 display-only speaker-turn line breaks. These are intervention counts, not proven error counts. A final application check caught 14 restaurant repairs lost under a reused private patch key; all 434 addressable authored repair rows subsequently matched the candidate. A later English pass caught and removed one accidentally added sentence. These failures and their repairs are part of the run.

Five dialogue passages retain partial uncertainty. The opening also carries a lyrics-unclear caption after mutually incompatible model observations; the reference labels music, and the exact sound classification remains unverified. No guessed opening lyrics were accepted.

## Comparison

Whole-file dialogue metrics exclude sound/speaker tags, formatting and credits. Word comparison normalizes punctuation and case while retaining Turkish letters. Reading density uses the same 25-characters-per-second screening threshold across the four tracks, not a universal reading standard.

| Measure | Generated TR | Reference TR | Generated EN | Reference EN |
|---|---:|---:|---:|---:|
| All cues | 1,816 | 1,615 | 1,816 | 1,253 |
| Normalized dialogue words | 9,390 | 9,021 | 13,471 | 11,350 |
| Median dialogue cue duration | 1.68s | 2.08s | 1.68s | 2.50s |
| Dialogue cues under 1s | 295 | 104 | 295 | 0 |
| Dialogue cues over 25 chars/s | 167 / 9.2% | 0 / 0% | 445 / 24.5% | 143 / 11.4% |

Turkish normalized word disagreement fell from 2,143 edits / 23.8% in fresh Whisper to 1,284 edits / 14.2% after production, a 40.1% reduction. This is reference disagreement, not measured accuracy: repetitions, colloquial forms and editorial compression contribute alongside recognition errors. English disagreement is 75.4%, which is not a translation-error measure because valid paraphrases use different words.

241 exact normalized Turkish cue matches of at least five words give a median start offset of −4.86s, with the middle 80% from −5.02s to −4.56s. Caption boundaries affect these anchors. Contextual review used a provisional −5.36s virtual offset with neighboring dialogue visible; archive files were not retimed. Matching passages extend across the episode, without an obvious large missing section, but do not establish full word coverage.

The agent compared all four tracks in five three-minute windows selected before production, totaling 15 minutes / 17.5% of the video: 298 generated cues, 267 Turkish-reference cues and 213 English-reference cues. Targeted comparison added unclear passages and material meaning differences. Three further neutral original-audio observations were run after freeze. This is a producer self-evaluation with sampled direct comparison, not a second full acoustic review or independent qualification.

The generated English better preserves several employment, financing, family-relation and humor meanings. The reference English sometimes adds an unsupported character description or selects the wrong meaning of a business term. However, two source mistakes change direct address to an elder into reported speech, and a contextual verb sense is translated incorrectly. Other generated phrasing remains less fluent. The reference generally wins readability and lyric phrasing; its Turkish also supplies more sound and speaker information.

Extra repetitions and forms of address can help Turkish study, while also increasing reading work. Generated English has about 19% more dialogue words and 45% more cues than the reference. Sharing the small Turkish cue boundaries contributes to fragmented, fast English. Sampled text fitting on screen does not establish comfortable reading speed.

## Cost accounting

| Production component | Recorded usage | Estimate / equivalent |
|---|---|---:|
| Gemini recovery | 246 requests / 123 uploads; 76m26s raw clips including repeats, 152m51s processed | US$2.255946 |
| DeepSeek English | 28 requests; reported cache hits/misses, all off-peak | US$0.031128 |
| External provider subtotal | 274 requests | US$2.287074 |
| Codex agent, Standard API equivalent | 231 usage receipts | US$8.368002 |
| Production model-cost equivalent | 98.3 elapsed minutes | US$10.655076 ≈ US$10.66 |

The agent estimate uses 1,429,459 uncached input tokens, 34,964,736 cached input tokens and 201,261 output tokens. Reasoning is included in output. The largest production request had 247,477 input tokens, below the 272K long-context pricing threshold. Recorded cumulative usage is sampled immediately before production and 0.410s after freeze. Cached tokens include repeated conversation context, not distinct subtitle words.

All production Gemini attempts, including malformed responses, retain usage; all 123 upload receipts confirm deletion. Post-freeze evaluation added six requests / three uploads, 74s raw / 148s processed, and US$0.051566; all three files were deleted.

The complete trial through the 2026-10-02T23:29:14.013Z usage checkpoint is US$13.24 at Standard model rates, including preparation and comparison/reporting. Assessment took 26.0 minutes after freeze; subsequent accounting and documentation add overhead. Final delivery after that checkpoint is excluded.

Prices were checked against [Google](https://ai.google.dev/gemini-api/docs/pricing), [DeepSeek](https://api-docs.deepseek.com/quick_start/pricing/) and [GPT-6.1 Sol](https://developers.openai.com/api/docs/models/gpt-6.1-sol). These are usage-based estimates and a Standard API equivalent, not reconciled invoices or a verified Codex subscription charge. Actual Codex tier/allocation, electricity and hardware costs are unpriced. Bounded episode approval remains the default; this run had explicit user approval without aggregate limits, recorded privately through the [workbench exception](../guides/WORKBENCH.md).

## Guard state and limits

The production dry release was held by two truncated Qwen scan windows even though targeted original-audio evidence and current adjudications covered those intervals. The gate was not weakened for the trial. After comparison, two supported source errors and three unresolved restaurant/payment conflicts were registered in the normal evidence-disagreement queue. The unchanged source now has five open material questions, and its earlier Turkish-ready checkpoint is rejected. Historical freeze receipts remain intact.

Nineteen portable checks and 28 sampled bilingual libass renders passed. These establish application/structural/render behavior, not complete linguistic correctness. The agent did not hear audio directly: acoustic evidence comes from hashed original-video clips and saved recognizer observations. Fresh neutral observations use the same provider involved in production and cannot establish independent evaluation. Native IINA playback and a full human watch-through remain unverified. Nothing was installed; both existing sidecars, both references and the frozen pair remain hash-unchanged.

The run shows useful improvement over fresh Whisper and specific English meaning wins. Its remaining limitations are trustworthy source adjudication, contextual English review and reading time. Agent work accounts for most of the Standard model-cost equivalent; the initial English draft is inexpensive.

## Private evidence provenance

This is a publication edition of the private `episode-042-hybrid-2026-10-02/comparison/REPORT.md`, SHA-256 `6f900c59af4c11e680a4e43e8c9ac79250599b00648580c18903714c663c1133`. Media, commercial references, subtitle/model excerpts, clips, prompts, provider responses, frame observations, cases, decisions and token ledgers remain outside Git. Reference archive IDs: Turkish 9951024, English 8661760. Frozen track SHA-256 values:

- Turkish: `fef822712872463647291054b9feee118b16c88319fd5d415a491758aaa7a6b2`
- English: `91d9235e7ff338fb9094ff2f8adeaf566890c357f7de4428e6d3e21d80efbeff`

Private cost and preservation receipts retain exact formulas, stage boundaries and file hashes. This report does not authorize another episode, provider experiment or installation.
