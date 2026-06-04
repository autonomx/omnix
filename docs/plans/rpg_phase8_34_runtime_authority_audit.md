# RPG Phase 8.34 UI Runtime-Authority Boundary Audit

Phase 8.34 records the UI runtime-authority boundary audit for the Phase 8 panel closeout.

## Audit scope

This audit covers registered Phase 8 frontend panels and shared panel chrome/layout helpers.

The audit is source-backed and provider-free. It does not add gameplay commands, command execution paths, runtime mutation, provider calls, or LLM calls.

## Runtime authority rules

The UI boundary remains:

- Simulation/runtime is authoritative for gameplay truth.
- Shared panel chrome is presentation-only.
- Panel payloads are read-only unless they submit command intents through existing runtime validation paths.
- Suggested actions are hints only and are not accepted gameplay actions.
- Survival inspector actions may use command bridge hooks, but only as runtime-validated command intents.
- Rejected/non-player-turn actions must not be treated as successful state changes.
- Turn authority remains with `app.rpg.session.runtime_part27`.
- Combat action authority remains with `app.rpg.session.runtime_part23`.

## Audited UI files

The audit covers these active registered UI files:

- `src/static/rpg-conversation-settings.js`
- `src/static/rpg/rpgMapLocationPanel.js`
- `src/static/rpg/rpgPlayerHud.js`
- `src/static/rpg/rpgObjectiveJournalPanel.js`
- `src/static/rpg/rpgCombatActionPanel.js`
- `src/static/rpg/rpgInventoryPartyPanel.js`
- `src/static/rpg/rpgRecentActivityPanel.js`
- `src/static/rpg/rpgSuggestedActionsPanel.js`
- `src/static/rpg/rpg-survival-inspector.js`
- `src/static/rpg/rpgPanelChrome.js`
- `src/static/rpg/rpgPanelLayoutRegistry.js`

## Audit assertions

Provider-free source guards should continue to verify:

- No registered read-only panel calls `fetch(`, `XMLHttpRequest`, provider APIs, LLM APIs, `apply_turn`, or random source APIs.
- Registered read-only panels do not call `sendCommand`, `executeCommand`, `acceptAction`, or mutation helpers.
- `rpg-survival-inspector.js` is the only registered panel allowed to reference `RpgCommandBridge.submitCommand` and `window.rpgSendMessage`, and those remain command-intent submission hooks.
- Shared chrome metadata keeps `READ_ONLY_AUTHORITY = "runtime_validated_commands_only"`.
- Shared chrome continues to render runtime-validation notices.
- Runtime wrapper manifest still records `final_apply_turn_authoritative_module = "app.rpg.session.runtime_part27"`.
- Runtime wrapper manifest still records `final_apply_attack_combat_action_module = "app.rpg.session.runtime_part23"`.

## Phase 8 closeout routing

This audit satisfies Phase 8.34 from the closeout plan. The remaining planned Phase 8 closeout slice is:

- Phase 8.35 — Phase 8 final closeout note and Phase 9 handoff.
