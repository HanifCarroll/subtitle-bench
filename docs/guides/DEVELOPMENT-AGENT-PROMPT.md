# Reusable production agent prompt

Produce Turkish and English subtitles for this video. Work directly; do not delegate. Follow [PROCESS.md](../../PROCESS.md), the authoritative production sequence, and use [WORKBENCH.md](WORKBENCH.md) for commands. Keep media, references, drafts, evidence, and checkpoints in the private run directory; preserve installed sidecars.

Select one initial recognizer profile, `whisper-turbo` or `gemini-five-minute`, and record its actual settings. Reuse existing independently generated recognition with matching media/settings receipts. Gemini means overlapping five-minute requests, not the old single-request full-audio observation. Do not start a recognizer survey or both full transcriptions by default.

Complete Turkish wording and usable speech timing before bulk English. Review coherent dialogue sections, including accepted lines, and batch source edits/alignment. Use focused recognition for words, VAD for activity/boundaries, separation only for relevant masking, and timestamped frames for visual context. Choose authorized hosted audio review when local evidence is inadequate or inefficient. Do not claim to hear audio from transcripts or images. Resolve seams from evidence; midpoint selection does not settle them. Record material pending work honestly; indistinct-speech captions are only for genuinely unrecoverable speech.

Save a source-hash-bound Turkish-ready checkpoint after coverage, material repairs, timing, and substantive dialogue review are complete. A frozen or budget-limited snapshot is not ready. If source work is incomplete, report that stage as incomplete before advancing to English. Do not refresh English or render each scene during initial source production.

Generate English in bulk using the selected path: DeepSeek Flash with agent review/correction, or direct agent translation with a final contextual check. Use identical context and terminology in a comparison. Keep provider drafts distinct from agent-authored text. Review all English against current Turkish and nearby dialogue, including apparently clean cues. Save English-only corrections in the existing translation checkpoint so re-export retains them. A late source error reopens its affected interval and nearby English only.

Finish display grouping, line breaks, layout, whole-candidate checks, and rendering at final checkpoints. Keep source links through separate English display cues. Report actual completed/incomplete stages, elapsed time, substantive repairs, usage/cost, and remaining limitations. Synthetic tests prove software behavior, not subtitle accuracy. Installation requires separate authorization and playback observation.

For the small translation comparison, use one settled 10–15-minute section. Save independent outputs before opening an English reference; accept equivalent wording and distinguish reference problems. Stop after the comparison and provisional English-path decision. Do not start another full episode, qualification campaign, or broad model comparison.

Inputs:

- Video: `<VIDEO_PATH>`
- Private run directory: `<RUN_DIRECTORY>`
- Existing independent Turkish draft/receipts: `<DRAFT_PATH_OR_NONE>`
- Primary profile: `<whisper-turbo|gemini-five-minute>`
- English path: `<deepseek|agent|small-comparison>` (provisional preference: DeepSeek with approved calls and mandatory agent review; direct agent otherwise)
- Applicable provider authorization: `<AUTHORIZATION_PATH_OR_NONE>`
