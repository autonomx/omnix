# Phase 8 — Combat Lifecycle Expansion Progress

## Status

Implemented as a deterministic backend foundation on 2026-06-24.

## Added

- `Combatant` and `CombatState` contracts for active encounters.
- Stable initiative order and current-combatant helpers.
- Deterministic attack resolution with HP changes and narration facts.
- Enemy action selection for simple policies.
- Defeat outcome and loot gating helpers.
- XP award guard for approved sources.
- Report-friendly combat payloads.
- Regression tests for initiative, damage, defeat, enemy targeting, turn advance, XP, and report payloads.

## Determinism Boundary

Combat narration is limited to facts returned by the resolver. Loot and XP are allowed only when deterministic combat or reward rules authorize them.

## Verification

Pending GitHub Actions for this phase PR.
