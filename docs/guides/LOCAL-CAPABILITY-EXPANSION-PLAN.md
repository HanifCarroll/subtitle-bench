# Local Subtitle Recovery Capability Expansion Plan

This document is an implementation and evaluation plan for expanding Subtitle Bench's **local/no-additional-inference-API-cost** capabilities after the Episode 41 local-only production run stopped at an incomplete Turkish source.

It is intentionally narrower than a new production campaign. The goal is to add several genuinely different local acoustic capabilities, test them on a fixed set of existing Episode 41 failures and correct controls, determine which ones materially improve source recovery, and integrate only the useful ones into the existing workbench.

The existing hosted coding agent may orchestrate the work, inspect text/images, make judgments, and directly translate English. "Local/free" in this document means **no additional hosted inference calls or inference API spending** during capability tests. Hardware, electricity, downloads, and the existing agent service are not free in the literal sense.

## 1. Why this work exists

The Episode 41 local-only run preserved the desired production order:

```
Turkish recognition
→ Turkish repair and timing
→ Turkish ready
→ English
→ bilingual finalization
```

It correctly stopped before English because the Turkish source was not ready.

The run already exercised:

- Whisper large-v3-turbo as the primary recognizer.
- Focused Whisper large-v3.
- Qwen3-ASR 1.7B MLX 4-bit.
- Silero VAD.
- HTDemucs separation.
- Turkish WhisperX/wav2vec2 alignment.
- FFmpeg frames and scene context.
- Existing source-review, joining, evidence, and readiness machinery.

Do **not** repeat that exact combination and call it a new experiment.

The unresolved cases showed a more specific limitation: the agent often had only conflicting textual recognizer outputs and image context. It lacked a strong local way to ask questions directly of the waveform, distinguish speech/singing/music more precisely, obtain a materially different acoustic reading, or isolate a target voice rather than generic vocals.

## 2. Ground rules

### Preserve the existing process

Do not replace the current source-first production architecture.

New components are evidence providers for the existing source-review flow. Reuse:

- current video/source hashes;
- scene bundles;
- source decisions;
- Turkish readiness;
- alignment;
- semantic review;
- English checkpoint/export;
- layout and release tooling.

Do not build a second evidence ledger or another general agent framework.

### Preserve Episode 41 as development material

Use the existing E041 local-only run and its saved clips as development cases.

Do not open OpenSubtitles before a raw capability output has been saved for a test case. Reference text may be used afterward to help assess a frozen test result where appropriate, but it must never be fed into the model input.

Do not silently repair the E041 partial source during capability screening and then claim the capability was tested blind.

### No hosted inference

During this plan:

- no Gemini;
- no DeepSeek;
- no Scribe;
- no Google/Deepgram/other hosted speech APIs;
- no free-tier hosted inference;
- no automatic fallback to a provider.

Downloading open/local model weights and source code is allowed.

If a model repository requires accepting a license or access condition that cannot be accepted noninteractively, stop that installation and report the exact user action needed. Do not work around access controls.

### Isolate dependencies

Create reusable environments outside the repository, for example under:

```
~/.local/share/subtitle-bench/
```

Do not mutate the known-working WhisperX or MLX/Qwen environments in place unless the change is fully compatible and reversible.

Record:

- repository/version/revision;
- model identifier/revision;
- weight format/quantization;
- environment path;
- install command;
- model path/cache;
- license/access note;
- disk size;
- observed peak memory when practical;
- observed inference time.

Treat a changed model revision as a new configuration.

## 3. Fixed E041 recovery set

Before installing or running new inference, create one manifest containing short original-video intervals from the **existing unresolved E041 cases** plus correct controls.

Use the private E041 evidence to choose the exact boundaries. Preserve enough surrounding context for the problem.

The set should include approximately:

1. **Opening/credit hallucination**
   - A passage where Whisper/Qwen emitted stock credit language or empty/looping text.
   - Tests whether the method distinguishes music/singing/speech and avoids invented dialogue.

2. **Ordinary battery dialogue**
   - A passage with disputed ordinary Turkish words.
   - Tests normal lexical recovery, not just music classification.

