# Reusable production agent prompt

Produce Turkish and English subtitles for ONE user-selected video. Do not choose an episode from assumptions about viewing history. Work directly; do not delegate. Follow [PROCESS.md](../../PROCESS.md), the authoritative production sequence, and use [WORKBENCH.md](WORKBENCH.md) for commands. Keep media, references, drafts, evidence, and checkpoints in the private run directory; preserve installed sidecars. Verify episode-specific provider authorization and conservative remaining cost before any paid call or upload; otherwise request one consolidated allowance. This prompt grants no provider or installation permission.

Select one initial recognizer profile, `whisper-turbo` or `gemini-five-minute`, and record its actual settings. Reuse existing independently generated recognition with matching media/settings receipts. Gemini means overlapping five-minute requests, not the old single-request full-audio observation. Do not start a recognizer survey or both full transcriptions by default.

Complete Turkish wording and usable speech timing before bulk English. Review coherent dialogue sections, including accepted lines, and batch source edits/alignment. Use focused recognition for words, VAD for activity/boundaries, separation only for relevant masking, and timestamped frames for visual context. Choose authorized hosted audio review when local evidence is inadequate or inefficient. Do not claim to hear audio from transcripts or images. Resolve seams from evidence; midpoint selection does not settle them. Record material pending work honestly; indistinct-speech captions are only for genuinely unrecoverable speech.

Register applicable saved independent evidence in the existing source case. Before readiness, inspect it beside the candidate and surrounding dialogue, including speech detected inside subtitle gaps. Resolve material contradictions explicitly as recognition artifacts, supported alternatives, or unresolved questions. A focused rejection cannot silently coexist with approval. Do not decide by majority vote or require unanimous agreement.

Save a source-hash-bound Turkish-ready checkpoint using that current case after coverage, material repairs, timing, and substantive dialogue review are complete. A frozen or budget-limited snapshot is not ready. If source work is incomplete, report the specific remaining evidence need before advancing to English. Do not refresh English or render each scene during initial source production.

After Turkish ready, generate English with DeepSeek Flash's concurrent contextual batches under applicable authorization. Keep provider drafts distinct from agent-authored text. Review all English against current Turkish and nearby dialogue, including apparently clean cues. Save English-only corrections in the existing translation checkpoint so re-export retains them. Reuse valid English when resuming. A late source error reopens its affected interval and nearby English only.

Finish display grouping, line breaks, layout, whole-candidate checks, and rendering at final checkpoints. Keep source links through separate English display cues. Report actual completed/incomplete stages, elapsed time, substantive repairs, usage/cost, and remaining limitations. Synthetic tests prove software behavior, not subtitle accuracy. Installation requires separate authorization and playback observation.

Keep OpenSubtitles and reference-derived corrections outside production until both generated final tracks are saved. Any subsequent reference comparison must use that preserved pair; reference-assisted corrections belong in a separate version. Do not run another model comparison, experiment campaign, or additional episode.

Inputs:

- Video: `<VIDEO_PATH>`
- Private run directory: `<RUN_DIRECTORY>`
- Existing independent Turkish draft/receipts: `<DRAFT_PATH_OR_NONE>`
- Primary profile: `<whisper-turbo|gemini-five-minute>`
- Applicable provider authorization: `<AUTHORIZATION_PATH_OR_NONE>`
