# RPG Mode UI Redesign Implementation Roadmap

## Purpose

This roadmap turns the approved RPG mode redesign direction into a sequence of narrow, auditable implementation slices. The target UI is a gameplay-first RPG control surface rather than the current job/form dashboard. It should preserve the deterministic simulation boundary while giving the player a real game interface for story, character state, party, inventory, quests, world state, combat, jobs, reports, and checkpoints.

The design direction is based on the proposed full-screen RPG workstation mockup: left player/party/quest rail, center story and action composer, center-lower journal/history panels, right world/map/jobs rail, and bottom inventory/ability hotbar.

## Non-negotiable implementation principles

1. **Simulation remains authoritative.** UI renders state and submits intents; it must not invent canonical world, inventory, combat, currency, quest, or party state.
2. **Narration is presentation.** LLM text can explain and embellish, but state-changing claims must come from deterministic turn results.
3. **Build mock-first, then wire live state.** Layout and component contracts should be validated with fixtures before replacing old RPG surfaces.
4. **Keep slices narrow.** Each implementation PR should add one surface or one integration layer, with docs/tests updated in the same slice.
5. **Do not block the player on background work.** RPG jobs, narration, reports, and image generation should appear as async status surfaces without freezing the main action loop.
6. **Readable at a glance.** Every critical state should have a compact summary and a drill-down path.
7. **Keyboard and accessibility safe.** The action composer, tabs, quick actions, menus, and panels must be navigable without a mouse.

