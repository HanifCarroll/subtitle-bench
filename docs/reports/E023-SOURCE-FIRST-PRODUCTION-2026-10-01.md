# E023 source-first production run — 1 October 2026

Both full subtitle exports are complete and usable as candidates for the 82m 29.621s episode: Turkish with 1,307 display cues and English with 1,248 display cues. All 1,258 settled source units have reviewed English. The final stage is **partially verified**: exports and sampled libass renders passed, but representative native playback is blocked by the capture service. No installation was performed.

## Actual stage times

| Stage | Observed wall time | Result |
|---|---:|---|
| Turkish repair, timing and ready checkpoint | 73m 21.8s | Complete, with two honest indistinct-speech captions |
| Approval wait within Turkish stage | 2m 18.6s | Included above; source stage excluding this wait was 71m 3.2s |
| Missing English generation and checkpoint | 0m 19.2s | 30 units; three concurrent DeepSeek requests took 5.139s |
| Whole English review | 4m 24.1s | Every unit reviewed; four later frame-context corrections included below |
| Final timing, layout, exports, rendering, native attempts and reports | 32m 0.2s | Export/render complete; native verification blocked |
| Total through this saved status | 110m 5.3s | Includes tool, context, reporting and approval overhead |

These are actual wall times, not pure model speed. Reused initial transcription and the prior 187-unit translation section were not repeated. Individual measured work: initial alignment 302.988s; settled alignment 313.880s; final alignment 297.450s; two-window timing refinement 7.151s; focused initial local ASR 179.597s; hosted audio batch 680.229s. One hosted request took about 548s. Rendering and native-attempt time is included in the final-stage wall time, not separately claimed as model runtime.

## Source and English repairs

Used the saved independent five-minute Gemini draft and matching original-audio evidence. Removed 13 chunk-seam duplicates, joined a split boundary utterance, removed another duplicated fragment, and retained independently supported wording over provider inventions. Focused repairs included the staff struggle and its object/person instructions, the babysitting idiom, shouted instructions, the fighter's address/names, the music-masked reply, the plainclothes-police exchange, and the final father's question. Rejected hallucinated plate/cake ownership, a snack/tea sentence during fighting, phantom telephone wording, and unsupported final words.

The source pass adjusted 855 unit boundaries, then refined 19 coverage tails and two final speech boundaries. These counts describe passes and overlap; they are not a sum of distinct cues. The Turkish-ready checkpoint was saved before new English generation. Source text from the valid 187-unit section was preserved.

Reused 1,228 English units where source/evidence matched, including the previously reviewed 187-unit section. DeepSeek generated only the 30 missing units. The agent reviewed all 1,258 units against settled Turkish and adjacent dialogue, using saved scene frames for concrete referents. Saved 129 correction operations across 128 distinct units, including meaning, idiom, actor/object, negation, repetition and wording repairs. Four final corrections addressed the staff, a bench/broom remark, and threat dialogue. Provider authorship remains recorded separately from agent approval.

## Verified exports

Both exports are UTF-8, ordered, within video duration, nonoverlapping, and preserve all reviewed words. Each has at most two lines and 42 characters per line. Source and English use separate display segmentation with intact source links. Current semantic-review and material timing checks have no blockers. The whole final coverage scan has 21 gaps, assessed in a single saved batch using matching prior decisions and original-audio evidence; 18 VAD misses were not treated as grounds to delete supported text.

All 26 current libass samples passed mechanical checks and were visually inspected, spanning early/middle/late dialogue, both uncertainty captions, the repaired staff/fight/police scenes, and the final father's question. No clipping or corrupted characters was observed. A rendered still is not native moving playback or a listening receipt.

The existing dry release report was run and remains **held**: formal audio decisions are missing, 62 current source queue items lack the gate's receipt format (including 44 coverage items and 7 severe mechanical flags), and 7 source-to-English display-grouping warnings remain counted by that gate. Production adjudication and source-linked review are saved separately; they do not pretend to be those formal installation receipts. The seven grouping warnings were reviewed with neighboring English and are explained by independent display segmentation. The frozen report remains unchanged; no tooling was expanded to suppress it. This pair is not claimed to be installation-certified.