3. **Short guard reply**
   - Tests preservation of brief speech.

4. **Classroom language-switching exchange**
   - Tests multilingual/code-switched recognition.

5. **Mafia or prison dialogue**
   - Use a passage where focused local recovery already improved a long loop but exact words remain interesting.
   - Tests contextual ordinary dialogue and protects against regression.

6. **Music-masked speech or lyric**
   - Tests separation and audio understanding.

7. **Late musical/credit transition**
   - Tests stock-credit hallucination and event classification late in the episode.

8. **At least two known-good controls**
   - Ordinary dialogue already supported by the existing run.
   - A capability must not earn credit merely by changing every candidate.

Prefer 15–60 second clips. Use 60–90 seconds only where context is genuinely required.

Save:

- video SHA-256;
- interval;
- purpose;
- current partial-source text in the interval;
- existing local evidence paths;
- whether the case is unresolved or a control.

Do not include the desired answer in model prompts.

## 4. Capability A — higher-precision Qwen3-ASR

### Question

Is the existing `Qwen3-ASR-1.7B-4bit` configuration losing useful Turkish recognition quality because of quantization/runtime choices?

### Research references

Primary project:

- https://github.com/QwenLM/Qwen3-ASR

Apple-Silicon implementations worth inspecting rather than blindly installing all of them:

- https://github.com/moona3k/mlx-qwen3-asr
- https://github.com/gabrimatic/qwen3-asr-mlx

### Build

First inspect the existing Qwen runner and environment.

Test the smallest controlled change possible:

1. Current 4-bit configuration as baseline.
2. 8-bit or higher-precision configuration if supported by a practical MLX runtime.
3. BF16/FP16 only if it fits the M1 Pro 32 GiB machine with reasonable headroom.

Keep constant where possible:

- exact input clips;
- language;
- audio preprocessing;
- context;
- generation limits;
- chunk boundaries.

Do not change precision, prompt/context, chunking, and implementation all at once.

### Audit the runner

Before attributing errors to Qwen, verify:

- actual sample rate and channel handling;
- complete requested audio reaches inference;
- output/token limit is adequate;
- no state/context leaks between requests;
- raw model output is preserved before parsing;
- language selection is correct;
- the classroom case is handled in a multilingual-compatible way.

### Optional vocabulary context

If supported, test a **small independent glossary of established recurring names** on a name-specific case only.

Do not use reference-derived phrases or the disputed answer as vocabulary context.

### Success signal

Higher precision is useful only if it:

- corrects meaningful words or omissions on unresolved cases;
- preserves correct controls;
- avoids creating more hallucination/loop problems;
- has acceptable memory and latency.

Do not adopt it merely because the text looks more fluent.

## 5. Capability B — FireRedVAD / audio-event map

### Question

Can a better local acoustic event map help distinguish speech, singing, music, overlap, and possible subtitle gaps more reliably than the current Silero-only route?

### Research reference

- https://github.com/FireRedTeam/FireRedVAD

Inspect its current model card/repository documentation before installation and record the exact model/revision used.

### Build

Install in an isolated local environment.

Create a small reusable workbench helper, only if the existing code cannot cleanly consume the output, which emits video-relative intervals with event labels/confidence.

Attach relevant event intervals to existing scene bundles.

Do not create a second source queue.

### Test

Run FireRed and current Silero on the same recovery set.

For the opening/music cases, inspect whether FireRed distinguishes:

- music;
- singing;
- speech;
- combinations/overlap where supported.

For short-reply controls, check whether it drops speech that Silero or supported subtitles retain.

### Rules

Audio-event detection is **evidence**, not a deletion filter.

Never infer:

- "no words" from no speech detection alone;
- "the ASR text is false" merely because music is present;
- exact Turkish wording from an event label.

### Success signal

Adopt it if it surfaces real speech/activity questions that the current path misses or materially improves routing of music/speech cases without suppressing supported dialogue.

## 6. Capability C — local audio-language review

This is the highest-priority new *type* of capability.

### Question

Can a local audio-capable language model answer bounded questions about the original waveform well enough to resolve cases where transcript-only reasoning stalls?

