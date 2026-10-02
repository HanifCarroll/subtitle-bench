# Local acoustic capability comparison — October 2, 2026

**Decision: the tested expansion does not justify another full local-only production run.** FireRed adds useful targeted speech/music/singing routing. Qwen 8-bit demonstrated reduced looping at about 0.80 GiB extra MLX peak memory; that operational benefit is retained separately from word accuracy. No new configuration establishes a reliable recovery of the meaning-changing words, brief replies, language switches, or masked speech that held E041. SAM Audio Small remains access-blocked; its potential is unknown.

This executes the [authoritative expansion plan](../guides/LOCAL-CAPABILITY-EXPANSION-PLAN.md) at starting revision `cef34db`. All feasible requested capability families were tested, including both Omnilingual sizes and the optional Turkish Whisper checkpoint. No hosted inference, full E041 production attempt, training campaign, or playback installation was performed. Existing caches and large files were retained.

The pushed comparison was reviewed and the completed capability tests are closed. Their outputs, baselines, environments, and caches are preserved. The Qwen 8-bit classification below is a refinement of the existing frozen results, not another benchmark. SAM Audio Small is the only pending experiment; its follow-up access check is recorded below. No other model tests or full episode run were started during this follow-up.

## Comparison conditions and limits

Hardware: Apple M1 Pro, 10 CPU cores, 32 GiB unified memory, macOS 27.0. Heavy models ran sequentially. The four new environments are reusable and isolated; the existing Qwen, WhisperX, and Demucs environments were preserved. [Setup and operation notes](../guides/LOCAL-CAPABILITIES-SETUP.md) record paths, versions, access conditions, and commands.

Before new inference, 921 baseline files (635,074,099 bytes) were copied and hashed. The frozen partial Turkish source has SHA-256 `05999e14a81220975aa430b553bb638ff24e686a19be90f68c55d689135f16e5`. Original and copied baselines remain unchanged. Media identity, current source text, purposes, clip hashes, and baseline receipt paths are in the private recovery manifest.

| Fixed case | Original interval, seconds | Purpose |
|---|---:|---|
| Opening | 0–30 | Credit/word hallucination and music |
| Battery | 120–165 | Disputed ordinary dialogue |
| Guard | 720–741 | Brief replies and corrupted words |
| Classroom | 1398–1420 | Language switching |
| Prison | 1180–1220 | Contextual dialogue and preservation |
| Mafia | 3208–3253 | Important continuation/negation |
| Song | 565–605 | Singing and masked words |
| Late music | 4128–4168 | Musical transition and stock text |
| Police overlap | 4259–4295 | Overlapping dialogue/loop |
| Cafe control | 300–318 | Supported negation and short reply |
| Plan control | 934–949 | Supported ordinary dialogue/names |

The eleven intervals total 352 seconds. Models with short input limits used the same frozen, contiguous subdivisions of at most 30 seconds: 17 inputs, with no omitted tail. An additional 1.38-second reply was used for audio-path smoke tests and scorer calibration. Separation used the same four stereo originals; recognizers received matched mono 16 kHz views. The opening WAV is 29.979 seconds because the source audio begins 21 ms after video zero; this offset was recorded, not silently padded with invented evidence.

Controls are supported by the existing baseline, **not independently labeled listening ground truth**. The agent inspected saved outputs and timestamped frames but did not directly hear the original audio. Receipts disclose that limitation. This is a qualitative development screen; there is no defensible aggregate accuracy percentage. Agreement, fluency, confidence, empty decoding, and fewer queue items were never sufficient to approve wording.

No OpenSubtitles/reference text was opened, including during assessment. Each blind observation was saved before its relevant candidate comparison. The initial screen was hash-frozen before scorer calibration; later audit reruns retained the same audio-only settings and preserved initial outputs. Only the experimental scorer and the later Omni comparison received candidates after their blind observations had been saved. They did not receive a desired transcript in generation or first-pass observation.

## Capability decisions

Decisions concern these exact model/runtime configurations, not every possible implementation of a model family. **No new word-recovery configuration earns `adopt`.**

