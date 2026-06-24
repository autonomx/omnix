# RPG AI RPG Parity Phase 28 — Environmental Narration

Phase 28 adds a deterministic environmental narration trigger and scene-introduction contract system.

## Landed

- Added `src/app/rpg/environmental_narration_runtime.py`.
- Detects scene-introduction triggers for new games, location/region changes, time/weather changes, major event changes, scene activity transitions, perceived world changes, and changed return visits.
- Builds a scene-introduction contract with atmospheric description, current activity summary, notable observations, and player awareness cues.
- Assembles sensory and world-context inputs from simulation state: sights, sounds, smells, physical feel, emotional tone, location, region, time, season, weather, activity, events, factions, NPC activity, recent actions, consequences, economy, hazards, conflicts, and celebrations.
- Adds an autoplay wrapper fragment to attach environmental narration metadata to transcript rows and summaries.
- Adds tests for new-location narration, changed return visits, and missing-trigger/context validation.

## Verification

Pending GitHub Actions for the Phase 28 PR.