Examples:

- Is there speech beneath this music?
- Is this spoken, sung, or only instrumental?
- What short response is audible after speaker A?
- Which parts are uncertain?
- Does the waveform support candidate A, candidate B, neither, or remain unclear?

### First candidate: Gemma 4 E4B

Official capability documentation:

- https://ai.google.dev/gemma/docs/capabilities/audio

Local Apple-Silicon paths to investigate:

- MLX-VLM: https://github.com/Blaizzy/mlx-vlm
- llama.cpp multimodal: https://github.com/ggml-org/llama.cpp

Use an **audio-capable Gemma 4 E4B** model/configuration. If E4B is impractical, test E2B. Do not substitute a Gemma model variant that does not support audio.

### Install and smoke-test before integration

Do not integrate anything until the audio input path is proven.

Use three simple smoke tests:

1. Clear Turkish speech.
2. Instrumental/music-only passage.
3. Short spoken reply.

Keep the prompt identical where possible while changing audio.

Confirm that:

- the model actually consumes the waveform;
- output changes appropriately with audio;
- Turkish speech produces meaningful observations;
- music-only input does not consistently hallucinate dialogue;
- prompts/chat templates are the documented ones for that runtime.

If these controls fail, stop the Gemma integration and retain the failure report.

### Review modes

Implement one thin local review operation with two possible passes:

#### Blind observation

Input:

- audio clip;
- interval;
- neutral request.

Do **not** provide the disputed subtitle wording.

Ask for:

- whether relevant speech/singing is audible;
- transcription where reasonably supported;
- uncertainty;
- speaker turn structure when useful.

#### Candidate comparison

Run only when needed.

Input:

- same original audio;
- competing candidate readings;
- surrounding scene context.

Ask whether the audio supports:

- candidate A;
- candidate B;
- neither;
- insufficient evidence.

Retain both passes so candidate-induced answer changes are visible.

### Important limitation

The audio model is another fallible model. Its confidence does not make a word true.

### Success signal

The capability is useful if it resolves or correctly preserves uncertainty in cases that transcript-only local evidence could not, while behaving correctly on controls.

## 7. Capability D — Qwen3-Omni, only if practical

### Question

Can a stronger local audio-understanding model materially outperform the small Gemma route on difficult Turkish audio?

### Research reference

- https://github.com/QwenLM/Qwen3-Omni

Turkish must be explicitly supported by the exact model/input path selected.

### Gate

Do not begin this download/install until:

- actual model sizes and quantization options are checked;
- expected peak memory is compatible with the 32 GiB M1 Pro;
- a practical local runtime is identified.

Prefer a quantized llama.cpp/Apple-Silicon route if documented and stable.

If it clearly cannot fit with safe headroom, record "not practical on current hardware" rather than forcing installation or swap-heavy inference.

### Test

Use the same local-audio-review smoke tests and only a subset of the recovery set.

Do not make Qwen3-Omni mandatory if Gemma already provides the useful local audio-review function at much lower operational cost.

## 8. Capability E — SAM Audio Small target-specific separation

### Question

Can target-specific local separation recover speech that generic HTDemucs vocals did not?

### Research references

Original:

- https://github.com/facebookresearch/sam-audio

Apple-Silicon/MLX model/runtime availability should be verified before download. The prior research identified an `mlx-community/sam-audio-small` conversion; verify its current repository/model card and requirements before using it.

### Build

Install in an isolated environment.

Start only with short clips.

For selected masked/overlapping cases, generate:

- target stem;
- residual stem;
- original retained alongside both.

Example targets may include phrases such as "man speaking" or a temporally identified voice, depending on the documented prompting interface.

Do not feed desired Turkish words as the separation prompt.

### Test

Transcribe:

1. original mix;
2. target stem;
3. residual where useful.

Use the same recognizer/configuration to compare the acoustic views.

### Success signal

Useful separation should recover or clarify real speech without deleting important consonants/words or manufacturing a cleaner but incorrect ASR result.

Do not replace original-audio evidence with a separated stem.

## 9. Capability F — one RoFormer-based separator

