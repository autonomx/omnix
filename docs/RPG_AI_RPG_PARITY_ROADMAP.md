# RPG AI RPG Parity Roadmap

This roadmap captures the feature plan for bringing the Omnix RPG closer to the best player-facing capabilities of `envy-ai/ai_rpg` while preserving the Omnix RPG rule that the deterministic simulation owns truth and the LLM only interprets, narrates, summarizes, and presents grounded state.

## North Star

Build a fast, replayable, simulation-authoritative AI RPG where:

- the simulation owns authoritative game state;
- the LLM may classify intent, produce flavor, summarize memory, and polish presentation;
- every inventory, currency, combat, quest, travel, relationship, and save/load change is represented by a deterministic state delta;
- long campaigns can be replayed and regression-tested even if narration wording changes.

## Implementation Rules

1. Every feature must keep simulation state deterministic.
2. LLM output must never directly mutate authoritative state.
3. LLM-derived suggestions must be treated as proposals until a simulation resolver accepts them.
4. New browser-facing work must use the shared `src/apps/web` infrastructure and typed backend APIs.
5. Each phase should land as a narrow, auditable PR with tests and a roadmap status update.
6. Reports and debug surfaces should expose enough metadata to audit what happened without relying on hidden prompts.

## Phase 1 — Grounded Narration Quality Pass

Goal: Make RPG responses less repetitive, more characterful, and easier to audit without weakening grounding.

Features:

- post-narration repetition detector;
- repeated phrase and sentence-opening checks;
- configurable banned/low-value phrase policy;
- recent transcript overlap checks;
- safe rewrite request contract that preserves state facts;
- quality report fields for repetition, slop phrases, rewrite recommendation, and grounding follow-up.

Acceptance criteria:

- deterministic simulation output is unchanged;
- narration quality evaluation is pure and testable;
- a rewrite may be requested only as a presentation-layer action;
- the report records why a rewrite was or was not requested.

## Phase 2 — Prompt and Model Profiles

Goal: Create per-subsystem prompt/model profiles so cheap deterministic tasks can use fast models and high-value prose can use stronger models.

Features:

- prompt profile registry;
- per-task provider/model override;
- temperature, token, timeout, retry, streaming, and background/blocking settings;
- debug viewer payload for prompt profile, model, latency, raw output, and validated output.

Acceptance criteria:

- intent classification and narration can use different model profiles;
- prompt profile choice is visible in reports;
- failed background profile jobs cannot block deterministic turn resolution.

## Phase 3 — Map, Region, and Location Stub System

Goal: Add a usable graph-map and location-stub workflow while keeping travel deterministic.

Features:

- world/region/location graph model;
- lightweight undiscovered or unexpanded location stubs;
- known exits, blocked routes, danger/service markers, and discovered-but-unvisited nodes;
- deterministic instant travel for known safe routes;
- dev/editor helpers for creating nodes and exits.

Acceptance criteria:

- map state survives save/load;
- safe discovered travel can resolve without a heavy LLM call;
- new locations are expanded from deterministic seed/context, not freeform state mutation.

## Phase 4 — NPC Disposition and Relationship Axes

Goal: Make NPC relationships explicit, persistent, mechanically meaningful, and deterministic.

Features:

- trust, respect, friendship, fear, loyalty, suspicion, romantic interest, debt, and resentment axes;
- deterministic relationship deltas from resolved events;
- NPC-facing compact memory summaries;
- relationship effects on prices, rumors, companion eligibility, checks, betrayal risk, and quest branching.

Acceptance criteria:

- relationship deltas are shown in turn deltas;
- save/load preserves dispositions;
- NPC dialogue reflects relationship state without inventing unsupported events.

## Phase 5 — NPC Schedules and Offscreen Activity

Goal: Make the world continue moving when the player is elsewhere.

Features:

- deterministic NPC schedules;
- offscreen ticks at time checkpoints;
- hidden world log separate from player-known events;
- discovery surfaces through rumors, investigation, witnesses, scouting, party reports, letters, and visible changes.