## Target screen architecture

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ Top app shell: Omnix logo, Chat / RPG / Voice / Image tabs, engine status    │
├───────────────┬──────────────────────────────────────────────┬───────────────┤
│ Player rail   │ Main adventure surface                       │ World rail    │
│ - hero        │ - location header                             │ - map         │
│ - vitals      │ - story / dialogue transcript                 │ - world state │
│ - XP/currency │ - recent events                               │ - encounter   │
│ - gear        │ - action composer + quick actions             │ - NPCs        │
│ - party       ├──────────────────────────────────────────────┤ - jobs        │
│ - quests      │ Journal / dialogue log / turn history         │ - reports     │
├───────────────┴──────────────────────────────────────────────┴───────────────┤
│ Inventory / abilities / hotbar + save/export/settings status                 │
└──────────────────────────────────────────────────────────────────────────────┘
```

## Phase 0 — Approval and repository orientation

**Goal:** Lock the design direction and identify the existing RPG UI entry points before code changes.

Deliverables:

- Keep `docs/plans/rpg_mode_ui_feature_component_inventory.md` as the feature/component source of truth.
- Add this roadmap as the implementation source of truth.
- Capture the approved mockup direction in the roadmap or follow-up design notes.
- Locate the current RPG route, stylesheet, job cards, session selector, and API calls.
- Identify existing state payloads for sessions, turns, jobs, reports, checkpoints, and autoplay.

Acceptance gate:

- The team can point to one approved design direction and one ordered implementation plan.
- No runtime behavior changes yet.

## Phase 1 — UI state contracts and fixture layer

**Goal:** Define the normalized client-side model the redesigned RPG UI will render.

Work items:

- Create a UI-facing RPG state adapter that normalizes backend/session responses into stable view models.
- Add fixture data for a representative scene: hero, party, quests, inventory, location, world state, NPC relationships, jobs, reports, and checkpoint status.
- Add type/shape guards if the frontend stack supports them, or lightweight validation helpers if it is plain JavaScript.
- Add empty/loading/error states for every major panel.

Primary view models:

| View model | Purpose |
| --- | --- |
| `RpgHeroView` | Character name, class, level, XP, HP, stamina, mana, gold, renown, avatar. |
| `RpgPartyView` | Companions, roles, status, HP, relationship summary. |
| `RpgQuestView` | Active quests, objective text, progress, priority. |
| `RpgSceneView` | Location, tags, narrative, dialogue blocks, recent events. |
| `RpgActionView` | Current command, quick actions, submit state, validation message. |
| `RpgWorldView` | Map/thumbnail, time, weather, temperature, reputation, travel controls. |
| `RpgEncounterView` | Combat status, initiative, enemies, available combat actions. |
| `RpgJournalView` | Journal entries, dialogue log, turn history. |
| `RpgInventoryView` | Items, quantities, equipment, ability/hotbar slots. |
| `RpgJobView` | Running/queued/completed jobs, progress, ETA, cancellation/view details. |
| `RpgReportView` | Autoplay state, reports, checkpoints, save/export actions. |

Acceptance gate:

- The new screen can render from fixtures without calling live endpoints.
- Missing fields degrade gracefully instead of breaking the layout.

## Phase 2 — Static shell and responsive layout

**Goal:** Replace the current form/card layout with the new RPG workstation shell using fixture data only.

Work items:

- Add the top RPG mode status shell: engine status, local-first chip, route/status indicators.
- Build the three-column desktop layout: left player rail, center adventure stack, right world rail.
- Add the bottom inventory/hotbar strip.
- Add responsive breakpoints:
  - **Desktop wide:** three columns + bottom strip.
  - **Laptop:** collapsible side rails.
  - **Narrow/mobile:** stacked sections with sticky action composer.
- Preserve the existing top Omnix navigation and route behavior.

Acceptance gate:

- The mock layout is visually close to the approved design.
- No live RPG flows are removed; old behavior can still be reached or the new UI safely renders the same route.

## Phase 3 — Player, party, gear, and quest rail

**Goal:** Implement the left rail as a complete player status hub.

Work items:

- Hero card: portrait placeholder, name, class/archetype, level, title/origin.
- Resource bars: HP, stamina, mana, XP.
- Currency/reputation row: gold/silver/copper if available, renown/reputation summary.
- Equipped gear list: weapon, armor, cloak, ring, or empty-state slots.
- Party list: companion avatar, role, level, HP/status, relationship summary.
- Active quests: quest title, current objective, urgency/progress indicator, open/drill-down action.

Acceptance gate:

- A player can understand character readiness, party health, and active objectives without reading the transcript.
- Empty party, no gear, no quests, and missing portrait states are handled cleanly.

## Phase 4 — Main story scene and action composer

**Goal:** Make the center panel the primary play surface.

Work items:

- Location header with tags: location name, biome/type, danger/weather/time tags.
- Story transcript cards: player action, narrator result, NPC dialogue, system/state event entries.
- Recent event stack: deterministic deltas such as XP gained, item added, location changed, relationship change.
- Command input with submit button, dropdown, and keyboard shortcut.
- Quick action buttons: Talk, Travel, Investigate, Rest, Inventory, Attack.
- Action validation: disabled states when combat/travel/service gating prevents an action.
- Turn pending/running state that shows progress without clearing current context.

Acceptance gate:

- The player can read what happened, decide what to do next, submit a turn, and see deterministic deltas in one place.
- The action composer remains available and obvious.

## Phase 5 — Journal, dialogue log, and turn history

**Goal:** Add the center-lower audit and memory surfaces.

Work items:

- Tab strip: Journal, Dialogue Log, Turn History.
- Journal list with timestamp/location/category chips.
- Journal detail card with objective links and related entities.
- Dialogue log grouped by speaker/NPC and session turn.
- Turn history showing command, result summary, state deltas, and replay/checkpoint hooks.
- Search/filter affordance if the log grows long.

Acceptance gate:

- The player can recover context after dozens of turns.
- Debug/audit information is available without overwhelming the main story panel.

## Phase 6 — World rail: map, world state, encounter, NPC relationships

**Goal:** Turn the right rail into the world awareness hub.

Work items:

- Location/map card with current marker and change-location/travel affordance.
- World state card: time, date/day, weather, temperature, faction/reputation, danger level.
- Encounter card:
  - Idle state: no active combat.
  - Warning state: hostile signs / imminent threat.
  - Combat state: enemies, initiative, turn order, active actor, available combat actions.
- NPC relationship card: NPC name, stance, trust/affinity, last interaction summary.
- Hooks for travel graph, faction status, and rumor/world events as they mature.

Acceptance gate:

- The player can tell where they are, what the conditions are, who matters nearby, and whether danger/combat is active.

## Phase 7 — Jobs, autoplay, reports, and checkpoint controls

**Goal:** Preserve workstation transparency without making jobs the whole RPG UI.

Work items:

- RPG jobs compact card with running/queued/completed states.
- Progress bars and ETAs for turn, narration, world update, image generation, report generation.
- Autoplay controls: off/on, scenario selector if available, run progress.
- Reports card: latest reports, ready count, open/export actions.
- Checkpoint card: saved timestamp, create checkpoint, restore/checkpoint list affordance.
- Error surfacing for failed background jobs with retry/view details.

Acceptance gate:

- The existing job/report/checkpoint capabilities are still visible and controllable, but no longer dominate the RPG mode.

## Phase 8 — Inventory, abilities, and hotbar

**Goal:** Give the player a game-like lower control strip.

Work items:

- Inventory tab with item slots, quantity badges, rarity/quality hints, empty slots.
- Abilities tab with learned abilities, cooldown/availability state, stat dependency hints.
- Hotbar tab/strip with numbered slots and click/keyboard bindings.
- Item detail popover: inspect, use, equip, drop/sell where supported.
- Ability detail popover: target requirements, stamina/mana cost, combat/travel gating.

Acceptance gate:

- Inventory and abilities are visible enough to encourage gameplay choices, not hidden as raw JSON or logs.

## Phase 9 — Live API wiring and migration from old screen

**Goal:** Replace fixtures with live RPG data incrementally.

Work items:

- Wire session selector/current session loading into the new state adapter.
- Wire turn submission through the existing deterministic turn endpoint.
- Wire job polling or SSE status into the RPG jobs card.
- Wire reports, checkpoints, and autoplay controls to existing endpoints.
- Wire journal/history from session state or generated reports.
- Keep clear boundaries between canonical state, narration, and background audit/correction output.
- Remove or hide old duplicate panels only after parity is confirmed.

Acceptance gate:

- Existing RPG turn, session, jobs, reports, checkpoint, and autoplay flows still work through the redesigned UI.
- No canonical state is parsed from free-form narration.

## Phase 10 — Combat and encounter expansion

**Goal:** Make combat state/action affordances first-class once live combat lifecycle data is available.

Work items:

- Combat banner when active: active actor, round, initiative queue.
- Enemy cards: HP, status effects, intent/stance if available.
- Combat action set: Attack, Defend, Ability, Item, Flee, Talk/Negotiate where supported.
- Disable non-combat quick actions during combat unless allowed by simulation.
- Show deterministic combat deltas: hit/miss, damage, XP, loot, defeat, companion status.

Acceptance gate:

- The player cannot spam invalid actions and can clearly see whose turn it is.

## Phase 11 — Visual polish, accessibility, and performance

**Goal:** Make the UI feel production-ready.

Work items:

- Finalize dark RPG theme tokens: surfaces, borders, glow, text contrast, danger/success/warning colors.
- Add skeleton/loading states for each panel.
- Add focus rings and keyboard order.
- Add reduced-motion safe animations.
- Add truncation and overflow handling for long NPC names, quests, item names, and narrative text.
- Ensure large logs are virtualized or paginated if needed.
- Keep turn submission and panel updates under the existing performance targets.

Acceptance gate:

- The UI is readable, responsive, keyboard usable, and does not degrade long-session performance.

## Phase 12 — Test coverage and regression gates

**Goal:** Protect the redesigned RPG mode from breaking deterministic gameplay flows.

Work items:

- Fixture render tests for every panel state.
- Adapter tests for missing/partial backend payloads.
- Turn submission integration test using a mocked deterministic result.
- Job status rendering tests for queued/running/completed/failed jobs.
- Accessibility smoke tests for tabs, action composer, quick actions, and modal/popover controls.
- Visual regression screenshots if the project has a screenshot test path.
- Update docs with the final component map and accepted design screenshots.

Acceptance gate:

- The redesign has enough regression coverage to safely iterate on new RPG mechanics.

## Suggested PR sequence

| PR | Slice | Expected scope |
| --- | --- | --- |
| 1 | Roadmap and design approval | Docs only; feature/component inventory plus implementation roadmap. |
| 2 | State adapter and fixtures | Normalized RPG UI view models and fixture payload. |
| 3 | Static shell layout | New three-column RPG screen with fixture data. |
| 4 | Player rail | Hero, vitals, gear, party, quests. |
| 5 | Main story/action composer | Scene transcript, recent events, command input, quick actions. |
| 6 | Journal/history panels | Journal, dialogue log, turn history surfaces. |
| 7 | World rail | Map/location, world state, encounter, NPC relationships. |
| 8 | Jobs/reports/checkpoints | Compact workstation controls wired to live or fixture data. |
| 9 | Inventory/abilities/hotbar | Lower game controls and item/ability details. |
| 10 | Live data wiring | Session load, turn submit, jobs, reports, checkpoint parity. |
| 11 | Combat affordances | Initiative, enemy cards, combat action gating. |
| 12 | Polish/tests | Accessibility, responsive layout, performance, regression coverage. |

## First implementation target

The first code PR should not attempt full live integration. It should add the normalized RPG UI fixture layer and render the redesigned shell in a safe, reversible way. The goal is to make the approved design tangible in the app without risking the deterministic turn loop.

Recommended first code slice:

1. Add `rpg-ui-fixtures` or equivalent fixture module.
2. Add `normalizeRpgUiState` or equivalent adapter helper.
3. Add the new RPG shell containers and CSS tokens.
4. Render the redesigned layout behind a temporary flag or isolated route/state branch if needed.
5. Keep the current turn submission flow intact until Phase 9.

## Open implementation questions

- Should the first live version use the current RPG route directly, or a temporary preview route until parity is reached?
- Does the existing frontend stack support component-level tests, or should the first coverage be adapter/unit tests only?
- Should portraits and scene/map images be placeholders at first, or should they hook into the existing local image-generation service immediately?
- Should autoplay controls live in the right rail only, or also expose a compact top-level run mode toggle?
- Should inventory/hotbar actions submit natural-language intents, structured deterministic actions, or a hybrid command payload?

## Definition of done for the full redesign

The redesigned RPG mode is complete when a player can:

- Load or create a session.
- Understand hero, party, quest, inventory, world, NPC, and encounter state at a glance.
- Submit normal role-playing commands through the action composer.
- Use quick actions without breaking deterministic gating.
- See turn results, state deltas, journal/history, and background job progress.
- Save/checkpoint/export/report without leaving RPG mode.
- Continue through long sessions without losing context or performance.
