# RPG Branching Policy

Date: 2026-05-30

## Policy

From this point forward, `rpg` is the main RPG integration branch.

Feature work should use this flow:

```text
rpg
  -> feature branch, e.g. rpg-phase0-architecture-compliance
  -> implementation commits
  -> validation
  -> merge/fast-forward back into rpg
```

## Rules

1. Treat `rpg` as the source of truth for RPG work.
2. Do not commit feature work directly to historical version branches such as `rpg-v1.36` unless explicitly requested.
3. Create feature branches from the current `rpg` head.
4. Merge completed feature branches back into `rpg`.
5. Keep branch names descriptive and phase-oriented.
6. Use architecture/evaluation/plan docs as persistent baselines.
7. Update `docs/rpg_architecture.md` when source architecture changes.
8. Update `docs/rpg_evaluation_snapshot.md` when a major milestone changes scores.
9. Update `docs/plans/rpg_production_readiness_plan.md` when phase gates change.

## Current First Phase

First feature branch:

```text
rpg-phase0-architecture-compliance
```

Phase goal:

```text
Lock the current architecture so future work does not regress CE.2.12/CE.2.13.
```

Phase 0 scope:

- Assert interactive/manual matrix turns use `interactive_first_call_runtime.apply_turn` unless explicitly marked legacy.
- Assert no harness-owned fast gameplay routing returns.
- Assert source fields exist for fallbacks and repairs.
- Assert stateful first-call visible responses cannot mutate state.
- Add final-result hard-state-claim audit scaffolding.
