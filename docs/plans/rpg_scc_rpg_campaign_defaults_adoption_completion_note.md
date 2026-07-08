# RPG Settings Follow-up Completion Note — Campaign Default Adoption

Central Settings defaults now seed new RPG campaign creation.

Implementation PR: #1254
Implementation branch: `scc-adopt-rpg-defaults`
Implementation head SHA checked: `464117d30d1900f6901fb6f5719ba3662ff396d4`
Implementation merge SHA / source-of-truth SHA: `f83aa0efa5b2d10a182fd6293b2c6caaa4f1ad6f`

Required checks observed passing on the exact implementation head SHA:

- RPG Phase 0 architecture compliance — passed
- RPG deterministic PR gates — passed

## Completed scope

- Added a typed adapter from central RPG settings into the campaign wizard's existing option vocabulary.
- Mapped difficulty, world activity, economy pressure, and combat lethality defaults without changing deterministic request construction.
- Mapped autosave, companions, permadeath, grounding validation, background soft audit, narration, image generation, TTS, and STT defaults.
- Applied central defaults once when the new-campaign wizard loads.
- Preserved explicit user interaction as authoritative when the settings profile resolves after the user begins editing.
- Preserved `buildRpgNewGameRequest` as the owner of deterministic campaign request construction.
- Added focused mapping and DOM-application unit coverage.

## Safety and authority boundaries

- Existing campaigns are not mutated.
- RPG turn state and simulation truth are unchanged.
- Central settings seed new-campaign controls only.
- Explicit wizard selections override central defaults.
- The existing campaign wizard implementation remains responsible for validation, progress, and request submission.

## Follow-up state

Direct central-default adoption is now present for Image Generation, Speech Input, Voice Studio, and RPG campaign creation. Remaining Settings follow-up work should focus on running-app smoke evidence and end-to-end persistence coverage rather than additional default adapters.