### Question

Does a modern music/vocal separator provide a materially better speech view than the tested HTDemucs configuration?

### Research reference

- https://github.com/nomadkaraoke/python-audio-separator

Select **one** suitable BS-RoFormer or Mel-Band RoFormer vocal model based on current documentation and Mac compatibility.

Do not download a large ensemble.

### Test

Use the same music-masked recovery clips used for Demucs and SAM Audio.

Preserve the original mix and outputs.

Measure:

- separation time;
- memory;
- downstream ASR change;
- whether correct controls remain intact.

Adopt only if it supplies useful evidence on cases Demucs did not.

## 10. Capability G — VibeVoice-ASR

### Question

Can a different long-form/speaker-aware local recognizer improve contextual Turkish dialogue and language switching?

### Research reference

- https://huggingface.co/microsoft/VibeVoice-ASR

Prior research also identified MLX conversions. Verify the exact current model card/revision and Turkish support before download.

Do not accidentally substitute a VibeVoice streaming checkpoint whose documented language coverage differs from the multilingual long-form ASR model.

### Hardware gate

Record download size and observe memory/latency on one short clip before running the full recovery set.

If the model is impractical on the 32 GiB machine, stop cleanly.

### Test

Prioritize:

- classroom language switching;
- short speaker exchanges;
- one mafia/prison dialogue case;
- controls.

Do not run a full E041 transcription during this phase.

### Success signal

Useful if it provides materially better supported dialogue/speaker turns than current Whisper/Qwen evidence on the fixed clips.

## 11. Capability H — Meta Omnilingual ASR CTC

### Question

Can a genuinely different acoustic architecture provide useful independent evidence on short Turkish disputes?

### Research reference

- https://github.com/facebookresearch/omnilingual-asr

Verify current Turkish language code/support from the official repository. Prior research identified `tur_Latn`.

### Configuration

Start with a smaller CTC model, preferably around 300M; consider 1B only if needed and practical.

Do not begin with a 7B model.

Run in an isolated environment.

### Why CTC matters

The purpose is not "another fluent transcript." A CTC recognizer provides a different acoustic decoding path from the autoregressive recognizers already in use.

### Test

Use short clips within the model's documented input-length limits.

Focus on:

- disputed ordinary words;
- short replies;
- candidate negation;
- correct controls.

### Success signal

Adopt it as targeted evidence if it changes unresolved decisions for the better without broad control regressions.

## 12. Capability I — acoustic candidate scoring with the existing Turkish wav2vec2 model

### Question

Can the already-installed Turkish wav2vec2/CTC model help compare a small set of competing readings against the same waveform?

Current aligner/model:

`mpoyraz/wav2vec2-xls-r-300m-cv7-turkish`

Inspect its current model card and exact cached revision before adding another use.

### Build

Create a small experimental tool, separate from final acceptance logic, that can:

1. Decode a bounded audio clip without forcing candidate text.
2. Score a few supplied candidate Turkish strings against the same audio.
3. Report normalized candidate scores and the unconstrained decode.
4. Allow an explicit "neither / insufficient acoustic support" outcome.

A possible decoder helper to investigate:

- https://github.com/kensho-technologies/pyctcdecode

Do not add a strong language model initially; first inspect acoustic evidence.

### Calibration

Candidate scoring is easy to misuse.

Test it on:

- known-correct candidate versus obviously wrong candidate;
- two near variants;
- a case where neither candidate is correct;
- different crop boundaries.

If the scorer simply prefers shorter/more common strings or always chooses one supplied option, do not integrate it into production.

### Success signal

It is useful only if it provides calibrated targeted evidence on short disputes. Forced alignment or the highest score must never automatically approve text.

## 13. Capability J — Turkish-specific Whisper checkpoint, optional later test

This is lower priority than the capabilities above.

### Candidate

Prior research identified:

- https://huggingface.co/selimc/whisper-large-v3-turbo-turkish

Verify current model card, provenance, license, and evaluation before use.

### Test

Use the same ordinary-dialogue/name/short-reply clips.

Do not run another full episode.

