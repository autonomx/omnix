# PostgreSQL Completion Evidence

**Branch:** `agent/postgresql-completion-c0-c8`  
**Pull request:** `#1362`  
**Base:** `main` at `ed80ec86e69a21044f0557ca507aedf4814fa1cb`

The corrective program advances only after all four required provider-free workflows succeed on the exact phase head:

- PostgreSQL persistence gates;
- RPG Phase 0 architecture compliance;
- Live Chat hardening gates;
- RPG deterministic PR gates, including continuous 1,000-turn public apply-turn endurance.

## Verified phase heads

| Phase | Exact head | Phase 0 run | PostgreSQL run | Live Chat run | Deterministic run |
|---|---|---:|---:|---:|---:|
| C0 | `aa3087f44f047ff6d2568e09328d36b999c565c7` | 4268 | 186 | 458 | 4531 |
| C1 | `df00272da0521665f11a774e8efb7b20305a284a` | 4276 | 194 | 466 | 4539 |
| C2 | `e698a23b768c068341fd4f382d37e9531339b4b2` | 4289 | 207 | 479 | 4552 |
| C3 | `ca523adaec7c92018b4df17be4c9057083ac9fec` | 4291 | 209 | 481 | 4554 |
| C4 | `2284ed5b4cff986ab9392bed3a2aee701194bc4a` | 4298 | 216 | 488 | 4561 |
| C5 | `4c409b364dc51e8824861a0063579cd5dae33031` | 4303 | 221 | 493 | 4566 |
| C6 | `895151a0e0e9c3182ef633427deb37e25e6c14bb` | 4307 | 225 | 497 | 4570 |
| C7 | `9fdc08054eb0d9d14854d22b9124174d0902a750` | 4312 | 230 | 502 | 4575 |
| C8 | `4374619b2d8d192330b6c45c62c7658536e1f1a3` | 4315 | 233 | 505 | 4578 |

The reconciled completion documentation is reverified once more on its own final exact head before the pull request leaves draft state.

## Implemented contracts

- C0: `docs/CENTRALIZED_POSTGRESQL_COMPLETION_FIXES_ROADMAP.md`
- C1: `docs/architecture/POSTGRESQL_TRANSACTION_SCHEMA_CONTRACT.md`
- C2: `docs/architecture/POSTGRESQL_OUTBOX_DELIVERY_CONTRACT.md`
- C3: migration `0012_tenant_integrity_security.sql` and `security_audit.py`
- C4: `docs/architecture/POSTGRESQL_COORDINATED_RECOVERY.md`
- C5: `docs/architecture/POSTGRESQL_CURRENT_TOPOLOGY_CORRECTNESS.md`
- C6: `docs/architecture/POSTGRESQL_CUTOVER_STATE_MACHINE.md`
- C7: `docs/architecture/POSTGRESQL_DATA_LIFECYCLE_CAPACITY.md`
- C8: `src/tests/persistence/test_postgresql_completion_evidence.py` and this evidence ledger

## Failure corrections

- C2 initially failed because existing RPG atomic writers omitted the new outbox `event_key`; migration-level sequence defaults preserved compatibility while explicit new writers retain globally unique keys.
- C3 initially failed because existing participant writers did not pass `workspace_id`; a database trigger now derives tenant scope from the campaign before enforcing the composite relationship.
- C5 initially failed because an optional node filter had an indeterminate PostgreSQL parameter type; explicit text casts fixed the query without weakening filtering.

All fixes were committed to the same branch and reverified before the next phase began.

## Final policy

GitHub Actions remain provider-free. No API keys, live model servers, external provider calls, or local GPU requirements are introduced into CI. Local provider-backed quality and latency acceptance remains explicit operator evidence.