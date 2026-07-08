# MEM-15 — Adversarial release gate

Status: complete and squash-merged into `rpg`.

Implementation pull request: #1273.

Exact verified head: `91954b6566e0c2503b0b9429d3bb3dafb34d2af0`.

Squash merge SHA: `aefdc5e4d8d7bab43110b8806e760540382875ec`.

## Release scope

MEM-0 through MEM-14 established the Chat memory architecture, contracts, prompt assembly, persistence, snapshot lifecycle, approved-memory injection, management UI, explicit commands, pending suggestions, consolidation policy, FTS5 history recall, long-session compaction, optional Hermes synchronization, and server-enforced privacy settings.

MEM-15 added the final adversarial integration gate and process-local concurrency hardening. Chat read-modify-write operations are serialized, snapshot refresh participates in the same mutation lock, and JSON fallback persistence uses atomic temporary-file replacement. SQLite remains the recommended durable Chat store.

Both required GitHub Actions workflows passed on the exact MEM-15 head before squash merge:

- `RPG Phase 0 architecture compliance`
- `RPG deterministic PR gates`

## Adversarial evidence

The final gate covers these risks directly or through the named phase tests:

| Release concern | Evidence |
|---|---|
| Cross-project and cross-session isolation | `test_release_gate_blocks_cross_scope_pending_rejected_and_external_instructions`, MEM-1, MEM-7, MEM-11 tests |
| Pending and rejected candidate exclusion | MEM-1, MEM-6, and MEM-15 release-gate tests |
| Forget propagation into frozen snapshots | MEM-3, MEM-5, MEM-6, and MEM-15 release-gate tests |
| Web, email, tool, and Hermes prompt-injection resistance | MEM-2, MEM-9, MEM-13, and MEM-15 release-gate tests |
| Duplicate retry protection | MEM-3, MEM-9, MEM-12, and MEM-13 idempotency tests |
| Contradiction, supersession, and capacity behavior | MEM-10 tests |
| Stale record and snapshot revisions | MEM-3, MEM-5, MEM-7, and MEM-15 concurrency tests |
| Restart-safe JSON-to-SQLite migration | MEM-4 migration and rollback tests |
| SQLite partial-write and active-generation failure behavior | MEM-4 transaction tests and MEM-15 recoverable streaming-failure test |
| FTS deletion and degraded mode | MEM-11 tests |
| Streaming and non-streaming prompt parity | MEM-2 and MEM-6 tests |
| Memory-disabled compatibility and non-destructive rollback | MEM-6, MEM-14, and MEM-15 tests |
| Long-session budget enforcement | MEM-2, MEM-10, and MEM-12 tests |
| Existing session compatibility | MEM-1 and MEM-4 legacy tests |
| Voice and text snapshot parity | MEM-15 serialized-prompt parity test |
| Hermes-offline independence | MEM-13 and MEM-15 tests |
| Simultaneous sends, edits, and refreshes | MEM-15 process-local mutation and optimistic-conflict tests |
| Forget or refresh during active generation | MEM-5 snapshot semantics and MEM-15 future-prompt invalidation test |

## Active-generation semantics

Provider input is frozen when a generation begins. Forgetting a record cannot retract bytes already sent to a provider, but it immediately purges the record and frozen snapshot copy so every later provider assembly excludes it. Refresh operations use optimistic snapshot revisions; concurrent refresh attempts cannot silently overwrite one another.

A streaming provider failure leaves the persisted user turn in `running` state. The turn can be completed with explicit failure metadata or retried by higher-level orchestration without losing the user input. Non-streaming generation remains all-or-nothing: a failed provider call does not append a fabricated assistant response.

## Completed staged rollout evidence

After MEM-15 merged, six independent rollout gates were implemented and verified:

| Stage | Pull request | Capability boundary | Merge SHA |
|---|---:|---|---|
| 1 | #1274 | SQLite Chat storage | `ce44a70f79a9f13d8b000cbe64d0029d685838d1` |
| 2 | #1275 | Explicit approved memory | `189552aedfd671ba15ae9160f03850cc3271c783` |
| 3 | #1276 | Pending suggestions | `e37a88a5d2a30101d55d0ab26915e8cd85edbfcc` |
| 4 | #1277 | Scoped history recall | `191c5bb5080e639d3b5b4887738bdf1b7098900f` |
| 5 | #1278 | Long-session compaction | `5e9161af773ca486cc91770b20f8f47659891ffb` |
| 6 | #1279 | Optional Hermes adapter | `d4de5d1233db8d9cb382153a8683e3bff7bc2746` |

Each stage has a runbook, temporary-store preflight, unit coverage, rollback guidance, and exact-head workflow evidence. The consolidated matrix is in `chat-memory-release-evidence.md`.

## Recommended operational posture

The fully verified native configuration keeps Hermes off by default:

```text
OMNIX_CHAT_SQLITE_STORE_ENABLED=1
OMNIX_CHAT_MEMORY_ENABLED=1
OMNIX_CHAT_MEMORY_SUGGESTIONS_ENABLED=1
OMNIX_CHAT_HISTORY_RECALL_ENABLED=1
OMNIX_CHAT_COMPACTION_ENABLED=1
OMNIX_HERMES_MEMORY_SYNC_ENABLED=0
```

Hermes can be enabled later as a controlled optional pilot after backing up its directory and running the Stage 6 preflight.

## Rollback

- Disable any feature through persisted settings or its environment override; stored records and migrated history are retained.
- Disable `OMNIX_CHAT_MEMORY_ENABLED` to restore the legacy provider payload shape for sessions without active memory use.
- Disable history recall or compaction independently without deleting Chat messages or summaries.
- Disable Hermes synchronization without affecting normal Chat.
- Switch off the SQLite Chat feature flag only while the preserved legacy JSON store remains an acceptable rollback source. Do not alternate writers between JSON and SQLite after new production-only messages have accumulated without first reconciling them.
- Forget is intentionally irreversible for active content and frozen snapshot copies; audit events preserve only non-sensitive metadata.

## Release conclusion

MEM-15 and the staged repository rollout are complete. Repository completion does not assert that every flag is enabled in production; deployment adoption remains an operational decision.
