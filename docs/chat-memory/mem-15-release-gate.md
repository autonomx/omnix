# MEM-15 — Adversarial release gate

Status: implementation complete pending exact-head required checks and merge.

## Release scope

MEM-0 through MEM-14 established the Chat memory architecture, contracts, prompt assembly, persistence, snapshot lifecycle, approved-memory injection, management UI, explicit commands, pending suggestions, consolidation policy, FTS5 history recall, long-session compaction, optional Hermes synchronization, and server-enforced privacy settings.

MEM-15 adds the final adversarial integration gate and process-local concurrency hardening. Chat read-modify-write operations are serialized, snapshot refresh participates in the same mutation lock, and JSON fallback persistence uses atomic temporary-file replacement. SQLite remains the recommended durable Chat store.

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

## Rollout

Recommended initial production settings:

```text
OMNIX_CHAT_SQLITE_STORE_ENABLED=1
OMNIX_CHAT_MEMORY_ENABLED=0
OMNIX_CHAT_MEMORY_SUGGESTIONS_ENABLED=0
OMNIX_CHAT_HISTORY_RECALL_ENABLED=0
OMNIX_CHAT_COMPACTION_ENABLED=0
OMNIX_HERMES_MEMORY_SYNC_ENABLED=0
```

Enable features independently after confirming migration counts and the Memory view. A safe sequence is SQLite Chat storage, curated read-only memory, explicit saves and management, pending suggestions, history recall, compaction, and finally Hermes synchronization.

## Rollback

- Disable any feature through persisted settings or its environment override; stored records and migrated history are retained.
- Disable `OMNIX_CHAT_MEMORY_ENABLED` to restore the legacy provider payload shape for sessions without active memory use.
- Disable history recall or compaction independently without deleting Chat messages or summaries.
- Disable Hermes synchronization without affecting normal Chat.
- Switch off the SQLite Chat feature flag only while the preserved legacy JSON store remains an acceptable rollback source. Do not alternate writers between JSON and SQLite after new production-only messages have accumulated without first reconciling them.
- Forget is intentionally irreversible for active content and frozen snapshot copies; audit events preserve only non-sensitive metadata.

## Final merge requirement

MEM-15 is complete only after both required GitHub Actions workflows pass on the exact PR head and the PR is squash-merged into `rpg`:

- RPG Phase 0 architecture compliance
- RPG deterministic PR gates
