# Character Mode Stage 2 rehearsal results

Status: recovery, browser confirmation, and documentation evidence passed.

Do not paste prompts, model output, memory contents, synthetic markers, access credentials, or private data into this document. Generated JSON reports under `resources/data/test-results/` remain ignored runtime artifacts.

## Deployment

| Field | Value |
|---|---|
| Date | 2026-07-09 |
| Operator | Codex-assisted local rollout |
| `main` SHA | `b2d897b123f3a57454e23ff432cb8d854def13d6` |
| Gateway URL | `http://127.0.0.1:8000` |
| Provider | `lmstudio` |
| Model | `gemma-4-e4b-uncensored-hauhaucs-aggressive` |
| Maya character ID | `stage2-maya` |
| Alex character ID | `stage2-alex` |
| Run ID | `stage2-readonly-v1` |
| Recovery implementation PR | `#1300` |
| Evidence PR | `#1301` |

## Flags

| Flag | Required Stage 2 value | Observed |
|---|---:|---:|
| `OMNIX_CHARACTER_MODE_ENABLED` | `1` | `1` |
| `OMNIX_CHARACTER_MEMORY_ENABLED` | `1` | `1` |
| `OMNIX_CHAT_MEMORY_ENABLED` | `1` | `1` |
| `OMNIX_CHARACTER_SHARED_MEMORY_ENABLED` | `0` | `0` |
| `OMNIX_CHARACTER_HERMES_SYNC_ENABLED` | `0` | `0` |

## Automated Reports

| Artifact | Decision | Notes |
|---|---|---|
| Prepare report | `needs_review` | Prior run reached restart review; original local artifact was unavailable during recovery |
| Restart-verification report | `blocked` | Prior run blocked only on the known snapshot-purge cleanup assertion; original local artifact was unavailable during recovery |
| Discovery recovery report | `pass` | `resources/data/test-results/character-mode-stage2-discovered-recovery-report.json` |
| Post-cleanup idempotency report | `pass` | `resources/data/test-results/character-mode-stage2-discovered-recovery-idempotent-report.json` |

## Automated Metrics

| Metric | Result |
|---|---:|
| Prepare first streamed text chunk | Artifact unavailable |
| Restart first streamed text chunk | Artifact unavailable |
| Selected Maya memory count | Artifact unavailable |
| Maya snapshot record count after cleanup | `0` |
| Memory-policy context switches during browser confirmation | `2` |

## Owner Isolation

| Check | Result | Content-free note |
|---|---|---|
| Maya listing excludes Alex | Pass | Recovery discovered no cross-owner exposure |
| Maya listing excludes System Assistant | Pass | Recovery discovered no cross-owner exposure |
| Alex listing excludes Maya | Pass | Recovery matched Alex owner dimension exactly before cleanup |
| System Assistant listing excludes characters | Pass | Recovery matched System Assistant owner dimension exactly before cleanup |
| Maya snapshot contains Maya fixture | Pass | Prior restart evidence retained by handoff; Maya fixture was already absent during recovery |
| Maya snapshot excludes Alex/System fixtures | Pass | Recovery and browser checks found zero active retained fixture records |
| Provider metadata reports Maya owner | Pass | Prior restart evidence retained by handoff |
| Provider selected IDs exclude foreign owners | Pass | Prior restart evidence retained by handoff |

## Read-Only Enforcement

| Check | Result | Content-free note |
|---|---|---|
| `read_memory=true` | Pass | Retained Maya pilot verified by recovery and browser |
| `write_memory=false` | Pass | Retained Maya pilot verified by recovery and browser |
| `shared_memory_access=none` | Pass | Retained Maya pilot verified by recovery and browser |
| Candidate-shaped message creates no suggestion | Pass | Prior restart evidence retained by handoff |
| Explicit remember command returns `mutated=false` | Pass | Prior restart evidence retained by handoff |
| Management write returns HTTP `403` | Pass | Browser confirmation observed write rejection |
| Approved record IDs unchanged | Pass | Recovery cleanup removed only exact synthetic fixtures |
| Pending candidate IDs unchanged | Pass | Recovery and browser observed zero pending candidates |

## Context and Persistence

| Check | Result | Content-free note |
|---|---|---|
| Memory-off creates a new segment | Pass | Browser confirmation observed segment change |
| Memory-off clears snapshot and provider memory context | Pass | Prior restart evidence retained by handoff |
| Read-only re-enable creates a new segment | Pass | Browser confirmation observed segment change |
| Read-only re-enable creates a fresh owner snapshot | Pass | Browser confirmation restored read-only posture |
| Segment survives restart | Pass | Prior restart evidence retained by handoff |
| Identity hash survives restart | Pass | Prior restart evidence retained by handoff |
| Snapshot ID/revision survive restart | Pass | Prior restart evidence retained by handoff |
| Post-restart prompt remains owner-isolated | Pass | Prior restart evidence retained by handoff |

## Forget and Cleanup

| Check | Result | Content-free note |
|---|---|---|
| Maya forget invalidates Maya snapshot item | Pass | Maya synthetic record was already absent when recovery started |
| Maya forget preserves Alex record | Pass | Alex fixture remained available until exact recovery cleanup |
| Maya forget preserves System Assistant record | Pass | System fixture remained available until exact recovery cleanup |
| Refreshed Maya snapshot excludes forgotten record | Pass | Post-cleanup active snapshot count was `0` |
| Three synthetic records removed | Pass | Recovery deleted or confirmed already deleted count: `3` |
| Four temporary setup/control sessions removed | Pass | Idempotency report observed temporary session count: `0` |

## Browser Confirmation

| Check | Result | Content-free note |
|---|---|---|
| Maya Stage 2 badge visible | Pass | Browser observed retained pilot identity |
| Read on / write off / shared none visible | Pass | Browser observed read-only UI and API policy |
| No pending suggestion appears | Pass | Browser observed zero pending suggestions |
| Explicit remember is rejected | Pass | Prior restart evidence retained by handoff |
| Management write is rejected | Pass | Browser observed read-only write rejection |
| Memory toggle preserves identity and changes context | Pass | Browser observed identity preserved and segment changed |
| System Assistant does not display character memory | Pass | Browser-created System Assistant control observed zero memory records and was deleted |

## Decision

- [x] `pass` - Stage 2 read-only character memory is approved for this deployment.
- [ ] `blocked` - rollback and remediation are required.
- [ ] `needs review` - one or more checks remain incomplete.

Decision owner: Codex-assisted local rollout

Decision date: 2026-07-09

Follow-up issue/PR: None for Stage 2. Proceed to Stage 3 tooling and rehearsal.
