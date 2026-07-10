# Character live-avatar phases

Scope: Omnix Chat live calls only. RPG presentation and RPG image generation are intentionally unchanged.

## Phase 1 — avatar packs and audio-envelope mouth movement

Complete on the staged branch and verified by exact-head GitHub Actions.

- Each character may own a versioned avatar pack stored independently from identity, voice, memory, and transcript data.
- Packs reference browser-safe shared image assets rather than local file paths.
- The live-call runtime resolves the selected character's pack server-side.
- The browser monitors the same streaming PCM16 TTS response used by live playback and maps short audio windows to `closed`, `small`, `medium`, and `wide` mouth frames.
- Calls without a pack retain the existing Live Voice orb.

## Phase 2 — generation, cloned-voice backfill, and presentation

Implemented; awaiting its exact-head gates before Phase 3 begins.

- The Characters page can queue a canonical portrait and automatically fan out locked-reference image jobs for mouth, blink, listening, thinking, and happy frames.
- Optional alternate outfit and background prompts produce independently linked variants.
- Generation batches are durable in the Character SQLite database. Polling reconciles Image Generation jobs and finalizes the avatar pack only after all required assets exist.
- The Characters page previews completed packs, reports generation progress, and can regenerate a selected character.
- Governed cloned-voice discovery creates one character profile per usable `voice_profile` asset and queues missing avatar packs.
- Voice profiles are included only when consent is granted for both `character` and `live_call`; default/reference/test assets are skipped unless explicitly requested.
- Generated prompts require original fictional designs and prohibit depicting or imitating a real public person.
- Live presentation adds idle breathing, listening, thinking, speaking, error, and blink states while preserving the Phase 1 audio-envelope mouth fallback.

Actual image inference remains local: the backfill and generation actions queue jobs against the configured Omnix Image Generation provider when the application is running.

## Phase 3 — timed visemes

Planned after Phase 2 gates pass:

- timed viseme events aligned to streamed TTS chunks;
- six or more mouth-shape mappings with audio-envelope fallback;
- optional rig-renderer contract without requiring RPG integration.
