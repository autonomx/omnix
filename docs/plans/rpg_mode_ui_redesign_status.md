# RPG Mode UI Redesign Status

This note supersedes the earlier planning-only RPG mode UI inventory work. The approved direction is now implemented as a production-oriented RPG workstation shell, with remaining work focused on deeper live wiring, combat affordances, inventory/ability interactions, responsive polish, and regression coverage.

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

## Current component map

| Area | Component / module | Responsibility |
| --- | --- | --- |
| Workspace orchestration | `RpgWorkspace` | Coordinates data queries, selected session state, submit flow, and layout composition. |
| State normalization | `rpgUiState` | Builds a stable UI view model from live sessions, jobs, assets, reports, and preview fallbacks. |
| Header | `RpgWorkspaceHeader` | Shows RPG mode title, engine status, session status, and runtime chips. |
| Left rail | `RpgPlayerRail` | Shows hero state, meters, XP, currency, gear, party, and quests. |
| Center scene | `RpgStoryScene` | Shows active location, scene copy, dialogue preview, recent events, and action composer slot. |
| Action composer | `RpgActionComposer` | Handles session selection, command entry, quick actions, pending/invalid states, and turn submission controls. |
| Narrative history | `RpgNarrativeTabs` | Shows journal, dialogue log, and turn history panels. |
| Loadout | `RpgLoadoutTabs` | Shows inventory, abilities, and hotbar panels. |
| Right rail | `RpgWorldRail` | Shows location/map, world state, encounter, relationships, jobs, autoplay/report/checkpoint cards. |

## Remaining implementation work

### 1. Live control parity

The shell renders normalized jobs, reports, checkpoints, and autoplay status, but remaining work should verify and complete all end-to-end controls:

- Open/download report actions from the report cards.
- Create checkpoint behavior from the checkpoint card.
- Autoplay start/stop controls and visible running state.
- Job polling/SSE behavior for active background RPG jobs.
- Empty/loading/error states for reports, checkpoints, jobs, and sessions.

### 2. Combat affordance expansion

The encounter card is live-aware, but combat still needs a full tactical UI layer:

- Active actor, round number, initiative queue, and turn ownership.
- Enemy cards with HP/status/effects.
- Combat-specific action buttons and invalid-action gating.
- Deterministic combat result deltas in the story/log panels.
- Defeat/victory/escape state handling.

### 3. Inventory and ability interactions

Inventory, abilities, and hotbar are visible. Next interactive layer:

- Item detail popovers or side details.
- Use/equip/drop/sell affordances where supported by the simulation.
- Ability details, cooldown/resource cost display, and target requirements.
- Hotbar assignment or command insertion behavior.

### 4. Responsive and production polish

The layout is now componentized enough to safely improve responsiveness:

- Collapsible left/right rails.
- Narrow-screen stacking and keyboard-safe focus order.
- Reduced-motion behavior for progress/status effects.
- Better skeleton/loading surfaces.
- Long log overflow handling and pagination/virtualization where needed.

### 5. Regression coverage and docs

Existing component and adapter coverage is strong for the slices completed so far. Remaining gates:

- Workspace-level integration coverage for live sessions plus turn submission.
- Jobs/report/checkpoint control tests.
- Combat fixture render tests.
- Accessibility smoke tests for tab panels and rail controls.
- Final screenshot or design reference attachment once local visual validation is available.

## Recommended next PR sequence

1. `p559-rpg-live-controls` — wire/verify report, checkpoint, autoplay, and job-card controls.
2. `p560-rpg-combat-surface` — add tactical combat state panels and combat-only action affordances.
3. `p561-rpg-inventory-actions` — add inventory/ability details and supported command insertion behavior.
4. `p562-rpg-responsive-polish` — add collapsible rails, narrow-screen stacking, and overflow handling.
5. `p563-rpg-ui-regression` — add final workspace integration/accessibility regression gates.

## Notes

- Keep future slices narrow and auditable.
- Do not duplicate normalization logic in presentation components; extend `rpgUiState` first.
- Do not let narration fields update authoritative simulation state.
- Keep the existing deterministic `rpg.turn` submit behavior intact unless the backend turn contract changes deliberately.
