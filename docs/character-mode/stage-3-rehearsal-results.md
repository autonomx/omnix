# Character Mode Stage 3 rehearsal results

Status: automated restart verification and browser confirmation passed locally; code check-in pending.

Do not paste prompts, model output, memory contents, synthetic markers, access credentials, or private data into this document. Generated JSON reports under `resources/data/test-results/` remain ignored runtime artifacts.

## Deployment

| Field | Value |
|---|---|
| Date | 2026-07-09 |
| Operator | Codex-assisted local rollout |
| Local branch | `tmp-char-stage3-preflight` |
| Code state | Local working tree after `d4bfb977a`; final check-in pending |
| Gateway URL | `http://127.0.0.1:8000` |
| Provider | `lmstudio` |
| Model | `gemma-4-e4b-uncensored-hauhaucs-aggressive` |
| Maya character ID | `stage3-maya` |
| Alex character ID | `stage3-alex` |
| Run ID | `stage3-write-v1` |
| Tooling PR | Draft `#1302`; not merged per local-completion-first instruction |

## Flags

| Flag | Required Stage 3 value | Observed |
|---|---:|---:|
| `OMNIX_CHARACTER_MODE_ENABLED` | `1` | `1` |
| `OMNIX_CHARACTER_MEMORY_ENABLED` | `1` | `1` |
| `OMNIX_CHAT_MEMORY_ENABLED` | `1` | `1` |
| `OMNIX_CHAT_MEMORY_SUGGESTIONS_ENABLED` | `1` | `1` |
| `OMNIX_CHARACTER_SHARED_MEMORY_ENABLED` | `0` | `0` |
| `OMNIX_CHARACTER_HERMES_SYNC_ENABLED` | `0` | `0` |

## Automated Reports

| Artifact | Decision | Notes |
|---|---|---|
| Prepare report | `needs_review` | `resources/data/test-results/character-mode-stage3-prepare-report.json` |
| Restart-verification report | `pass` | `resources/data/test-results/character-mode-stage3-final-report.json` |

## Automated Metrics

| Metric | Result |
|---|---:|
| Prepare first streamed text chunk | `53.377 ms` |
| Explicit approved record count | `1` |
| Pending candidate count | `1` |
| Approved candidate record count | `1` |
| Refreshed Maya snapshot record count | `3` |
| Restart first streamed text chunk | Not measured by Stage 3 final harness |

## Write Controls

| Check | Result | Content-free note |
|---|---|---|
| Explicit remember writes to Maya owner | Pass | Automated and browser fetch observed `character/stage3-maya` owner |
| Write-only control can save memory | Pass | Automated report observed management save with read disabled |
| Write-only control exposes no readable memory context | Pass | Automated report observed no provider memory context |
| Inferred content creates one pending candidate | Pass | Automated and browser confirmation each observed one pending candidate |
| Pending candidate is not prompt-eligible | Pass | Automated and browser confirmation observed exclusion before approval/refresh |
| Approval creates one approved record | Pass | Automated and browser confirmation observed one approved record |
| Approved record becomes selectable only after refresh | Pass | Automated and browser confirmation observed activation only after refresh |
| Rejected candidate leaves pending queue | Pass | Automated and browser confirmation observed rejection exclusion |

## Owner Isolation

| Check | Result | Content-free note |
|---|---|---|
| Maya listing excludes Alex | Pass | Automated owner-isolation check passed |
| Maya listing excludes System Assistant | Pass | Automated owner-isolation check passed |
| Alex listing excludes Maya | Pass | Automated and browser isolation checks observed zero cross-owner records |
| System Assistant listing excludes characters | Pass | Browser isolation check observed zero cross-owner records |
| Shared memory remains `none` | Pass | Automated session policy check passed |

## Restart and Cleanup

| Check | Result | Content-free note |
|---|---|---|
| Read/write policy survives restart | Pass | Final report `restart.persistence` passed |
| Character identity survives restart | Pass | Final report `restart.persistence` passed |
| Approved records survive restart | Pass | Final report `restart.persistence` passed |
| Refreshed snapshot survives restart | Pass | Final report observed snapshot revision `2` |
| Synthetic records removed | Pass | Final cleanup deleted `3` records |
| Resolved candidate rows removed | Pass | Final cleanup deleted `2` candidate rows |
| Temporary sessions removed | Pass | Final cleanup deleted `3` sessions |

## Browser Confirmation

| Check | Result | Content-free note |
|---|---|---|
| Maya Stage 3 badge visible | Pass | Browser observed selected Stage 3 pilot identity |
| Read on / write on / shared none visible | Pass | Browser observed `Read and save` posture and API read/write policy |
| Explicit save appears under Maya owner | Pass | Browser fetch observed `character/stage3-maya` owner |
| Pending suggestion appears but remains inactive | Pass | Browser observed one pending suggestion and no active selection before approval |
| Approved suggestion activates only after refresh | Pass | Browser observed inactive before refresh and active after refresh |
| Rejected suggestion remains excluded | Pass | Browser observed rejected candidate absent from pending list |
| System Assistant does not display character memory | Pass | Browser-created System Assistant control observed zero Maya records and was deleted |
| Alex session does not display Maya memory | Pass | Browser-created Alex control observed zero Maya records and was deleted |

## Decision

- [x] `pass` - Stage 3 explicit character memory is approved for this deployment.
- [ ] `blocked` - rollback and remediation are required.
- [ ] `needs review` - one or more checks remain incomplete.

Decision owner: Codex-assisted local rollout

Decision date: 2026-07-09

Follow-up issue/PR: Commit local fixes and update draft PR `#1302` after remaining local work is complete.