| Capability | Evidence and effect on controls | Classification |
|---|---|---|
| Qwen3-ASR 8-bit | Avoids two observed 4-bit loops at 3.659 versus 2.858 GiB MLX peak memory. Some spellings and the cafe reply improve relative to 4-bit, but those words were already available in baseline Whisper. Important guard/classroom/mafia/police wording remains unsettled; music still receives unsupported phrases. | Targeted-only, loop robustness; no established new word recovery |
| Qwen3-ASR BF16 | Similar unresolved meanings, more memory, and slower inference. Removing a loop does not establish the replacement words. | Reject as precision upgrade |
| FireRed AED + VAD | Adds simultaneous speech/singing/music observations and directs music cases away from ordinary dialogue recovery. Detects the short reply, but ends its event 290 ms before the supported cue ends. No words are deleted or trimmed. Does not distinguish multiple speakers. | Targeted-only, activity routing |
| Gemma 4 E4B audio | Audio-capable configuration receives actual WAV input through the documented template. The required smoke battery fails overall: clear Turkish is meaningful but imperfect, music produces invented singing language, and the short reply is wrong. The broader 17-input diagnostic screen does not cure this. | Reject; no integration |
| Gemma 4 E2B audio | The same three smoke inputs fail: music is missed and the short reply is wrong. | Reject; no integration |
| Qwen3-Omni 30B-A3B 4-bit | Default template produces special-token corruption. A documented assistant prefill improves that failure, but invents/repeats words on the short reply and changes controls. Music descriptions are sometimes useful; guard/classroom/mafia words remain unreliable. Memory/swap cost is excessive for this evidence quality. | Reject |
| SAM Audio Small | Original checkpoint requires manual license/access acceptance. The follow-up weight-access check returned `401 GatedRepo`; no local credential is configured. Public MLX conversions were not used to bypass the gate. No fair inference test was possible. | Blocked, authorized local access unavailable |
| BS-RoFormer Viperx 1297 | Runs on MPS. Original/vocal/residual comparisons add alternative hallucinations, not established new words. Whisper loses the supported cafe reply on its vocal stem, while original and matched Demucs retain it. | Reject |
| VibeVoice-ASR 4-bit | Correct long-form multilingual checkpoint, no hotwords/context. Structured turns and music labels work, but a supported cafe negation becomes obligation; ordinary/name controls change. | Reject |
| Omnilingual CTC 300M v2 | CPU inference works. Different phonetic decoding still joins/substitutes words and drops replies; no new meaning-changing decision becomes supportable. | Reject for production recovery |
| Omnilingual CTC 1B v2 | Fits and was tested on all 17 inputs. An already-correct baseline noun is clearer; unresolved wording and short replies remain unreliable. Greater resource use yields no demonstrated new recovery. | Reject for production recovery |
| Turkish Whisper turbo fine-tune | Same whisper.cpp runtime/settings as original turbo. Adds lyric candidates, but corrupts supported negation and names/ordinary dialogue; stock music text remains. | Reject |
| Turkish wav2vec2/CTC scorer | Blind decode and forced-path scores are preserved separately. It can beat an obviously wrong candidate, yet prefers an incomplete/wrong short form under crop changes and harmful negation over supported wording. Music/blank dilution can make a wrong phrase score deceptively well. | Reject production scoring; retain experimental tool |

The existing Qwen 4-bit, Silero, Whisper, aligner, and HTDemucs remain baseline evidence tools; this screen does not newly qualify them as word judges.

Retain 8-bit as an optional bounded Qwen configuration for loop-prone clips, with the same window/token guards and unchanged standards for acoustic support. It is an operational reliability option, not a default accuracy upgrade or a reason to reopen the completed comparison. BF16 remains rejected as a precision upgrade.

### Qwen runner finding

`mlx-audio 0.5.6` subtracts each chunk's generated tokens from one shared budget and stops processing when that budget is exhausted. In the initial 11-clip 4-bit screen, a looping first chunk consumed 512 tokens on late music and police overlap, leaving the tail unprocessed. Loading the complete WAV did not mean the entire WAV reached acoustic inference.

All three precisions were therefore rerun on the **same 17 frozen inputs of at most 30 seconds**, with temperature 0, batch size 1, 512 tokens, no contextual vocabulary, and identical audio. Classroom uses automatic language selection; the other inputs request Turkish. Raw text before language parsing, input sample counts, generation tokens, and result objects are preserved. Higher precision avoids the two loops in this comparison but does not establish the missing meanings.

The shared workbench operation now caps a window at 30 seconds and uses actual generation-token counts to flag exhaustion, even when output contains few whitespace-separated words. Historical tokenless caches retain their limits; they are not retroactively certified. The pre-existing change that labels Whisper evidence using the actual model filename is preserved and tested.

### Audio understanding and separation checks

