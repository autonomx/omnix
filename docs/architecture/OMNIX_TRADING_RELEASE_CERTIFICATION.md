# Omnix Trading Release Certification

This document separates automated implementation gates from environment-dependent release evidence. A green unit/typecheck workflow proves the first category only.

## Automated implementation gates

These checks run in the dedicated **Omnix Trading terminal gates** workflow:

- Trading architecture and backend tests
- indicator parity fixtures
- normalized provider/fallback contracts
- stream duplicate, ordering, gap, and lifecycle logic
- workspace migration and revision conflict behavior
- alert cooldown/idempotency/finalized-bar policy
- bounded scanner limits, cancellation, timeout, and deterministic ranking
- immutable replay datasets and next-bar backtest sequencing
- return, drawdown, win-rate, exposure, trade, equity, and log evidence
- BlobStore backtest artifact checksum contract
- paper account/order/fill/ledger/P&L/idempotency contracts
- no-live-broker and no-AI-mutation boundaries
- read-only research schema, prompt bounds, source metadata, and provider isolation
- frontend unit tests
- Trading TypeScript compilation
- release/legal/operator structural invariants

Automated gate status is recorded by the exact-head GitHub Actions run attached to PR #1488.

## Environment evidence required before release certification

| Evidence | Required procedure | Pass condition | Current status |
|---|---|---|---|
| PostgreSQL migration | Apply all Trading migrations to an empty database and a representative upgraded database. Restart gateway and reload workspace, alerts, scanner definitions/results, replay datasets, backtests, and paper accounts. | No migration errors, no fabricated legacy data, persisted records reload with correct revisions and checksums. | Pending environment run |
| PostgreSQL conflict/concurrency | Run concurrent alert evaluation, workspace updates, scanner completion, paper fills, reset/archive, and retry cases against PostgreSQL. | Revision conflicts are deterministic; no duplicate triggers, fills, ledger entries, or scanner results. | Pending environment run |
| Provider outage | Interrupt each enabled provider during history, quote, stream, alert, scanner, paper, and research operations. Restore it afterward. | UI identifies the failed provider, fallback is whole-dataset and policy-compliant, workers recover without duplicate state changes. | Pending environment run |
| WebSocket soak | Run the supported live crypto stream for the agreed soak duration with reconnect injection and sequence gaps. | No duplicate bars, no stale subscription after symbol/interval change, bounded reconnects, deterministic REST repair, no resource leak. | Pending environment run |
| Browser accessibility | Exercise Trading with keyboard only, reduced motion, zoom, high contrast, and an accessibility scanner. Review chart alternatives and all dialogs/tabs/drawers. | No critical accessibility violations; focus order and labels are usable; reduced motion is respected. | Pending browser run |
| Browser lifecycle/heap | Repeatedly mount/unmount one- and multi-chart layouts, switch feeds/timeframes, open/close drawers, run replay, and reconnect streams while measuring heap/listeners/sockets. | No orphan chart, observer, timer, WebSocket, or unbounded heap growth beyond the accepted benchmark. | Pending browser run |
| Chart performance | Run the OTT-0 benchmark procedure on the supported host with 1/2/4 charts and the agreed bar counts/indicators/drawings. | Meets the accepted first-render, frame, interaction, and memory thresholds documented with raw evidence. | Pending host benchmark |
| Scanner production universe | Run the approved 50-instrument and maximum-allowlist scans against real configured feeds with rate-limit observation. | Completes within policy limits, cancellation works, results carry exact provider/fingerprint/formula evidence. | Pending environment run |
| Backtest artifact recovery | Create large backtests, verify BlobStore checksum, simulate a corrupted/missing artifact, and apply the operator recovery procedure. | Corruption is detected; relational summaries remain queryable; cleanup/rebuild path is documented and successful. | Pending environment run |
| Security/legal review | Review active provider terms, redistribution flags, visible attribution, secrets handling, public exposure, and paper/live execution boundaries. | Approved usage scope and attribution; no credential leakage or live-order route. | Pending reviewer approval |
| Rollback rehearsal | Roll back the application version while preserving or explicitly migrating Trading data and artifacts according to the operator plan. | Service returns to the previous supported state without silent data corruption. | Pending environment run |

## Release decision rule

The Trading module is **code-complete** when the exact-head automated gates pass. It is **release-certified** only when every required environment row above is marked passed with dated evidence and reviewer identity.

Until then:

- PR #1488 remains draft;
- the module must not be represented as production-certified;
- paper simulation and research remain clearly labeled;
- no live brokerage execution may be enabled.

## Evidence record template

For each environment row, attach:

- date and operator;
- commit SHA;
- environment and versions;
- provider/feed configuration without secrets;
- exact commands or procedure;
- raw logs, screenshots, metrics, or artifact checksums;
- pass/fail conclusion;
- defects and remediation links;
- reviewer approval.
