# RPG AI RPG Parity Phase 29 — Environmental Scene Intro Runtime

Phase 29 wires the Phase 28 environmental narration contract into narrator-facing scene-introduction request metadata.

## Landed

- Added `src/app/rpg/env_scene_intro.py`.
- Converts environmental narration triggers into a narrator-facing `environmental_scene_intro` task.
- Carries the Phase 28 scene-introduction contract and trigger reasons forward for narration.
- Adds an autoplay wrapper fragment that decorates transcript rows with scene-intro requests.
- Adds tests for triggered and non-triggered scene-introduction requests.

## Verification

Pending GitHub Actions for the Phase 29 PR.
