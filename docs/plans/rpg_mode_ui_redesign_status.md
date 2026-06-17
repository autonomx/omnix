# RPG Mode UI Redesign Status

This note supersedes the earlier planning-only RPG mode UI inventory work. The approved direction is now implemented as a production-oriented RPG workstation shell, with remaining work focused on production validation, loading states, and backend-driven affordance expansion.

## Source of truth

- Branch: `rpg`
- Design target: gameplay-first Omnix RPG workstation with player rail, story/action surface, journal/history, world/jobs rail, and loadout strip.
- Implementation rule: simulation remains authoritative; UI presents normalized RPG state and submits deterministic `rpg.turn` requests without mutating gameplay state locally.

## Completed implementation slices

| Slice | PR | Status | Notes |
| --- | --- | --- | --- |
| Redesigned RPG workspace shell | #543 | Merged | Replaced the old RPG form/dashboard with the approved three-rail workstation layout while preserving turn submission. |
| UI state adapter | #544 | Merged | Added normalized RPG workspace state, preview fixtures, and adapter tests. |
| Workspace-to-adapter wiring | #545 | Merged | Removed duplicated shell-local fixture/state constants from `RpgWorkspace`. |
| Live session summary derivation | #546 | Merged | Derived selected/latest session, location, checkpoint labels, jobs, reports, and summary context. |
| Player rail live derivation | #547 | Merged | Derived hero, vitals, currency, gear, party, quests, and inventory from live session fields. |
| World rail live derivation | #548 | Merged | Derived world rows, NPC relationships, and encounter preview from live session state. |
| Live encounter rendering | #549 | Merged | Replaced hardcoded encounter copy with normalized encounter card state. |
| Narrative derivation | #550 | Merged | Derived scene copy, recent events, journal entries, and details from timeline/dialogue/event logs. |
| Narrative tabs | #551 | Merged | Added selectable Journal / Dialogue Log / Turn History panels. |
| Loadout tabs | #552 | Merged | Added selectable Inventory / Abilities / Hotbar panels. |
| Action composer extraction | #553 | Merged | Isolated session selection, command input, submit button, and quick actions. |
| Player rail extraction | #554 | Merged | Isolated hero, vitals, gear, party, and quest rail rendering. |
| World rail extraction | #555 | Merged | Isolated world, encounter, NPC, jobs, report, autoplay, and checkpoint rail rendering. |
| Story scene extraction | #556 | Merged | Isolated scene card, dialogue preview, recent events, and action-composer slot. |
| Workspace header extraction | #557 | Merged | Isolated RPG module heading and runtime status chips. |
| Live controls | #559 | Merged | Wired report, checkpoint, autoplay, and job-card controls. |
| Combat surface | #560 | Merged | Added tactical combat panels and replay-safe combat command affordances. |
| Loadout actions | #561 | Merged | Added item, ability, and hotbar detail panels with command insertion affordances. |
| Responsive polish | #562 | Merged | Added collapsible rails, improved narrow-screen behavior, overflow containment, and reduced-motion safeguards. |
| Regression coverage | #563 | Merged | Added workspace-level regression coverage for replay-safe live controls and rail accessibility. |
| Loading and empty states | #564 | Merged | Added live data status surfaces, empty artifact affordances, and loading/error/empty-state regression coverage. |

## Current component map

| Area | Component / module | Responsibility |
| --- | --- | --- |
| Workspace orchestration | `RpgWorkspace` | Coordinates data queries, selected session state, submit flow, rail visibility, and layout composition. |
| State normalization | `rpgUiState` | Builds a stable UI view model from live sessions, jobs, assets, reports, and preview fallbacks. |
| Header | `RpgWorkspaceHeader` | Shows RPG mode title, engine status, session status, and runtime chips. |
| Live data status | `RpgLiveDataStatus` | Summarizes session, job, checkpoint/asset, and report query loading/error/empty states. |
| Left rail | `RpgPlayerRail` | Shows hero state, meters, XP, currency, gear, party, and quests. |
| Center scene | `RpgStoryScene` | Shows active location, scene copy, dialogue preview, recent events, and action composer slot. |
| Combat surface | `RpgCombatSurface` | Shows tactical encounter state, initiative, combatants, and combat command affordances. |
| Action composer | `RpgActionComposer` | Handles session selection, command entry, quick actions, pending/invalid states, and turn submission controls. |
| Narrative history | `RpgNarrativeTabs` | Shows journal, dialogue log, and turn history panels. |
| Loadout | `RpgLoadoutTabs` | Shows inventory, abilities, hotbar, details, and command insertion actions. |
| Right rail | `RpgWorldRail` | Shows location/map, world state, encounter, relationships, jobs, autoplay/report/checkpoint cards. |

## Remaining implementation work

### 1. Live control parity

The shell now renders and controls normalized jobs, reports, checkpoints, and autoplay status. Remaining work should focus on end-to-end validation under real backend data:

- Verify open/download report actions against produced report artifacts.
- Verify checkpoint creation payloads against replay persistence expectations.
- Verify autoplay start/stop behavior during active RPG sessions.
- Confirm job polling/SSE behavior for long-running background RPG jobs.
- Keep loading, empty, and error-state coverage aligned with backend behavior as API responses evolve.

### 2. Combat affordance expansion

The tactical combat surface now exists. Remaining combat work should follow backend capability and deterministic contract expansion:

- Victory, defeat, and escape state handling.
- Combat result deltas from live turn results in story/log panels.
- Richer invalid-action explanations when backend returns combat gating errors.
- Target selection once the simulation exposes targetable combatant identifiers.

### 3. Inventory and ability interactions

Inventory, abilities, and hotbar now provide detail panels and replay-safe command insertion. Remaining work depends on simulation affordance support:

- Sell/trade affordances where shop or merchant state is active.
- Hotbar assignment persistence if/when supported.
- Cooldown/resource-cost fields from live ability state.
- Rich target requirements once combat target identifiers are exposed.

### 4. Responsive and production polish

The layout is componentized and has its first production polish pass:

- Collapsible left/right rails.
- Narrow-screen stacking and keyboard-safe focus order.
- Reduced-motion behavior for progress/status effects.
- Long log overflow handling and scroll containment.
- Live data status cards for loading, empty, refreshing, ready, and error sources.

Remaining polish:

- Optional visual regression screenshots if supported locally.
- Manual browser pass across wide, tablet, and narrow layouts.

### 5. Regression coverage and docs

Existing component and adapter coverage is strong. Remaining gates after the loading-state slice:

- Stop-autoplay coverage once active job cancellation behavior is validated with real backend data.
- Visual regression screenshots if supported locally.
- Final screenshot or design reference attachment once local visual validation is available.

## Recommended next PR sequence

1. `p565-rpg-report-artifact-links` — tighten direct report/checkpoint artifact linking once backend artifact routing is confirmed.

## Notes

- Keep future slices narrow and auditable.
- Do not duplicate normalization logic in presentation components; extend `rpgUiState` first.
- Do not let narration fields update authoritative simulation state.
- Keep the existing deterministic `rpg.turn` submit behavior intact unless the backend turn contract changes deliberately.
