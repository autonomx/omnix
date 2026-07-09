# Character Mode Stage 3 rehearsal results

Status: pending deployment rehearsal.

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
| Maya character ID | `stage3-maya` |
| Alex character ID | `stage3-alex` |
| Run ID | `stage3-write-v1` |
| Tooling PR | Pending |

## Flags

| Flag | Required Stage 3 value | Observed |
|---|---:|---:|
| `OMNIX_CHARACTER_MODE_ENABLED` | `1` | Pending |
| `OMNIX_CHARACTER_MEMORY_ENABLED` | `1` | Pending |
| `OMNIX_CHAT_MEMORY_ENABLED` | `1` | Pending |
| `OMNIX_CHAT_MEMORY_SUGGESTIONS_ENABLED` | `1` | Pending |
| `OMNIX_CHARACTER_SHARED_MEMORY_ENABLED` | `0` | Pending |
| `OMNIX_CHARACTER_HERMES_SYNC_ENABLED` | `0` | Pending |

## Automated Reports

| Artifact | Decision | Notes |
|---|---|---|
| Prepare report | Pending | `resources/data/test-results/character-mode-stage3-prepare-report.json` |
| Restart-verification report | Pending | `resources/data/test-results/character-mode-stage3-final-report.json` |

## Automated Metrics

| Metric | Result |
|---|---:|
| Prepare first streamed text chunk | Pending |
| Explicit approved record count | Pending |
| Pending candidate count | Pending |
| Approved candidate record count | Pending |
| Refreshed Maya snapshot record count | Pending |
| Restart first streamed text chunk | Pending |

## Write Controls

| Check | Result | Content-free note |
|---|---|---|
| Explicit remember writes to Maya owner | Pending | Pending |
| Write-only control can save memory | Pending | Pending |
| Write-only control exposes no readable memory context | Pending | Pending |
| Inferred content creates one pending candidate | Pending | Pending |
| Pending candidate is not prompt-eligible | Pending | Pending |
| Approval creates one approved record | Pending | Pending |
| Approved record becomes selectable only after refresh | Pending | Pending |
| Rejected candidate leaves pending queue | Pending | Pending |

## Owner Isolation

| Check | Result | Content-free note |
|---|---|---|
| Maya listing excludes Alex | Pending | Pending |
| Maya listing excludes System Assistant | Pending | Pending |
| Alex listing excludes Maya | Pending | Pending |
| System Assistant listing excludes characters | Pending | Pending |
| Shared memory remains `none` | Pending | Pending |

## Restart and Cleanup

| Check | Result | Content-free note |
|---|---|---|
| Read/write policy survives restart | Pending | Pending |
| Character identity survives restart | Pending | Pending |
| Approved records survive restart | Pending | Pending |
| Refreshed snapshot survives restart | Pending | Pending |
| Synthetic records removed | Pending | Pending |
| Resolved candidate rows removed | Pending | Pending |
| Temporary sessions removed | Pending | Pending |

## Browser Confirmation

| Check | Result | Content-free note |
|---|---|---|
| Maya Stage 3 badge visible | Pending | Pending |
| Read on / write on / shared none visible | Pending | Pending |
| Explicit save appears under Maya owner | Pending | Pending |
| Pending suggestion appears but remains inactive | Pending | Pending |
| Approved suggestion activates only after refresh | Pending | Pending |
| Rejected suggestion remains excluded | Pending | Pending |
| System Assistant does not display character memory | Pending | Pending |
| Alex session does not display Maya memory | Pending | Pending |

## Decision

- [ ] `pass` - Stage 3 explicit character memory is approved for this deployment.
- [ ] `blocked` - rollback and remediation are required.
- [ ] `needs review` - one or more checks remain incomplete.

Decision owner: Pending

Decision date: Pending

Follow-up issue/PR: Pending