[Gemma's official audio interface](https://ai.google.dev/gemma/docs/capabilities/audio) supports the E4B/E2B audio path and short audio inputs. Both selected conversions contain the audio tower/configuration. The neutral observation prompt and audio chat template were fixed across smoke controls; an additional documented ASR prompt variant was tested for E4B. Failed controls stopped integration. The broader E4B outputs are diagnostic evidence, not an alternative approval route.

[Qwen3-Omni](https://github.com/QwenLM/Qwen3-Omni) explicitly supports Turkish. Its existing local 4-bit weights were reused after the size/runtime gate. The documented [MLX-VLM prefill issue](https://github.com/Blaizzy/mlx-vlm/issues/1770) explains the additional fixed-prefix configuration. Both default and prefilled outputs remain inspectable. Two later music comparisons preserve the earlier neutral observations; their claims of insufficient support for stock subtitle language do not overcome the failed word controls or establish absence of obscured speech.

RoFormer was compared with original audio and preserved Demucs output, then with **fresh Demucs on the exact same original intervals** to remove separation-context differences. Both recognizers/configurations were held constant across acoustic views. An incorrectly offset draft stem crop was caught and replaced before any inference on that draft; it contributed no result. Every original, stem, and raw recognizer output was retained. Neither separator supplies an accepted new wording repair.

### Scorer calibration

The [cached Turkish wav2vec2 model](https://huggingface.co/mpoyraz/wav2vec2-xls-r-300m-cv7-turkish) was decoded greedily without the card's KenLM language model. Twenty-one blind observations cover the fixed subdivisions plus short-reply/crop/negation controls. Seven candidate comparisons cover correct-versus-obviously-wrong, near variants, neither, changed crop boundaries, negation, and music. Candidate input happens after frozen acoustic observation.

The dynamic program sums CTC paths, including repeated-token/blank transitions. Portable enumeration checks establish that calculation, not linguistic calibration. Per-frame and per-token normalization expose different length/crop effects. The result defaults to `insufficient_acoustic_support` and lists `neither` as an available assessment; it never automatically selects or approves the highest-scoring text. The failed calibration rules out production integration.

## Observed speed and memory

GB below means decimal file size; GiB means memory bytes divided by 2^30. MLX peak is the allocator measurement, RSS is the process high-water mark, and footprint is `/usr/bin/time -l`; they are not interchangeable or complete system-memory measurements. Inference totals exclude loading/imports unless stated. These are one-pass observations, not benchmark averages.

| Configuration | Tested scope | Total / per-input seconds | Observed memory |
|---|---|---|---|
| Qwen 4-bit, corrected comparison | 17 inputs / 352 s | 28.398 / 0.334–6.631 | 2.858 GiB MLX peak |
| Qwen 8-bit | Same 17 | 25.543 / 0.374–3.274 | 3.659 GiB MLX peak |
| Qwen BF16 | Same 17 | 38.904 / 0.404–5.208 | 5.161 GiB MLX peak |
| FireRed AED | 11 + short reply | 1.254 / 0.050–0.130 | 0.334 GiB max RSS |
| FireRed VAD | Same 11 | 1.109 / 0.070–0.125 | Separate VAD peak not sampled |
| Silero baseline comparison | Same 11 | 4.025 / 0.278–0.574, includes CLI/load | Not sampled; timing differs from AED |
| Gemma E4B smoke / broader screen | 3 / 17 | 6.306 / 51.097; screen 0.845–5.647 | 5.573 / 5.569 GiB MLX peak |
| Gemma E2B smoke | 3 | 3.090 / 0.237–2.042 | 4.101 GiB MLX peak |
| Omni default smoke | 1 | 34.594 generation; 50.83 process/load | About 23 GiB process footprint |
| Omni prefilled smoke / subset | 3 / 6 | 78.327 / 89.358; subset 4.637–53.990 | Up to 20.756 GiB MLX peak |
| Omni later music comparison | 2 | 46.693 / 7.426–39.266 | 20.700 GiB MLX peak |
| RoFormer, MPS | 4 / 127.979 s | 274.724 / 30.573–85.731, plus 1.688 load | 4.15 GiB process footprint; 1.581 RSS |
| Matched HTDemucs, CPU | Same 4 | 45.714 / 8.578–12.679, includes process/load | 1.759 GiB process footprint |
| VibeVoice | 11 / 352 s | 112.670 / 4.665–17.767 | 6.871 GiB MLX peak; 7.73 footprint on smoke |
| Omnilingual 300M | 17 / 352 s | 22.488 / 0.336–2.087 | 4.016 GiB max RSS in batch |
| Omnilingual 1B | Same 17 | 44.728 / 0.694–4.098 | 7.661 GiB max RSS in batch |
| Original Whisper turbo | Same 17 | 35.158 / 1.533–3.506, includes process/load | 1.838 GiB process footprint |
| Turkish Whisper turbo | Same 17 | 41.887 / 1.554–5.760, includes process/load | 1.849 GiB process footprint |
| wav2vec2 blind observation | 21 | 33.174 / 0.199–4.229 | 1.59 GiB single-clip RSS; 9.004 repeated-load batch RSS |

Qwen 8-bit's lower total includes avoidance of 4-bit looping; it is not evidence that higher precision is intrinsically faster for equivalent output. Scorer batch RSS includes repeated model loading/mapping retention; it is not the model's minimum memory requirement.

During the final bounded Omni comparison, system swap increased from about 16.50 to 20.06 GiB despite sequential model execution. Background applications prevent exact attribution of all swap to this task. Further Omni testing stopped at the documented operational gate. Its accuracy had already failed controls. No cache deletion was used to make it fit.

## Exact installed models and revisions

| Configuration | Model/revision or checkpoint identity | Cached/build size | Access/license note |
|---|---|---:|---|
| Qwen 4-bit, reused | `mlx-community/Qwen3-ASR-1.7B-4bit@78a389c776a5483b2d0d4ea5494e11012e0d6159` | 1.608 GB | Apache-2.0 |
| Qwen 8-bit | `mlx-community/Qwen3-ASR-1.7B-8bit@a8379a2e2f9e313c9292cdf1af4055ab56d50d55` | 2.468 GB | Apache-2.0 |
| Qwen BF16 | `mlx-community/Qwen3-ASR-1.7B-bf16@e1f6c266914abc5a46e8756e02580f834a6cf8a7` | 4.081 GB | Apache-2.0 |
| FireRed AED + VAD | `FireRedTeam/FireRedVAD@7990aaccc6b7aec1e527743bd30201f2c4a03b8c`; code `c30ec49e8cc69642b0ee65362eba11b9d11c6e54` | 0.00475 GB installed model files | Apache-2.0 |
| Gemma E4B | `mlx-community/gemma-4-e4b-it-4bit@475b9088d29754a3379866cf5aeb6b41acd313c2` | 5.179 GB | Ungated conversion; community card says Gemma, current original says Apache-2.0 |
| Gemma E2B | `mlx-community/gemma-4-e2b-it-4bit@238767527555cb75a05732a84dff5d6ba0dd6809` | 3.583 GB | Same card discrepancy recorded |
| Omni, reused | `mlx-community/Qwen3-Omni-30B-A3B-Instruct-4bit@93b3cbddd65ed4babff8f22fba491cdba7a21778` | 21.840 GB | Apache-2.0 |
| SAM, not downloaded | `facebook/sam-audio-small@20b65f56888142eebe7c37448c6f6b3b32600e9b` | 5.101 GB advertised original weights | Gated SAM license/contact-sharing agreement |
| RoFormer | `model_bs_roformer_ep_317_sdr_12.9755.ckpt`; SHA-256 `5b84f37e8d444c8cb30c79d77f613a41c05868ff9c9ac6c7049c00aefae115aa` | About 0.640 GB | Separator code MIT; selected listing does not establish a separate weight license |
| VibeVoice | `mlx-community/VibeVoice-ASR-4bit@a1a15cb6c7b70f76b588af7e12f6fab34d5ab654` | 5.714 GB | MIT, ungated |
| Omnilingual 300M v2 | `omniASR_CTC_300M_v2`; SHA-256 `8ce340ada22435d189908a8af67e3bb04899b6f2f5329d036248b9c3e38d2b50` | 1.304 GB | Apache-2.0, official checkpoint URL |
| Omnilingual 1B v2 | `omniASR_CTC_1B_v2`; SHA-256 `354f981756aa8f41591ea363e45b9c4eba1ec5144c2273af82e747efbb08919c` | 3.903 GB | Apache-2.0, official checkpoint URL |
| Turkish Whisper | `selimc/whisper-large-v3-turbo-turkish@e914cebbaa5f7eefd2b77c2441f2d9a5e30e0286`; GGML SHA-256 `622e00cb466ecdcfec5ccb3d6ba9eab3d3d7c0e5d2bbe89f802c81db80eafab7` | 3.240 GB downloaded; 1.625 GB generated GGML | MIT; Common Voice 17 adaptation, card metrics are not TV evaluation |
| wav2vec2, reused | `mpoyraz/wav2vec2-xls-r-300m-cv7-turkish@708639f50559d7970f462e13ec64d3f059ca89f6` | 1.262 GB cached snapshot | CC-BY-4.0; attribution required |

Approximately 31.74 GB of new checkpoint/tokenizer/build artifacts were retained, including the generated GGML file and RoFormer. This is an artifact-size sum, not measured network traffic. Four new environments occupy about 3.17 GiB by individual directory allocation counts; package-cache hardlinks mean this is not an exclusive additional-disk total. Source checkouts and private evidence require extra space. Omni, 4-bit Qwen, wav2vec2, and existing recognizer/separator weights were reused.

The official [Omnilingual repository](https://github.com/facebookresearch/omnilingual-asr) supplies `tur_Latn`; native CTC was tested on CPU FP32, four threads, with inputs below its limit. The 7B model was not needed. [VibeVoice-ASR](https://huggingface.co/microsoft/VibeVoice-ASR) is the multilingual long-form model, not the narrower streaming checkpoint. [The Turkish Whisper card](https://huggingface.co/selimc/whisper-large-v3-turbo-turkish) documents training provenance; its reported evaluation is not evidence of superiority on this series.

### SAM access action

The October 2 follow-up at 15:36 UTC checked the original pinned repository and issued a HEAD request for `checkpoint.pt`. Repository metadata still reports a manual gate; weight access returned HTTP `401` with `GatedRepo`. No Hugging Face credential is configured locally. This establishes unavailable local access, not whether the user's web account has already accepted the conditions. No weights were downloaded, no runtime was installed, and no inference or replacement benchmark was started. The pending SAM experiment is stopped at this access boundary.

Sign in to Hugging Face, open [SAM Audio Small](https://huggingface.co/facebook/sam-audio-small), personally review and accept its SAM license/contact-sharing terms, request access, and wait for approval if required. Then authenticate locally with `~/.local/share/subtitle-bench/env-vlm/bin/hf auth login` using a read-capable token for the approved account; never paste the token into chat. If acceptance and approval are already complete, only local authentication is needed. Access must authorize the original model before using a conversion. No acceptance was made for the user. SAM remains an untested hypothesis, not a rejected acoustic result.

Once authorized access is available, the remaining experiment is one short audio-path smoke followed by Small on the exact original opening (0–30 s), song (565–605 s), late-music (4128–4168 s), and cafe control (300–318 s) intervals already compared with Demucs and RoFormer. Keep neutral sound descriptions, explicit timing/sample-rate conversions, original/target/residual views, and matched recognizer settings; reuse existing matching baseline outputs. A small prompting comparison is justified only by a specific target ambiguity. Carry an established recovery through a separate development source/timing/English/export copy; otherwise retain an unsettled or negative result. No larger SAM variant, parameter search, other capability search, or full episode run is authorized by this follow-up.

## Scene-level production evidence

Three separate child excerpts preserve parent media/source provenance and original cue IDs. Fresh original-audio Whisper/Qwen, FireRed observations, Silero coverage, a scene overview, and before/during/after frames were saved for each. FireRed enters the existing `saved_evidence` timeline; it creates no second queue or automatic wording decision.

| Development slice | Downstream result | What this establishes |
|---|---|---|
| Cafe, 7.36 s / 3 source cues | Baseline negation/reply retained; source assessment/readiness, alignment, direct-agent English, all-unit semantic review, linked display export, consistency/layout checks, 8 successful render samples | Event evidence survives the existing route without deleting a brief reply or flipping negation |
| Prison, 9.68 s / 4 source cues | Supported reported speech/conditional retained; same downstream steps and 8 successful renders; equivalent shorter English sentence removes a density warning; four sub-second tail warnings retained explicitly | Source context survives cropped recognizer omissions; actor, negation, and condition remain in English |
| Guard, 5.4 s / 3 source cues | Evidence/frames/alignment saved; first reply/address still disputed; no readiness or English | Activity labels and frames do not settle exact words |

Both completed slices have current word timing, zero translation consistency/presentation flags, complete agent semantic reviews, and no material timing blockers. Eight rendered samples were visually inspected across both tracks, including the protected reply and conditional; sixteen samples passed the renderer's checks. Native player playback was not observed. These are preservation/production-plumbing examples, **not newly recovered lexical failures, an accepted episode, or qualification**. No baseline Turkish words were changed to manufacture a success.

## Proposed local-only order

This is a bounded recovery policy for a future explicitly selected episode. The evidence does not authorize or recommend starting another full E041 attempt now.

1. Freeze media/settings. Use existing Whisper large-v3-turbo isolated fresh processes with the current 300-second cores/five-second overlap; preserve raw output and joining receipts.
2. Prepare the existing source case; inspect Silero coverage and recognizer defects. Use scene bundles and timestamped visual context when a referent/speaker matters.
3. For music, masked activity, or a possible short-reply gap, add **FireRed AED** on the original bounded clip. Labels direct investigation; they never approve words, absence of speech, deletion, or automatic cue trimming.
4. Investigate disputed wording with focused Whisper large-v3 and existing Qwen3-ASR on original clips of at most 30 seconds. Keep 4-bit as the baseline and retain 8-bit as an optional loop-robustness configuration at modest extra memory, without treating changed wording as a proven recovery. Preserve raw/token completion evidence; use multilingual-compatible language selection for language switches. Expand surrounding context through additional bounded clips rather than hiding a tail behind one token budget.
5. For genuinely masked material, optionally compare existing HTDemucs vocal/residual views using the same recognizer settings and interval. Retain the original. Do not add rejected RoFormer/audio-language/alternative-ASR/scoring configurations as routine fallbacks.
6. Record supported source decisions. If an important acoustic question remains unsupported, retain uncertainty and stop at incomplete Turkish; do not clear a queue by assertion. Finish batched Turkish timing with the existing aligner before source readiness.
7. Only after substantive Turkish readiness: direct-agent English, every-unit contextual semantic review, separate linked layouts, focused and whole-candidate checks, sampled rendering, and existing dry release review. Installation and native playback remain separate authorized work.

**Now manageable:** locating music/singing/speech mixtures for investigation; preserving supported ordinary dialogue and replies through the existing downstream route; preventing the Qwen multi-chunk/token-budget coverage mistake; and retaining 8-bit's observed loop robustness at modest extra memory. Those are routing, preservation, and operational improvements, not established recovery of outstanding meanings.

**Still unsupported:** exact ordinary battery/guard/police words, some mafia continuations/negation, foreign-language classroom turns, and music-masked words/lyrics. Credible music-event descriptions still do not provide a trustworthy local exact-word/silence adjudicator. There is no demonstrated new lexical failure class that warrants a full run. SAM could change the masking result, but cannot be assumed to do so.

**Recommendation:** retain the Whisper-led source-first stack, bounded Qwen with its window/token guards and optional 8-bit loop robustness, and targeted FireRed activity routing. These improve operational reliability and routing; actual new recovery of the important outstanding words remains unestablished. Preserve unresolved source questions and the stopped SAM Small experiment; another full local-only episode run is not justified.

No reliable full-run runtime estimate follows from fast acoustic kernels while source questions still fail. The only remaining expansion experiment is the authorized matched SAM Small test after local access is available; it is stopped while access is unavailable. Longer-term adaptation remains a feasibility note, not active work: independently supported clean passages, episode-separated training/evaluation, and no raw OpenSubtitles-as-truth training. No training was implemented.

## Reusable changes and verification

Two small operations were added: `audio-event-map.py` for typed FireRed observations and `candidate-acoustic-score.py` for the explicitly requested rejected experiment. The existing source-review adapter validates media/receipt/frame identities and preserves event kinds. Event labels do not become transcript gap text. The workbench Qwen window/token guard and actual Whisper model labeling have portable regressions.

Focused acoustic-input, event mapping, source-review, saved-scene, and evidence-label checks passed during implementation. All 19 README portable checks passed, as did Python compilation and diff whitespace checks. A real FireRed smoke also verified absolute evidence paths when given a relative output. Final results are saved with execution evidence. Synthetic checks verify calculation, parsing, binding, and unsafe automatic behavior—not every Turkish word. No held-out content was inspected or qualification restarted.

The access/classification follow-up changes documentation only. Local documentation links and whitespace were checked; all 917 completed evidence artifacts still match the final freeze. Implementation hashes still match the completed 19-check suite. No capability inference was repeated, and no new runtime, model, or scene repair was produced while SAM access was unavailable.

Private evidence lives in `~/Movies/Leyla ile Mecnun/Workflow/pilots/local-capability-expansion-041-2026-10-02`: frozen manifests, baseline hashes, model/runtime inventory, raw observations/stems, scorer calibration, authored per-case judgments, and scene review/export/render receipts. None of that media, subtitle text, or model output is committed. The public report records conclusions without protected excerpts.
