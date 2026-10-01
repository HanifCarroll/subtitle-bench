# Turkish ASR strategy screen: six E015 excerpts

Recorded 2026-09-30. Scribe v2 and Gemini 3.8 Flash were shortlisted for further development; **no full-episode winner or accuracy qualification was established**. Subsequent [E023 reports](E023-PRODUCTION-STRATEGY-2026-10-01.md) and [PROCESS.md](../../PROCESS.md) contain the later decisions.

## Fixed sample and comparison

Six frozen E015 excerpts total 864.979 seconds (14m24.979s): opening music 154.979s, ordinary dialogue 150s, phone negotiation 150s, water-delivery scene 130s, wedding 150s and late dialogue 130s. Cloud prompts did not contain reference or candidate wording. All 18 cloud responses completed before comparison. The community Turkish reference had an approximately 4.86-second shift and slight drift.

The following values are normalized reference word disagreement. They mix actual recognition errors, reference omissions, event captions and alignment differences. **They are not accuracy percentages or independently annotated WER.** Opening music also makes aggregate scores misleading.

| Candidate | Music | Ordinary | Phone | Delivery | Wedding | Late | Five dialogue clips | All six | Elapsed seconds |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Whisper large-v3 | 1.278 | .203 | .245 | .292 | .135 | .205 | .210 | .224 | 157.9 |
| large-v3 reset | .889 | .210 | .204 | .287 | .138 | .221 | .208 | .217 | 140.9 |
| large-v3 VAD | .833 | .207 | .155 | .287 | .129 | .218 | .196 | .204 | 127.0 |
| Whisper turbo | 1.333 | .203 | .192 | .258 | .150 | .221 | .203 | .217 | 58.6 |
| turbo reset | .889 | .190 | .184 | .233 | .154 | .224 | .196 | .204 | 55.7 |
| turbo VAD | .778 | .233 | .220 | .263 | .163 | .237 | .221 | .228 | 50.4 |
| Qwen 1.7B 4-bit | .278 | .361 | .359 | .496 | .307 | .322 | .363 | .361 | 53.8 + 1.6 load |
| Qwen 30s | .222 | .328 | .314 | .487 | .364 | .284 | .351 | .349 | 52.2 + load |
| Gemini 3.5 Transcribe | .056 | .174 | .135 | .217 | .160 | .208 | .179 | .177 | 92.7 |
| Gemini 3.8 Flash | .056 | .167 | .118 | .171 | .116 | .192 | .154 | .152 | 65.3 |
| Scribe v2 | .056 | .157 | .106 | .167 | .091 | .148 | .133 | .132 | 39.9 |

## Material findings

Whisper variants invented repeated phrases over music. Large-v3 lost a negation and confused a person with a room; turbo retained the negation but still confused the noun. The opening lyric boundary was supported by cloud output and the reference. Turbo reset added an end hallucination, while VAD cut real calls. Turbo's raw speed advantage and similar dialogue scores made it worth retaining as a local option.

Cloud results also made material mistakes: Gemini 3.5 changed a phone-scene action and missed a short reply; Scribe corrupted an idiom and a disguise metaphor despite its best aggregate score. Flash/Scribe better preserved some names that Qwen corrupted. Exact disputed words were not independently listened to, so these classifications do not certify correctness. Qwen was weaker on dialogue in this sample and was not chosen as the main repair route.

Scribe supplied native word timestamps but had seven zero-duration words needing repair. Gemini supplied text without native word timestamps. Whisper supplied rough SRT cues, including false long opening cues. Text and timing are separate results; native timestamps and low disagreement do not establish usable final timing.

A historical 84-minute Gemini output started lyrics near 110.932s versus reference 111.9s; an opening omission was not proven. Its timestamps moved backward around 54:48 and 77:56, preventing a credible full-episode word-error comparison from that alignment.

## Provider use and limits

Eighteen baseline cloud calls processed 2,594.937 audio seconds. Summed elapsed was 197.888s: 92.719s Gemini 3.5, 65.292s Gemini 3.8 and 39.877s Scribe, including upload/deletion. Provider latency was not separately measured.

The conservative reservation was US$1.32 against a US$5 ceiling. Estimated combined cost was approximately US$0.1714: US$0.0755 Gemini 3.5, US$0.0431 Gemini 3.8 and US$0.0529 Scribe. No invoice was available. Gemini 3.5 reported 21,631 input tokens, zero top-level output tokens and 2,688 nested output tokens used in estimation; Gemini 3.8 reported 21,775 input, 2,823 output and 4,304 thought tokens. Scribe supplied no token usage; its estimate used audio duration. Twelve Gemini and six Scribe deletion receipts were recorded.

This was a six-excerpt screening exercise. It did not establish episode-wide completeness, actual audio accuracy, English quality, full alignment, native playback or a reusable process on unseen media. The shortlist required a fuller development comparison, not automatic installation.

## Evidence availability

Publication edition of private `turkish-asr-strategy-screen-2026-09-30/screen-results.md`, SHA-256 `1a28540c7944cc198f0766a109a05f94537b9ff2ba797cbad84273bde4f69e13`. Sample media, subtitle/reference text, local/model output and individual provider receipts remain outside Git.