The model was adapted on Turkish speech data; that does not establish superiority on this television series, songs, overlap, or music.

Adopt only if it materially improves the fixed recovery set.

## 14. Longer-term capability — series/domain adaptation

Do not implement this in the first pass.

Create only a short feasibility note if the tests above remain insufficient.

Potential future work:

- Build a clean training set from independently supported passages.
- Exclude reference-only or unsettled text.
- Preserve episode-level train/evaluation separation.
- Consider fine-tuning a suitable Whisper, Omnilingual, VibeVoice, or other trainable recognizer.
- Include recurring character names, acoustic conditions, and comedic dialogue.

Do not train on raw OpenSubtitles files as if they were ground truth.

## 15. Experimental execution order

Do not install and test everything simultaneously. Work through this order, but **complete all requested capability evaluations unless a documented hardware/license blocker prevents one**.

### Phase 0 — manifest and baseline

1. Freeze the fixed E041 recovery-set manifest.
2. Materialize the exact local clips.
3. Save current Whisper/Qwen/Silero/Demucs outputs as baseline evidence.
4. Record current model/runtime revisions.
5. Do not change E041 source files yet.

### Phase 1 — low-cost/current-stack upgrades

Test:

1. higher-precision Qwen;
2. FireRedVAD/audio events.

These should require relatively little new architecture.

### Phase 2 — local audio understanding

Test:

1. Gemma 4 E4B audio;
2. E2B fallback if required;
3. Qwen3-Omni only if practical on current hardware.

Do the smoke tests before running unresolved cases.

### Phase 3 — separation

Test:

1. SAM Audio Small;
2. one RoFormer separator.

Only on masking/overlap cases.

### Phase 4 — alternative ASR

Test:

1. VibeVoice-ASR;
2. Omnilingual CTC;
3. optional Turkish-specific Whisper checkpoint.

### Phase 5 — acoustic candidate scoring

Implement/calibrate the Turkish wav2vec2 CTC scoring experiment.

### Phase 6 — integration decision

For every capability classify:

- **adopt** — materially useful and operationally acceptable;
- **targeted-only** — useful for a particular failure class;
- **reject** — no meaningful improvement or harmful;
- **blocked** — hardware/license/runtime prevented a fair test.

Integrate only `adopt` and justified `targeted-only` capabilities into existing scene review.

## 16. Evaluation rules

For each model/tool/capability and each applicable recovery clip, record:

- input interval and hash;
- configuration/model revision;
- raw output before repair;
- elapsed inference time;
- peak memory where practical;
- result on the unresolved question;
- effect on a correct control;
- whether it adds evidence, resolves a question, contradicts current text, or remains unusable.

Use qualitative decision categories:

- **material improvement**;
- **minor useful evidence**;
- **no material change**;
- **regression**;
- **inconclusive**.

Do not report an invented aggregate "accuracy" percentage unless a legitimate labeled dataset supports it.

### What counts as a material improvement

Examples:

- recovers an omitted intelligible reply;
- correctly rejects a stock-credit hallucination;
- supplies a better-supported meaning-changing word;
- distinguishes speech from singing/music in a way that changes recovery routing;
- isolates speech so an independent recognizer can recover useful words;
- preserves a correct control while improving a failure;
- explicitly and correctly leaves an unclear case unresolved instead of manufacturing text.

### What does not count

- more fluent-looking Turkish without better acoustic support;
- confidence alone;
- agreement by two highly related models;
- reducing queue counts by inserting uncertainty captions;
- reference similarity caused by feeding reference vocabulary;
- output that damages known-good controls.

## 17. Carry successful capabilities through a small production slice

A capability is not fully useful merely because it produces an interesting transcript.

For each adopted capability, use one or more affected E041 scenes to demonstrate:

```
new local evidence
→ source decision
→ Turkish repair/timing
→ direct-agent English for that repaired scene
→ English review
→ display export
→ focused consistency/layout check
```

Do this in a separate development copy.

Do not rewrite the frozen E041 partial baseline.

This confirms that the evidence can actually improve subtitle production rather than merely create more alternatives.

## 18. Integration design

Prefer a small set of generic interfaces.

