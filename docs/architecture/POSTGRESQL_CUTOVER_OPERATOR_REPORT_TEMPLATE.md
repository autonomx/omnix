# PostgreSQL Cutover Operator Report Template

Do not commit a completed copy containing private installation data, credentials, dumps, BlobStore contents, or secret-bearing migration bundles.

## Deployment

- Software SHA:
- Schema version:
- Repository path (private report only):
- Python environment:
- Maintenance window start/end (UTC):
- Environment summary without secrets:

## Legacy backup and import

- Legacy backup manifest path:
- Legacy backup manifest SHA-256:
- Migration bundle path:
- Migration bundle SHA-256:
- Import run ID:
- Discovered counts:
- Imported counts:
- Failed counts:
- Import verification result:

## Coordinated recovery

- Recovery generation ID:
- PostgreSQL dump reference without credentials:
- BlobStore backup reference:
- Blob manifest SHA-256:
- Manifest asset count/bytes:
- Disposable database restore result:
- Restored migration verification:
- Restored deterministic smoke result:
- Disposable BlobStore verification result:
- Missing/mismatched/unexpected blob counts:

## Authority transitions

Record timestamp, source state, target state, software SHA, schema, import run, generation, operator note, and acknowledgement for each transition.

| UTC timestamp | From | To | Evidence/decision |
| --- | --- | --- | --- |
| | `legacy_preflight` | `imported_unverified` | |
| | `imported_unverified` | `imported_verified` | |
| | `imported_verified` | `postgresql_activated_frozen` | |
| | `postgresql_activated_frozen` | `postgresql_open_for_writes` | |
| | `postgresql_open_for_writes` | `postgresql_stabilized` | |

## Acceptance and stabilization

- Deterministic smoke-test summary:
- Provider-backed acceptance summary or documented unavailability:
- Stabilization window start/end (UTC):
- Monitoring summary:
- Latest authoritative revision:
- Final authority state:
- Rollback decision, if applicable:
- Unresolved risks:

## Safety confirmation

- [ ] No secrets were printed or committed.
- [ ] No private backup, dump, BlobStore content, or completed private report was committed.
- [ ] Legacy sources are immutable archives only.
- [ ] No runtime writer targets SQLite, JSONL, or mutable JSON authority.
- [ ] PostgreSQL and restored BlobStore evidence refer to the same recovery generation.