Acceptance criteria:

- offscreen events derive from seed/time/state;
- hidden events do not leak into player knowledge;
- reports distinguish hidden, discovered, local, and global events.

## Phase 6 — Conversation and Social Scene Upgrade

Goal: Make social scenes feel like living scenes rather than one-line command responses.

Features:

- directed, ambient, group, argument, negotiation, interrogation, and party-banter thread kinds;
- NPC turn-taking gates and ambient budgets;
- deterministic memory hooks for promises, threats, secrets, deals, insults, and clues;
- social checks using charisma, intimidation, deception, insight, reputation, faction standing, and disposition.

Acceptance criteria:

- NPCs do not spam every turn;
- social outcomes are deterministic deltas;
- conversations can be interrupted, redirected, or left cleanly.

## Phase 7 — Economy and Service Depth

Goal: Make shops, inns, jobs, scarcity, and money feel real.

Features:

- canonical gold/silver/copper currency;
- merchant stock, prices, scarcity, restock cadence, and relationship modifiers;
- inn services for room, meal, rumors, stable, storage, recovery, NPC meetings, and overheard conversations;
- pay enforcement with explicit exceptions for persuasion, credit, sponsorship, theft, comping, or quest authorization;
- local job templates.

Acceptance criteria:

- services cannot be consumed without payment or an explicit exception;
- prices vary deterministically;
- 100-turn coverage includes at least one service transaction.

## Phase 8 — Combat Lifecycle Expansion

Goal: Turn combat into a complete deterministic RPG loop.

Features:

- full initiative order;
- deterministic enemy AI policies;
- defeat outcomes including death, unconsciousness, capture, robbery, rescue, forced retreat, and reputation loss;
- XP only from kills, quests, or explicit milestone rewards;
- usage-driven skill growth;
- combat narration contract that can describe only resolved combat facts.

Acceptance criteria:

- no attacking outside combat unless combat starts;
- no death, loot, or XP unless simulation state allows it;
- a 100-turn run can include a complete combat lifecycle.

## Phase 9 — Quest, Journal, and Chronicle Upgrade

Goal: Make the player always know what happened, what changed, and what can be done next.

Features:

- quest state machine for unknown, rumored, offered, accepted, advanced, blocked, completed, failed, and expired states;
- objective journal with clues, NPCs, locations, deadlines, reward, and risk;
- chronicle sections for what happened, what was learned, what changed, unresolved threads, and suggested next actions;
- rumor-to-lead-to-quest pipeline.

Acceptance criteria:

- journal updates only from resolved state events;
- recaps do not invent facts;
- suggested actions are grounded in current state.

## Phase 10 — Party and Companion System

Goal: Make companions mechanically and narratively meaningful.

Features:

- deterministic companion eligibility;
- roles such as fighter, healer, scout, merchant, guide, scholar, lockpick, and face;
- companion actions for comments, checks, combat, warnings, memory reveals, objections, and leaving;
- loyalty, morale, fear, debt, and personal-goal tracking.

Acceptance criteria:

- companion join/leave is deterministic;
- party composition affects combat, social, and travel checks;
- companion dialogue respects memory and personality.

## Phase 11 — Image, Portrait, and Scene Generation

Goal: Add optional visuals without blocking gameplay.

Features:

- NPC, party, enemy, and quest-giver portraits;
- scene images for locations, quest beats, combat starts, boss reveals, and faction events;
- image prompt contract grounded in known location/NPC/time/weather/object state;
- background image queue by default.

Acceptance criteria:

- image generation never blocks core turn resolution;
- generated image prompts are visible in debug/report surfaces;
- portraits persist by NPC ID.

## Phase 12 — Performance Sprint

Goal: Push human-equivalent blocking turns toward sub-5 seconds.

Features:

- blocking-path audit for must-block, stream, defer, batch, cache, and skip work;
- deterministic fast responses for look, inventory, stats, map, journal, known travel, known purchases, and known room rental;
- background narration polish, memory summary, journal recap, image prompt, offscreen events, and soft audits;
- compact current-turn-first prompts and entity cards.

