# Character live-avatar phases

Scope: Omnix Chat live calls only. RPG presentation and RPG image generation are intentionally unchanged.

## Phase 1 — avatar packs and audio-envelope mouth movement

Complete and verified by exact-head GitHub Actions.

- Each character may own a versioned avatar pack stored independently from identity, voice, memory, and transcript data.
- Packs reference browser-safe shared image assets rather than local file paths.
- The live-call runtime resolves the selected character's pack server-side.
- The browser monitors the same streaming PCM16 TTS response used by live playback and maps short audio windows to `closed`, `small`, `medium`, and `wide` mouth frames.
- Calls without a pack retain the existing Live Voice orb.

## Phase 2 — generation, cloned-voice backfill, and presentation

Complete and verified by exact-head GitHub Actions.

- The Characters page can queue a canonical portrait and automatically fan out locked-reference image jobs for mouth, blink, listening, thinking, and happy frames.
- Optional alternate outfit and background prompts produce independently linked variants.
- Generation batches are durable in the Character SQLite database. Polling reconciles Image Generation jobs and finalizes the avatar pack only after all required assets exist.
- The Characters page previews completed packs, reports generation progress, and can regenerate a selected character.
- Governed cloned-voice discovery creates one character profile per usable `voice_profile` asset and queues missing avatar packs.
- Voice profiles are included only when consent is granted for both `character` and `live_call`; default/reference/test assets are skipped unless explicitly requested.
- Generated prompts require original fictional designs and prohibit depicting or imitating a real public person.
- Live presentation adds idle breathing, listening, thinking, speaking, error, and blink states while preserving the Phase 1 audio-envelope mouth fallback.

## Phase 3 — timed visemes and renderer extension

Implemented; the final exact-head verification is the release gate.

- Existing sprite packs can generate nine locked-reference visual mouth shapes: `A`, `E`, `O`, `U`, `MBP`, `FV`, `L`, `WQ`, and `other`, with `silence` mapped to the closed frame.
- Viseme generation is durable and promotes the pack to `render_mode=viseme` only after every required image asset is available.
- The browser derives a deterministic visual sequence from the exact outgoing TTS text and schedules it against the duration of each streamed PCM chunk.
- Native future TTS events shaped as `{type: "viseme", viseme, start_ms, duration_ms}` take precedence when available.
- When a precise visual shape is absent, the renderer maps that viseme to the Phase 1 closed/small/medium/wide frames. If timing is unavailable, the Phase 1 audio-envelope path remains active.
- The pack contract supports `sprite`, `live2d`, and `rive` renderers. Rigged packs require a governed shared rig asset and receive `omnix:character-rig-viseme` browser events; the built-in sprite renderer remains the default.
- The Characters page automatically follows a newly completed base avatar with precise viseme generation and also exposes a manual regenerate action.
- Cloned-voice backfill upgrades each generated character to precise visemes while the Characters page remains open.

## Phase 4 — selectable Live2D avatars

Implemented behind explicit third-party license acceptance.

- The Characters page exposes separate **Generated avatar** and **Live2D avatar** workflows. Selecting Live2D does not remove or overwrite the character's generated image assets.
- The catalog includes Niziiro Mao (PRO) and Shizuku (PRO) from Open-LLM-VTuber, plus the official Haru, Hiyori Momose (PRO), Epsilon (PRO), Chitose, Koharu, Haruto, Tororo, and Hijiki sample runtimes.
- Omnix does not vendor the Live2D Cubism Core or sample model binaries. The user must accept the Live2D runtime and sample-model terms before Omnix downloads pinned files from their original projects.
- Downloaded runtime and model files are stored under `resources/data/character_live2d`, registered as governed shared assets, and served by local-only API routes after installation.
- Character avatar packs select the installed model through `renderer=live2d`, `render_mode=viseme`, and a governed `rig_asset_id`.
- Character live calls mount a PixiJS/Live2D canvas in the existing avatar stage. The same timed viseme stream used by sprite packs drives common Cubism mouth-open and mouth-form parameters while the model retains its own idle motion, physics, blink, and pose behavior.
- Disabling Live2D restores the character's previous generated avatar pack when one existed; otherwise the live call returns to the Voice orb.
- Model and runtime revisions are pinned so a later upstream change cannot silently alter an installed character. Official sample ZIPs are verified against catalogued SHA-256 hashes and only their referenced runtime files are extracted; Cubism authoring files are not retained.

### Licensing boundary

Open-LLM-VTuber's source code license does not replace the separate licenses attached to Live2D Cubism Core and its sample models. Omnix therefore stores source, revision, and license metadata with each installed rig and requires two explicit confirmations before download. Teams should review the linked Live2D terms for their organization size and intended commercial use.

## Running the cloned-voice image backfill

Actual image inference remains local. GitHub Actions verifies orchestration, persistence, UI behavior, and fallbacks but does not have access to the user's runtime voice files, image model, or GPU.

With the Omnix gateway and Image Generation worker running:

```bash
python scripts/backfill_character_avatars.py
```

The command asks the running gateway to discover its real governed `voice_profile` assets, creates missing Character profiles, queues canonical and presentation images, waits for those packs, then queues precise viseme frames. It excludes reference/default/test profiles unless `--include-reference-profiles` is supplied. The same workflow is available from **Characters → Create characters from cloned voices**.