Possible additions:

### `local-audio-observe`

Inputs:

- video/audio;
- interval;
- model profile;
- neutral question;
- optional candidate-comparison mode.

Output:

- model/revision/runtime;
- original-audio hash;
- raw response;
- parsed observation;
- hearing method = local audio model;
- uncertainty.

### `audio-event-map`

Inputs:

- video/audio;
- detector profile.

Output:

- video-relative event intervals;
- detector/model revision;
- confidence/labels.

Attach relevant intervals to normal bundles.

### `alternative-asr`

Inputs:

- clip;
- recognizer profile.

Output:

- exact model/runtime;
- raw transcript;
- timestamps when available;
- completion status.

### `candidate-acoustic-score`

Experimental only until calibrated.

Inputs:

- bounded original clip;
- candidate strings.

Output:

- unconstrained decode;
- normalized candidate scores;
- explicit warning that score is not proof.

Do not generalize these into a large plugin architecture unless repeated duplication actually requires it.

## 19. Hardware and failure discipline

Hardware baseline:

- Apple M1 Pro;
- 32 GiB unified memory.

For every heavyweight capability:

1. check weight/download size first;
2. run one smoke-test clip;
3. observe memory and runtime;
4. avoid running heavyweight models concurrently;
5. stop if swap/memory pressure makes the test operationally unreasonable.

A model that technically runs but takes impractical time per 30-second clip may be rejected for production even if accurate.

Do not delete existing model caches to make room without explicit user permission.

## 20. Security, licenses, and downloads

Before executing third-party code:

- use the official repository/model card where possible;
- record license;
- inspect installation instructions;
- avoid piping arbitrary network scripts directly to a shell;
- prefer pinned package/repository revisions;
- keep environments isolated;
- do not place credentials in commands or logs.

If Hugging Face access requires authentication already available locally, use normal local mechanisms without printing tokens.

If user acceptance of a model license is required, pause only that model and report the exact action. Continue other independent capability tests.

## 21. Repository changes

Code changes should be incremental and focused.

Allowed:

- new reusable local capability scripts;
- tests;
- setup documentation;
- configuration/profile registration;
- scene-bundle integration;
- evaluation reports.

Avoid:

- episode-specific repair scripts;
- a second workbench;
- generalized dependency frameworks with no immediate use;
- silently replacing current defaults before evidence supports the change.

After each integration:

- run relevant focused tests;
- run the existing portable suite before final commit;
- inspect Git diff/whitespace;
- preserve private media/model output outside Git.

Do **not** commit model weights, clips, raw subtitle text, raw provider/reference data, or private media.

## 22. Deliverables

At the end, leave:

1. **Capability inventory**
   - installed/rejected/blocked;
   - model/revision/runtime;
   - disk and practical memory/runtime notes.

2. **Fixed recovery-set manifest**
   - private if it exposes subtitle/media content;
   - public summary without protected text.

3. **Raw capability results**
   - private, hash-bound to media.

4. **One public comparison report**
   - no protected subtitle/media excerpts;
   - capability-by-capability conclusions;
   - elapsed times;
   - memory notes;
   - control regressions;
   - adopt/targeted/reject/blocked decision.

5. **Reusable local tools**
   - only for capabilities that need integration.

6. **Tests**
   - smoke tests;
   - parsers/input identity;
   - regression cases for any discovered software bugs;
   - no claim that synthetic tests establish language accuracy.

7. **A revised local-only production profile**
   - only after evidence supports it;
   - list the default primary and the targeted recovery policy.

## 23. Final decision

After testing all feasible capabilities above, answer:

> Can the expanded local-tool route now recover the failure classes that blocked E041 well enough to justify another full local-only production run?

If yes:

- identify the exact adopted tool order;
- estimate expected local runtime from observed data;
- propose one next full run;
- do not start it automatically.

If no:

- identify which acoustic questions remain beyond the tested local stack;
- state which capabilities helped but were insufficient;
- do not hide the negative result behind more framework work.

The endpoint of this plan is a **capability decision**, not a perfectly repaired Episode 41 and not another indefinite experiment campaign.
