# RPG Phase 7 closeout plan

Source: `deterministic_phase7_closeout_planning_gate`

This closeout plan records the Phase 7 state after saved artifact operator UX diagnostics and routes remaining Save/Load, Replay, Determinism, and 100-turn risks without overstating live-provider coverage.

## Closeout decision

Phase 7 can be treated as materially complete for provider-free PR gate coverage once the roadmap records Phase 7.20. The project should move next to Phase 8 UI/UX production pass while keeping the risks below visible for later targeted slices.

This is not a claim that a full live-provider 100-turn campaign has been completed in required PR CI. Required PR CI remains deterministic and provider-free. Live/manual/autoplay campaign evidence remains optional local validation unless a future slice explicitly adds a required live evidence gate.

## What Phase 7 now covers

Phase 7 now has deterministic coverage for:

- replay checkpoint digests and restore validation;
- replay turn sequence validation through canonical runtime command helpers;
- package/disk save-load replay roundtrip validation;
- 100-turn readiness analysis for progress, loop risk, and report/transcript budgets;
- 100-turn certification payloads and report rendering;
- saved certification JSON emission;
- saved autoplay/manual checkpoint and state digest sources;
- saved/loadable state digest comparison for persisted JSON state fixtures;
- saved output progress metrics extraction;
- report diagnostics visibility;
- live/manual completion-path saved artifact emission hooks;
- saved artifact disk bundle and ZIP verification;
- operator runbook guidance;
- end-to-end deterministic saved 100-turn fixture certification;
- real completion path smoke integration;
- hardened flat/nested artifact discovery; and
- operator-facing nested layout, duplicate, and partial-output diagnostics.

## Remaining risks routed forward

The following risks remain open and should be routed to later phases instead of blocking Phase 8 entry:

| Risk | Route | Reason |
|---|---|---|
| Full live-provider 100-turn campaign execution is not required in PR CI. | Phase 8/10 manual validation or a future explicit live-evidence slice. | Required PR CI is intentionally provider-free and deterministic. |
| Long multi-turn campaign replay is not exhaustive. | Phase 9 endurance systems. | Long-run replay needs bounded report and compression work. |
| Combat replay coverage is not full campaign-grade. | Phase 8 combat UI/state visibility or Phase 9 endurance. | Combat persistence should be visible to players before expanding endurance. |
| Quest reward replay coverage is not full campaign-grade. | Phase 8 objective/journal UI and later deterministic replay expansion. | Quest state needs better player-facing visibility and audit trails. |
| NPC memory replay and file-backed profiles remain pending. | Phase 5 NPC profiles/memory or Phase 8/9 follow-up. | NPC profile/memory persistence is a dedicated system area outside this closeout. |
| Party/companion replay is not full campaign-grade. | Phase 8 party UI and later replay expansion. | Party state needs clearer UI before broader endurance certification. |
| Full package/disk replay of an actual 100-turn campaign remains incomplete. | Phase 9 endurance and Phase 10 packaging/stability. | Actual long-run package replay depends on endurance and production packaging constraints. |
| Real saved/loadable campaign state diff validation in live completion paths needs more evidence. | Future live/manual evidence slice if needed. | Existing PR evidence is artifact-shaped and provider-free, not live-provider proof. |

## Architecture boundaries preserved

- Simulation/runtime remains authoritative.
- LLM/provider output remains presentation/advisory only.
- Deterministic diagnostics remain provider-free and source-backed.
- Rejected commands must not be treated as successful state changes.
- Digest mismatches, replay drift, persistence drift, readiness blockers, certification blockers, missing artifacts, missing ZIP entries, and ambiguous duplicate artifact diagnostics must not be ignored.
- Generated runtime outputs under `resources/data/test-results` must not be committed.

## Phase 8 entry recommendation

Move to Phase 8 UI/UX production pass after the roadmap cleanup records Phase 7.20. Phase 8 should focus on player-visible state, objective, journal, combat, inventory, party, map, settings, and report/status clarity rather than adding broad new runtime systems first.

Suggested first Phase 8 slice:

- Phase 8.1 — player-visible state and objective HUD foundation.
- Keep it deterministic and source-backed.
- Show current location, active objective, player resources, party summary, and major warnings without allowing UI presentation to mutate simulation state.
