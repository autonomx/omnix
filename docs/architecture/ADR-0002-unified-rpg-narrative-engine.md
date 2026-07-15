# ADR-0002: Unified RPG Narrative Engine and Legacy Presentation Replacement

- **Status:** Accepted for implementation
- **Date:** 2026-07-13
- **Decision owners:** Omnix maintainers
- **Base:** `main`
- **Related:** `ADR-0001-centralized-postgresql-authority.md`

## Context

RPG presentation is currently split across compact dialogue, first-call visible responses, runtime narration, world-scene narration, environmental narration contracts, deferred narration, deterministic fallbacks, canonical post-processing, and several independently renderable response fields. Route selection changes writing quality, grounding behavior, response shape, and publication ownership.

The existing strict response pipeline contains useful contracts and validators, but it still invokes legacy prose generators and adapts legacy payloads after generation. It is therefore a migration source, not the final architecture.

## Decision

Omnix will build an isolated `app.rpg.narrative_engine` package as the sole future owner of RPG presentation orchestration.

Every player-facing interaction will produce exactly one `TurnPresentationRequest`, one ordered narrative plan, and one persisted `CanonicalNarrativeResponse`. The UI and all downstream consumers will render ordered canonical blocks. Legacy fields may be projected at API boundaries during migration, but may not be independently generated, persisted, repaired, or rendered.

The new package may reuse or extract deterministic scene-change logic, evidence retrieval, NPC profiles, memories, grounding rules, claim validation, agency validation, provider adapters, and deterministic fallbacks. It may not import legacy generation modules.

## Required dependency direction

Legacy code may call the Narrative Engine during migration. The Narrative Engine may never call legacy generation code.

Prohibited imports include:

- `app.rpg.ai.compact_dialogue`
- `app.rpg.ai.world_scene_narrator`
- `app.rpg.narration.runtime_narration_legacy`
- `app.rpg.session.first_call_dialogue`
- `app.rpg.response_generation.legacy_bridge`

An architecture test will enforce this boundary.

## Canonical contracts

The replacement architecture defines:

- `TurnPresentationRequest`
- `EvidenceRecord`
- `NarrativeBeat`
- `NarrativeBlock`
- `CanonicalNarrativeResponse`
- authority, visibility, lifetime, significance, profile, and delivery enums

Blocks preserve explicit planner sequence. Fast, immersive, and cinematic are profiles of the same engine. Blocking and deferred are delivery modes for the same approved response, not different generation paths.

## Truth and agency

Simulation remains authoritative for mechanics and durable state. Narrative generation cannot change location, inventory, currency, health, combat outcomes, XP, quests, relationships, time, weather, discoveries, or persistent world objects.

Every factual claim must reference permitted evidence. Authority and visibility are separate dimensions. NPC belief, faction doctrine, rumor, disputed claims, and secret canon must not silently become objective canon.

Knowledge filtering occurs before planning and writing.

## Environmental narration and dialogue

Environmental narration is a deterministic scene-change signal and required-beat input, not an independent prose system.

NPC dialogue is an ordered block type, not an alternate publisher. Compact dialogue becomes a low-latency presentation profile using the same request, evidence, planning, validation, response, and renderer contracts.

## Persistence

PostgreSQL is authoritative for revisioned Campaign Bible state and canonical narrative responses. JSON and JSONL remain valid for exports, fixtures, diagnostics, reports, and migration input only.

The Campaign Bible begins as a revisioned JSONB aggregate containing documents, entities, facts, relationships, knowledge rules, retrieval cards, generation provenance, consistency reports, and completeness records.

## Migration

1. Build contracts, renderer, evidence broker, planner, writer, validator, response repository, and delivery coordinator in isolation.
2. Run shadow generation against real turns.
3. Cut over direct dialogue first.
4. Cut over environmental, observation, travel, stateful actions, services, commerce, combat, and major beats.
5. Add Campaign Bible MVP, World Forge, and bounded Hermes research.
6. Move UI, TTS, transcript, journal, recap, reports, and replay to canonical blocks.
7. Delete legacy presentation ownership after production call counts reach zero and release gates pass.

## Non-negotiable invariants

1. Every interaction creates one presentation request.
2. Every completed presentation has one response ID and content hash.
3. Blocks preserve planner sequence.
4. Every factual claim references permitted evidence.
5. Knowledge filtering precedes planning and writing.
6. Narration cannot mutate authoritative simulation state.
7. Direct dialogue cannot return through an alternate publisher.
8. Environmental changes become required beats.
9. Blocking and deferred delivery preserve identical canonical meaning.
10. UI, TTS, transcript, journal, recap, and reports consume the same blocks.
11. Compatibility fields are projections only.
12. The Narrative Engine cannot import legacy generation modules.
13. PostgreSQL owns mutable Campaign Bible authority.
14. Legacy generation is deleted after verified zero production use.

## Rejected alternatives

### Continue expanding the legacy-backed strict pipeline

Rejected because compatibility generation, legacy payload parsing, rollout duality, and alternate publishers would remain embedded in the final architecture.

### Delete all existing logic before replacement

Rejected because deterministic simulation, retrieval, grounding, validation, memory, and fallback logic remain valuable and should be extracted or reused.

### Authoritative filesystem Campaign Bible

Rejected because it conflicts with ADR-0001. Files remain export and diagnostic formats only.

## Consequences

The migration temporarily maintains old and new systems in parallel, but the dependency direction is one-way and deletion is an explicit completion requirement. The replacement adds implementation cost now in exchange for one coherent presentation model, stronger grounding, richer ordered responses, deterministic delivery, and substantially simpler long-term maintenance.