Native IINA inspection reached the private review video and external subtitle chooser. ScreenCaptureKit then failed with error -3812, persisting after observation refresh, reconnect, runtime reset and exact app identification. Final track selection and representative native playback were not verified. Restoring that service would allow the agent to finish the native check with the existing frozen files; no paid regeneration or separate user evaluation session is needed.

## Meaningful limitations

- 30:28.350–30:29.330: a short follow-on instruction remains indistinct after conflicting focused recognition and a failed independent hosted request. Its verb/negation cannot be recovered reliably. Both tracks use an honest caption.
- 57:58.100–58:00.500: music masks a brief reply. Independent hosted recognition also marked it unintelligible; the plausible alternatives were not strong enough to write as fact. Both tracks use an honest caption.
- 42 Turkish display cues (3.2%) and 53 English cues (4.2%) exceed 25 characters/s; 12 and 14 respectively exceed 30. Faithful rapid speech was retained. Some lines therefore require fast reading.
- Supported wording alternatives remain in noisy/comedic passages. The agent did not directly hear original audio. Recognition, alignment and scene observations support decisions but do not certify every spoken word. There was no full-episode watch-through.
- Native playback and the formal installation gate remain unverified/held as described above. Ordinary Turkish dialogue and English coverage are not pending.

## Provider use and preservation

Approved cap: USD 3; up to 40 Gemini audio requests/40 processed minutes and 30 DeepSeek text requests. Actual new use: 39 Gemini calls (36 successful observations, 3 HTTP 503 failures), 20 uploads, 368 unique uploaded seconds and 725 processed seconds (12m 05s); three DeepSeek text requests. No automatic retries, new initial transcription, or subscription. All 20 uploaded provider files were deleted with saved receipts.

Saved usage estimate: USD 0.2446392; failed calls have no returned usage and conservative preflight reservations add USD 0.05545125. Known usage plus those reservations is USD 0.30009045, below the approved USD 3 cap. This is an estimate, not an invoice; prior reused transcription/section cost is excluded. Rates were checked against [Google](https://ai.google.dev/gemini-api/docs/pricing) and [DeepSeek](https://api-docs.deepseek.com/quick_start/pricing/).

Both independent final outputs were frozen at 19:29:20.991 UTC before any new reference comparison. No OpenSubtitles/reference-derived production corrections or new reference comparison were used. Nine historical comparison artifacts and both installed sidecars have unchanged hashes. Prior reference exposure makes this a development run, not blind qualification. No production code, tools or repository organization were changed during this run. This publication adds the report and its navigation links only.

## Evidence availability

This is a publication edition of the private `production-023-source-first-2026-10-01/REPORT.md`. It preserves outcomes, actual stage times, repairs, provider use and limitations without publishing subtitle text, raw model output, media, credentials, cases or rendered frames. Private report SHA-256: `499fd4c57315a1fafaa68f2835037996f3a8a46ff94f64772c9c0a6424c5a43f`.

| Frozen artifact | SHA-256 |
|---|---|
| Turkish final export | `5e3f1dd884c65f9ae6abc9684b191e92da1848bd61d68e78e45fd4d88df1bfc6` |
| English final export | `ec2aed61e9483e71370c80a9a5a339875ad0d398e458f4574a3de12178b3fc1b` |
| Source-linked final meaning map | `d2d46edb3dd3522e09dd9c3b7d44645a18e8efcb21e2eeb1027e95a65e7c0291` |
| Turkish-ready checkpoint | `483a01f742670252d8a4fc86f98cc84a27d88d589df652332e1e2c09c674f2d8` |

The private run retains stage records, provider provenance and usage, source adjudication, coverage decisions, all English corrections, 63 current meaning-review batches, measured alignment, display links, timing decisions, final consistency checks, independent output freeze, 26 rendered checks and visual review, native-capture error status, and the held dry release report. Hashes identify artifacts; they do not make private evidence accessible to a repository reader. These are agent-authored development results, not independent linguistic qualification.

Read [PROCESS.md](../../PROCESS.md) for the authoritative sequence, the [earlier English-path comparison](ENGLISH-PATH-COMPARISON-2026-10-01.md) for the provisional translation choice, and the [report index](README.md) for prior checkpoints.
