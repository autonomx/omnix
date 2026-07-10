# Character live-avatar phases

Scope: Omnix Chat live calls only. RPG presentation and RPG image generation are intentionally unchanged.

## Phase 1 — avatar packs and audio-envelope mouth movement

- Each character may own a versioned avatar pack stored independently from identity, voice, memory, and transcript data.
- Packs reference browser-safe shared image assets rather than local file paths.
- The live-call runtime resolves the selected character's pack server-side.
- The browser monitors the same streaming PCM16 TTS response used by live playback and maps short audio windows to `closed`, `small`, `medium`, and `wide` mouth frames.
- Calls without a pack retain the existing Live Voice orb.
- The pack contract already reserves optional blink, expression, outfit, and background references for Phase 2.
- The renderer contract reserves `viseme` mode while Phase 1 defaults to `audio_envelope`.

## Phase 2 — generation and presentation

Planned on the same branch after Phase 1 gates pass:

- character-page avatar preview and generation controls;
- canonical portrait plus mouth, blink, expression, outfit, and background jobs through Image Generation;
- listening, thinking, speaking, and idle presentation states;
- governed cloned-voice discovery and character-profile backfill.

## Phase 3 — timed visemes

Planned after Phase 2 gates pass:

- timed viseme events aligned to streamed TTS chunks;
- six or more mouth-shape mappings with audio-envelope fallback;
- optional rig-renderer contract without requiring RPG integration.