Acceptance criteria:

- 20-turn benchmark shows lower blocking average;
- known simple actions complete without heavy LLM calls;
- reports include latency by subsystem.

## Phase 13 — Save/Load, Replay, and Regression Gates

Goal: Make deterministic reliability non-negotiable.

Features:

- snapshots for world, player, party, NPC, quest, map, inventory, combat, memory, RNG seed, and counters;
- replay state hashing;
- scripted regression scenarios for economy, room rental, travel, combat, companion recruitment, rumors, quest steps, and save/load boundaries;
- CI gates for replay, grounding, no unsupported state claims, no direct LLM state mutation, and 100-turn smoke coverage.

Acceptance criteria:

- replay state hash matches for same seed/actions;
- save/load does not duplicate events;
- CI fails if narration claims unsupported state.

## Phase 14 — Modding, Lorebook, and World Packs

Goal: Let users define worlds without editing code.

Features:

- structured lorebook entries;
- world packs for regions, locations, factions, NPC templates, item catalogs, encounter tables, quest seeds, tone rules, and style rules;
- mod overlays for items, services, NPCs, factions, quest hooks, prompt style, and image style;
- schema validation before loading.

Acceptance criteria:

- invalid packs fail safely;
- mods cannot bypass simulation authority;
- lore can influence narration but not directly mutate state.

## Phase 15 — World Director and Long Campaign Pacing

Goal: Make 100-turn and 1000-turn campaigns feel like coherent stories.

Features:

- director state for active arcs, threats, faction tension, player goals, repetition, pacing pressure, danger, and downtime;
- arc progression for escalation, branching, pausing, failure, resolution, and consequences;
- loop detection for location/NPC/action/no-progress loops;
- grounded suggested action engine.

Acceptance criteria:

- 100-turn campaigns reach multiple meaningful beats;
- autoplay does not stall in tavern/shop loops;
- suggested actions are always valid in current state.

## Phase 16 — Integration Hardening and Readiness Audit

Goal: Compose the Phase 1-15 deterministic foundations into one turn-level audit payload that highlights runtime wiring readiness without letting presentation change state.

Features:

- phase 1 narration quality plus safe rewrite contract output;
- phase 2 prompt profile debug payload and registry validation;
- phase 12 fast-action and blocking/deferred path audit;
- phase 13 stricter replay snapshot validation for full runtime state groups;
- phase 14 nested mod overlay mutation guardrails;
- phase 15 director suggestion/readiness audit.

Acceptance criteria:

- the integration report is pure and side-effect free;
- rewrite requests remain presentation-only;
- replay snapshots require world, player, party, NPC, quest, map, inventory, combat, memory, seed, and counters;
- nested mod overlays cannot hide forbidden state-mutation keys;
- tests prove several phase foundations compose in one stable report payload.

## Phase 17 — Runtime Integration Report Surface

Goal: Wire the Phase 16 audit into resolved turn/autoplay report surfaces so integration readiness is visible in real transcript and summary artifacts.

Features:

- resolved-turn integration report adapter;
- transcript-row integration report attachment;
- autoplay summary aggregation of ready turns and issue counts;
- persisted autoplay summary/transcript JSON decoration through the fragment loader;
- stale verification documentation cleanup.

Acceptance criteria:

- report decoration happens after simulation turn resolution;
- integration reports do not mutate authoritative state;
- autoplay summaries include per-turn runtime integration issues and aggregate counts;
- tests prove report payloads and persisted artifacts include the Phase 17 source marker.

## Status Log

- 2026-06-24: Roadmap created. Phase 1 implementation begins with pure narration quality policy/report helpers and regression tests.
- 2026-06-24: Phase 16 integration hardening adds a composite readiness report, stricter replay snapshot validation, nested world-pack overlay guards, and integration tests.
- 2026-06-24: Phase 17 begins runtime hardening by wiring the integration audit into resolved turn/autoplay report surfaces and persisted JSON artifacts.
