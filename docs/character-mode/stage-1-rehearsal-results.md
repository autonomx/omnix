# Character Mode Stage 1 rehearsal results

Status: not yet run against the deployment.

Do not paste prompts, transcripts, memory contents, cloned-voice audio, private consent evidence, or access credentials into this document. Generated JSON reports under `resources/data/test-results/` are runtime artifacts and remain ignored by Git.

## Deployment

| Field | Value |
|---|---|
| Date | Pending |
| Operator | Pending |
| `main` SHA | Pending |
| Gateway URL | Pending |
| Provider | Pending |
| Model | Pending |
| TTS service/version | Pending |
| Character ID | Pending |
| Voice asset ID | None / Pending |

## Flags

| Flag | Required Stage 1 value | Observed |
|---|---:|---:|
| `OMNIX_CHARACTER_MODE_ENABLED` | `1` | Pending |
| `OMNIX_CHARACTER_MEMORY_ENABLED` | `0` | Pending |
| `OMNIX_CHARACTER_SHARED_MEMORY_ENABLED` | `0` | Pending |
| `OMNIX_CHARACTER_HERMES_SYNC_ENABLED` | `0` | Pending |

## Automated reports

| Artifact | Decision | Notes |
|---|---|---|
| Prepare report | Pending | Expected `needs_review` until restart |
| Restart-verification report | Pending | Must be `pass` to approve Stage 1 |

## Automated metrics

| Metric | Result |
|---|---:|
| Runtime preload | Pending |
| First streamed text chunk | Pending |
| First streamed audio chunk | Pending |
| First audio chunk bytes | Pending |
| Response character count | Pending |

## Browser confirmation

| Check | Result | Content-free note |
|---|---|---|
| Correct character badge | Pending | |
| Character greeting spoken once | Pending | |
| Voice change does not change identity | Pending | |
| Voice-only selection stays System Assistant | Pending | |
| System → character → system context boundaries | Pending | |
| Character memory read remains off | Pending | |
| Character memory write remains off | Pending | |
| No memory snapshot appears | Pending | |
| System Assistant works after Character Mode rollback | Pending | |

## Voice governance

Complete this section only when a cloned voice is used.

| Check | Result |
|---|---|
| Subject/owner recorded | Pending / N/A |
| Creator and source provenance recorded | Pending / N/A |
| Consent granted by authorized operator | Pending / N/A |
| Source SHA-256 present | Pending / N/A |
| `character` allowed use present | Pending / N/A |
| `live_call` allowed use present | Pending / N/A |
| Deletion state active | Pending / N/A |

## Decision

- [ ] `pass` — Stage 1 identity without memory is approved for the selected deployment.
- [ ] `blocked` — rollback and remediation are required.
- [ ] `needs review` — one or more live or browser checks remain incomplete.

Decision owner: Pending

Decision date: Pending

Follow-up issue/PR: Pending
