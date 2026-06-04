# RPG Phase 8.33 Browser Smoke Coverage

Phase 8.33 records provider-free browser smoke coverage for the registered Phase 8 panels.

## Scope

This is a source-backed smoke coverage slice, not a new browser test harness installation.

The current repo did not expose a dedicated Phase 8 Playwright panel smoke test by source search, so this slice keeps coverage deterministic and provider-free by guarding the existing panel source contracts that a browser smoke pass must satisfy.

## Registered panel smoke matrix

Every registered panel must continue to satisfy these smoke conditions:

| Panel slot | Panel file | Required smoke contract |
| --- | --- | --- |
| `conversation-settings` | `src/static/rpg-conversation-settings.js` | shared chrome, source badge, runtime notice, decorated panel |
| `map-location` | `src/static/rpg/rpgMapLocationPanel.js` | shared chrome, source badge, empty state, runtime notice, decorated panel |
| `player-hud` | `src/static/rpg/rpgPlayerHud.js` | shared chrome, source badge, empty state, runtime notice, decorated panel |
| `objective-journal` | `src/static/rpg/rpgObjectiveJournalPanel.js` | shared chrome, source badge, empty state, runtime notice, decorated panel |
| `combat-action` | `src/static/rpg/rpgCombatActionPanel.js` | shared chrome, source badge, empty state, runtime notice, decorated panel |
| `inventory-party` | `src/static/rpg/rpgInventoryPartyPanel.js` | shared chrome, source badge, empty state, runtime notice, decorated panel |
| `recent-activity` | `src/static/rpg/rpgRecentActivityPanel.js` | shared chrome, source badge, empty state, runtime notice, decorated panel |
| `suggested-actions` | `src/static/rpg/rpgSuggestedActionsPanel.js` | shared chrome, source badge, empty state, runtime notice, decorated panel |
| `survival-inspector` | `src/static/rpg/rpg-survival-inspector.js` | shared chrome, source badge, empty state, runtime notice, decorated panel, runtime-validated command bridge only |

## Escaped payload smoke expectations

Panel browser rendering must keep user-visible dynamic values escaped. Source guards should verify registered panels and shared chrome preserve escaped rendering contracts such as:

- `escapeHtml`
- `${escapeHtml(source)}`
- `${escapeHtml(label)}`
- `${escapeHtml(detail)}` or equivalent detail/summary escaping
- `${escapeHtml(command)}` where command hints are displayed
- `${escapeHtml(reason)}` where reason text is displayed

## Runtime authority smoke expectations

Smoke coverage must not treat UI hints as accepted actions.

- Suggested actions remain hints until runtime validates a command.
- Survival inspector may submit command intents only through the existing runtime validation path.
- No registered panel may add provider/LLM calls.
- No registered panel may mutate gameplay truth.
- Runtime and simulation remain authoritative.

## Phase 8 closeout routing

This smoke coverage satisfies Phase 8.33 from the closeout plan. The remaining planned Phase 8 closeout slices are:

- Phase 8.34 — UI runtime-authority boundary audit.
- Phase 8.35 — Phase 8 final closeout note and Phase 9 handoff.
