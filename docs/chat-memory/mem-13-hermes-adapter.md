# MEM-13 — Hermes memory adapter

Status: implementation complete pending exact-head required checks.

Hermes synchronization is optional and disabled by default through `OMNIX_HERMES_MEMORY_SYNC_ENABLED`. The adapter recognizes only `USER.md` and `MEMORY.md` in the configured Hermes memory directory. It never reads scratchpad, execution-log, or arbitrary tool files.

Imported lines are filtered for secret and instruction-injection markers and are persisted only as pending `source=hermes`, `trust_level=unverified_agent` candidates. Re-imports are idempotent.

Exports use an atomic managed block. Only active, normal-sensitivity, user-approved, scope-compatible Omnix records are exported. Hermes-origin records, session-only records, pending candidates, and untrusted records are excluded to prevent feedback loops. Existing unmanaged Hermes text is preserved.

Missing or offline Hermes storage reports a non-fatal status and does not affect normal Chat.
