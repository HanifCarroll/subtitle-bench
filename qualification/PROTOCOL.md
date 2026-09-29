# Qualification protocol, version 2

This protocol is fixed before opening any version 2 held-out subtitle text or audio result. It tests whether a fresh agent can use the reusable process on an unseen episode. Development episodes 38–40, version 1 qualification episodes 016/064/099, and all earlier pilot clips are excluded. A repaired qualification case becomes a regression case; the revised process must use new held-out episodes.

## Input contract and cohort

The normal input is one Turkish episode video. A case may additionally supply a Turkish SRT and an English SRT; each is an untrusted candidate. The agent receives only these paths, a private output directory, and the reusable prompt. It may inspect the video and supplied candidates, and use the tools named in `PROCESS.md` and `WORKBENCH.md`. In the `video_only` case it may not search this library, archive, or neighboring paths for hidden subtitles. This explicitly tests transcription without a good source prerequisite. No user listening, phrase choice, or episode-specific engineering is part of the input contract.

The cohort was chosen from filename and ffprobe duration metadata before reviewing its media or subtitle content. No selected ID had a named prior pilot directory in the metadata check. Selection is fixed:

| Case | Inputs | Video duration | Purpose |
| --- | --- | ---: | --- |
| 007 | Video only; existing library sidecars are outside the allowed input | 82.9 min | End-to-end source recovery and English from video |
| 021 | Video, existing Turkish candidate, existing English candidate | 72.2 min | Source selection, preservation of correct content, repair of errors |
| 077 | Video and existing Turkish candidate; no English candidate | 80.6 min | Source validation and English production |

These durations and file presence are selection metadata, not quality results. The episodes must still be characterized for ordinary speech, short replies, overlap, music, loops, chunk seams, idioms, contextual meanings, and timing defects. If a category does not occur in this cohort, it remains untested and must be covered by a later held-out case or an explicitly labeled development regression.

## Frozen workflow and resources

`freeze.json` binds the prompt, protocol, workbench scripts, model file, and setup instructions by SHA-256. A run starts with `python3 scripts/qualification-runner.py verify`, then `start`; resuming repeats `start` with identical inputs. The runner rejects changed inputs or frozen files and records an event ledger. The agent model for this qualification is GPT-5.6 Luna with Max reasoning, in a fresh task with no previous episode conversation. It must not delegate, run memory tools, edit code, change prompts or thresholds, or inspect development/qualification answers. It may save case data under its private run directory.

The source route is the one in `PROCESS.md`: audio-checked cut reference where supplied and suitable, otherwise Whisper large-v3 with 30-second cores and two-second overlap; full 30-second Qwen3 ASR comparison at the pinned revision; targeted original-audio recovery; source-bound agent-written English batches where needed; Turkish WhisperX alignment; paired timing repair; libass render and release dry check. The local ASR receipt route can document a supported decision when both authentic outputs are complete; it is not an independent accuracy reference and cannot close a failed or repeated Qwen window by itself. Model revisions and observed environment are in `SETUP.md`. Any model substitution, hidden sidecar, new provider, prompt change, hand-written episode-specific script, or threshold tuning is a process change, not a successful qualification run.

Billable provider use is **not authorized** in this cohort. The old Episode 40 plan grants no permission here. The agent can use local evidence and must identify a permission-limited stopping point separately from a technical inability. A later standing authorization would be a new frozen configuration and require fresh held-out cases.

## Completion and stopping rules

The agent has up to eight active hours per episode. Make one full source transcription, reuse its unchanged clip receipts, and use the cached independent audio transcript for targeted rechecks and the final full check. A run stops earlier when it produces a complete candidate pair and a current release dry check, or when further recovery needs a service without authorization, audio is genuinely unrecoverable under `PROCESS.md`, the required environment is unavailable, or the work budget is reached. A large queue, missing English candidate, or failed first dry check is work to do, not itself a stop condition. It must never label an unresolved queue as completion.

`production_complete` requires a full-duration Turkish and English candidate, no known ordinary intelligible omitted dialogue, no known material English error, no unresolved source/audio/timing question, a passing current dry release check, and zero user content decisions. It is **still linguistically unverified** until independent evaluation below. A candidate with an honest indistinct-speech cue is counted as unresolved content. A provider-permission stop, missing dependency, tool failure, or budget stop is `partial` or `failure`, not success. All three attempted cases stay in the denominator.

Record every user request for listening, wording, spending permission, or episode choice as `human_intervention`, even if the user does not respond. Record any code/config/prompt change or bespoke handling as `episode_specific_engineering`. A routine agent decision using the frozen routes is not a human intervention. A process change triggered by a qualification case moves that case to development and still counts its first run as a qualification failure.

## Independent evaluation

Generation and its source/English review loop cannot certify their own linguistic accuracy. A bilingual evaluator who did not create the subtitles should annotate 15 minutes per episode, selected before viewing results as five three-minute windows centered at 3%, 27%, 50%, 73%, and 97% of video duration. The evaluator uses original media to annotate Turkish spoken turns, meaningful English content, and speech timing. Add every repaired high-risk scene and every indistinct-speech cue to the evaluation set. Preserve the evaluator's file, identity, date, video hash, and whether they were blind to the candidate. A trustworthy, cut-verified existing subtitle may support a specific text or timing answer but is not automatically a whole-episode gold reference. Model output remains provisional.

Report per episode and across all attempted episodes:

- Omitted spoken turns, unsupported added turns or words, and material Turkish word errors in the annotated intervals.
- Material English meaning errors, accepting equivalent wording rather than exact strings.
- Cue start/end errors over 500 ms on clear single-speaker speech, holds crossing the next turn, and segmentation that hides a reply; report difficult overlap and music separately.
- Incorrect changes to initially correct supplied candidate text or timing, using before/after candidates and the independent annotation.
- Completed episodes, partials, unresolved content and duration, user interventions, episode-specific engineering, active and elapsed runtime, local computation, provider calls, uploaded/processed audio, and observed or unknown charge.

Any omitted complete turn, unsupported spoken turn, material meaning reversal, or hold across a new spoken turn in the independent sample fails that episode's content criterion. The timing target is at least 95% of clear-speech sampled cue boundaries within 500 ms and no boundary error over one second. Qualification requires all three episodes to finish without human intervention or episode-specific engineering and to meet the sampled content and timing criteria. These samples can reject a poor process and support a bounded claim about tested material; they cannot prove perfection across every unannotated minute. A full independent bilingual watch of at least one completed episode would be the next evidence needed for a stronger whole-episode accuracy claim.

When independent bilingual evaluation is unavailable, report structural completion and provisional findings separately and mark trusted accuracy **unmeasured**. Do not turn model agreement, a passing gate, or the agent's own judgments into a trusted error rate.

## Reproduction

1. Run `python3 scripts/test-production-paths.py` and the portable suite in `README.md`.
2. Verify `qualification/freeze.json`, then run `qualification-runner.py start` for each listed case with only its allowed inputs. Save output outside the repository.
3. Give a fresh agent `qualification/AGENT-PROMPT.md` with those normal paths. Keep its original task transcript and run event ledger.
4. Run `qualification-runner.py status` and preserve every final or partial candidate, source report, decision, ASR receipt, render report, dry release report, and usage receipt.
5. Perform the independent evaluation above. Publish the complete cohort table, including failures, interventions, runtime, cost, and unmeasured fields. Never delete a failed case from the denominator.
