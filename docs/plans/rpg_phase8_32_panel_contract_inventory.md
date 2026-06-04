# RPG Phase 8.32 Panel Contract Inventory

Phase 8.32 records the current provider-free panel contract inventory after Phase 8.31 closeout planning.

## Registered panel slots

The shared layout registry defines nine deterministic panel slots, in stable render order:

1. `conversation-settings`
2. `map-location`
3. `player-hud`
4. `objective-journal`
5. `combat-action`
6. `inventory-party`
7. `recent-activity`
8. `suggested-actions`
9. `survival-inspector`

The registry contract is source-backed by `src/static/rpg/rpgPanelLayoutRegistry.js` and currently includes:

- `SOURCE = "deterministic_phase8_panel_layout_registry"`
- `PANEL_ORDER`
- `PANEL_LABELS`
- `panelOrder()`
- `panelLabels()`
- `panelLabel(panelId)`
- `panelIndex(panelId)`
- `ensurePanelRoot()`
- `ensurePanelSlot(panelId)`
- `ensureOrderedPanelSlots()`
- `attachPanelToSlot(panelElement, panelId)`

## Shared panel chrome contract

The shared chrome contract is source-backed by `src/static/rpg/rpgPanelChrome.js` and currently includes:

- `SOURCE = "deterministic_phase8_panel_chrome"`
- `READ_ONLY_AUTHORITY = "runtime_validated_commands_only"`
- `FOCUS_TARGET = "panel_region"`
- `PANEL_SCHEMA_VERSION = "phase8_panel_chrome_v1"`
- `panelSourceBadge(...)`
- `panelEmptyState(...)`
- `runtimeValidationNotice(...)`
- `attachPanelToLayout(...)`
- `decoratePanel(...)`

## Metadata families already present

The current Phase 8 chrome metadata families are:

- accessibility metadata
- state metadata
- read-only/runtime-authority metadata
- focus metadata
- section metadata
- density metadata
- freshness metadata
- priority metadata
- render-kind metadata
- provenance metadata
- tone metadata
- schema/version metadata
- surface metadata

These metadata families are now considered consolidated for Phase 8. Do not add another metadata-only family in Phase 8 unless a required gate exposes a concrete missing contract.

## Panel file coverage

The active registered panel files are:

- `src/static/rpg-conversation-settings.js`
- `src/static/rpg/rpgMapLocationPanel.js`
- `src/static/rpg/rpgPlayerHud.js`
- `src/static/rpg/rpgObjectiveJournalPanel.js`
- `src/static/rpg/rpgCombatActionPanel.js`
- `src/static/rpg/rpgInventoryPartyPanel.js`
- `src/static/rpg/rpgRecentActivityPanel.js`
- `src/static/rpg/rpgSuggestedActionsPanel.js`
- `src/static/rpg/rpg-survival-inspector.js`

Each registered panel should continue to use shared chrome helpers for source badges, empty states, runtime-validation notices, and decorated panel attachment.

## Runtime authority boundary

This inventory is documentation and source-guard only.

- No provider or LLM calls are part of the panel layout/chrome contract.
- Registered panels are presentation-only unless they submit command intents through the existing runtime validation path.
- Suggested actions remain hints, not accepted gameplay actions.
- Survival inspector actions remain command intents routed through runtime validation.
- Runtime and simulation remain authoritative for gameplay truth.

## Phase 8 closeout routing

This inventory satisfies Phase 8.32 from the closeout plan. The remaining planned Phase 8 closeout slices are:

- Phase 8.33 — Browser smoke coverage for registered panels.
- Phase 8.34 — UI runtime-authority boundary audit.
- Phase 8.35 — Phase 8 final closeout note and Phase 9 handoff.
