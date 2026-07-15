# Unified RPG Narrative Engine — Milestones G-L Completion

Status: implementation complete; release evidence is certified against the exact pull-request head.

## Scope

Phases 25 through 42 complete the production cutover from overlapping RPG prose paths to one canonical narrative response authority.

- **Milestone G — canonical correctness:** typed semantic claims, knowledge grants, visibility rules, ordered blocks, and deterministic validation.
- **Milestone H — production generation:** structured provider output, direct-dialogue replacement, and one authoritative presentation entry point.
- **Milestone I — durable authority:** PostgreSQL canonical-response storage, turn idempotency, atomic persistence, submission replay, and runtime repository selection.
- **Milestone J — World Forge:** provider-backed proposal generation, deterministic commit gates, campaign-bible revisions, and dossier-quality enforcement.
- **Milestone K — asynchronous Genesis:** resumable campaign creation, progress reporting, cancellation, retry, and launch-readiness gating.
- **Milestone L — delivery and retirement:** resumable validated-block delivery, durable retirement telemetry, legacy publisher deletion audits, and final release certification.

## Production invariants

1. Simulation remains authoritative for hard state.
2. One `CanonicalNarrativeResponse` owns every player-visible RPG response.
3. Blocking and deferred delivery reuse the same response ID, semantic hash, and ordered blocks.
4. Reconnect resumes persisted delivery state without regenerating prose.
5. Compatibility fields are projections of the canonical response, never alternate publication owners.
6. Legacy publisher imports and visible production hooks are absent from the production-owner path.
7. World Forge and Hermes remain proposal-only until deterministic acceptance.
8. Campaign launch cannot proceed until Genesis and lore materialization are complete.

## Final certification

`src/app/rpg/narrative_engine/release_certification.py` fails closed unless all of the following evidence is present:

- expected and observed 40-character commit SHAs match;
- the required GitHub workflows are present and successful;
- hosted CI is explicitly provider-free and does not claim live-provider execution;
- publisher ownership and legacy deletion audits pass;
- required migrations, production files, and Phase 25-41 regression tests exist;
- deferred delivery preserves ordering, resume behavior, and semantic identity;
- retirement telemetry contains at least one record, zero alternate publishers, and zero deletion violations.

The certificate is intentionally generated from external exact-head evidence rather than committing a self-invalidating SHA into the repository.

## Validation boundary

GitHub Actions provide deterministic, provider-free architecture, persistence, regression, and endurance evidence. Live-provider prose quality and local latency remain operator-run evidence and are not fabricated by hosted CI.
