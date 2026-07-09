# Character Mode Stage 2 rehearsal results

Status: not yet run against the deployment.

Do not paste prompts, model output, memory contents, synthetic markers, access credentials, or private data into this document. Generated JSON reports under `resources/data/test-results/` remain ignored runtime artifacts.

## Deployment

| Field | Value |
|---|---|
| Date | Pending |
| Operator | Pending |
| `main` SHA | Pending |
| Gateway URL | Pending |
| Provider | Pending |
| Model | Pending |
| Maya character ID | Pending |
| Alex character ID | Pending |
| Run ID | Pending |

## Flags

| Flag | Required Stage 2 value | Observed |
|---|---:|---:|
| `OMNIX_CHARACTER_MODE_ENABLED` | `1` | Pending |
| `OMNIX_CHARACTER_MEMORY_ENABLED` | `1` | Pending |
| `OMNIX_CHAT_MEMORY_ENABLED` | `1` | Pending |
| `OMNIX_CHARACTER_SHARED_MEMORY_ENABLED` | `0` | Pending |
| `OMNIX_CHARACTER_HERMES_SYNC_ENABLED` | `0` | Pending |

## Automated reports

| Artifact | Decision | Notes |
|---|---|---|
| Prepare report | Pending | Expected `needs_review` until restart |
| Restart-verification report | Pending | Must be `pass` |

## Automated metrics

| Metric | Result |
|---|---:|
| Prepare first streamed text chunk | Pending |
| Restart first streamed text chunk | Pending |
| Selected Maya memory count | Pending |
| Maya snapshot record count | Pending |
| Memory-policy context switches | Pending |

## Owner isolation

| Check | Result | Content-free note |
|---|---|---|
| Maya listing excludes Alex | Pending | |
| Maya listing excludes System Assistant | Pending | |
| Alex listing excludes Maya | Pending | |
| System Assistant listing excludes characters | Pending | |
| Maya snapshot contains Maya fixture | Pending | |
| Maya snapshot excludes Alex/System fixtures | Pending | |
| Provider metadata reports Maya owner | Pending | |
| Provider selected IDs exclude foreign owners | Pending | |

## Read-only enforcement

| Check | Result | Content-free note |
|---|---|---|
| `read_memory=true` | Pending | |
| `write_memory=false` | Pending | |
| `shared_memory_access=none` | Pending | |
| Candidate-shaped message creates no suggestion | Pending | |
| Explicit remember command returns `mutated=false` | Pending | |
| Management write returns HTTP `403` | Pending | |
| Approved record IDs unchanged | Pending | |
| Pending candidate IDs unchanged | Pending | |

## Context and persistence

| Check | Result | Content-free note |
|---|---|---|
| Memory-off creates a new segment | Pending | |
| Memory-off clears snapshot and provider memory context | Pending | |
| Read-only re-enable creates a new segment | Pending | |
| Read-only re-enable creates a fresh owner snapshot | Pending | |
| Segment survives restart | Pending | |
| Identity hash survives restart | Pending | |
| Snapshot ID/revision survive restart | Pending | |
| Post-restart prompt remains owner-isolated | Pending | |

## Forget and cleanup

| Check | Result | Content-free note |
|---|---|---|
| Maya forget invalidates Maya snapshot item | Pending | |
| Maya forget preserves Alex record | Pending | |
| Maya forget preserves System Assistant record | Pending | |
| Refreshed Maya snapshot excludes forgotten record | Pending | |
| Three synthetic records removed | Pending | |
| Four temporary setup/control sessions removed | Pending | |

## Browser confirmation

| Check | Result | Content-free note |
|---|---|---|
| Maya Stage 2 badge visible | Pending | |
| Read on / write off / shared none visible | Pending | |
| No pending suggestion appears | Pending | |
| Explicit remember is rejected | Pending | |
| Memory toggle preserves identity and changes context | Pending | |
| System Assistant does not display character memory | Pending | |

## Decision

- [ ] `pass` — Stage 2 read-only character memory is approved for this deployment.
- [ ] `blocked` — rollback and remediation are required.
- [ ] `needs review` — one or more checks remain incomplete.

Decision owner: Pending

Decision date: Pending

Follow-up issue/PR: Pending
