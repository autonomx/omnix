# PostgreSQL Cutover and Rollback State Machine

Omnix records authority progression separately from the compatibility `mode` field:

```text
legacy_preflight
  -> imported_unverified
  -> imported_verified
  -> postgresql_activated_frozen
  -> postgresql_open_for_writes
  -> postgresql_stabilized
```

Any state may record `rollback_recorded`, subject to the destructive-acknowledgement boundary below. Skips and backward transitions fail closed.

## Transition requirements

- `imported_unverified` requires a completed legacy import run and records its source hash.
- `imported_verified` requires that run's stored verification to report `ok: true`.
- `postgresql_activated_frozen` requires a verified coordinated PostgreSQL-plus-BlobStore recovery generation and an operator note.
- `postgresql_open_for_writes` requires an operator note plus `--write-reopen-acknowledged`.
- `postgresql_stabilized` requires an operator note and `--latest-authoritative-revision` after a real stabilization window.
- Post-write `rollback_recorded` requires an operator note plus `--destructive-rollback-acknowledged`.

Every transition records source and target states, import run, recovery generation, exact software revision, schema version, operator note, acknowledgements, metadata, and timestamp in `omnix_cutover_transitions`.

## Runtime policy

| Authority state | Diagnostics/import | Normal runtime start and mutations |
| --- | --- | --- |
| `legacy_preflight` | controlled legacy import only | blocked |
| `imported_unverified` | controlled import/inspection | blocked |
| `imported_verified` | inspection | blocked |
| `postgresql_activated_frozen` | read-only inspection | blocked |
| `postgresql_open_for_writes` | allowed | allowed |
| `postgresql_stabilized` | allowed | allowed |
| `rollback_recorded` | read-only inspection | blocked |

The shared authority policy is enforced at PostgreSQL runtime startup and the default unit-of-work mutation boundary. Import tooling uses a separate, explicit pre-cutover operation. There is no automatic legacy fallback.

A truly empty fresh installation is initialized coherently with both `mode = postgresql` and `authority_state = postgresql_stabilized`; nonempty legacy installations are never auto-activated.

## Rollback boundary

Before writes reopen, a matching immutable legacy installation may still be lossless. After PostgreSQL accepts writes, prefer forward repair or restoration of a coordinated PostgreSQL-plus-BlobStore generation. Returning to legacy then accepts data loss and must be explicitly acknowledged and audited.
