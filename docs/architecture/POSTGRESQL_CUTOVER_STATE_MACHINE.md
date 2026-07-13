# PostgreSQL Cutover and Rollback State Machine

Omnix records authority progression separately from the compatibility `mode` field. The durable authority states are:

```text
legacy_preflight
imported_unverified
imported_verified
postgresql_activated_frozen
postgresql_open_for_writes
postgresql_stabilized
rollback_recorded
```

## Transition requirements

- `imported_verified` requires a completed import whose stored verification reports `ok: true`.
- `postgresql_activated_frozen` requires a verified coordinated PostgreSQL-plus-BlobStore backup generation.
- `postgresql_open_for_writes` requires explicit operator acknowledgement that the legacy backup is no longer a lossless rollback target after new writes are accepted.
- `postgresql_stabilized` records completion of the stabilization window and the latest known authoritative revision.
- Invalid skips or backward transitions fail closed.

## Rollback boundary

Before PostgreSQL opens for writes, a matching legacy installation and software revision can remain a lossless rollback target. After PostgreSQL accepts new writes, ordinary recovery is forward repair or restoration of a coordinated PostgreSQL-plus-BlobStore generation. Recording a return to legacy authority after that point requires an explicit destructive acknowledgement and an operator note; it never happens automatically.

Every transition records source state, target state, import run, backup generation, software revision, schema version, operator note, destructive acknowledgement, and metadata in `omnix_cutover_transitions`. Runtime compatibility mode remains `postgresql` for all active PostgreSQL states, preserving existing startup behavior while exposing the stronger authority state through diagnostics.