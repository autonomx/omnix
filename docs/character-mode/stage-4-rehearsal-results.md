# Character Mode Stage 4 rehearsal results

Status: automated prepare, restart verification, and cleanup passed locally.

Generated reports contain only IDs, hashes, counts, policies, statuses, and timings. Prompts, model output, memory content, transcripts, and credentials are excluded.

## Deployment

| Field | Value |
|---|---|
| Date | 2026-07-09 |
| Gateway | `http://127.0.0.1:8000` |
| Provider | `lmstudio` |
| Model | `gemma-4-e4b-uncensored-hauhaucs-aggressive` |
| Character | `stage4-maya` |
| Run ID | `stage4-shared-readonly-v1` |

## Flags

| Flag | Observed |
|---|---:|
| `OMNIX_CHARACTER_MODE_ENABLED` | `1` |
| `OMNIX_CHARACTER_MEMORY_ENABLED` | `1` |
| `OMNIX_CHAT_MEMORY_ENABLED` | `1` |
| `OMNIX_CHARACTER_SHARED_MEMORY_ENABLED` | `1` |
| `OMNIX_CHARACTER_HERMES_SYNC_ENABLED` | `0` |

## Automated evidence

| Check | Result |
|---|---|
| Prepare report | `needs_review` |
| Final restart report | `pass` |
| Allowlisted normal shared record selected | Pass, count `1` |
| Non-allowlisted category excluded | Pass |
| Sensitive record excluded | Pass |
| Session-scoped record excluded | Pass |
| Character shared create/edit attempts | Pass, HTTP `403` |
| Shared-off control | Pass, no memory context |
| Off/on context boundaries | Pass, `2` segment switches |
| Restart persistence | Pass |
| Synthetic records removed | Pass, count `4` |
| Temporary sessions removed | Pass, count `3` |

Prepare first streamed text chunk was `2727.509 ms`; restart first streamed text chunk was `2579.545 ms`.

## Decision

- [x] `pass` - Stage 4 read-only shared System Assistant memory is approved for this deployment.
- [ ] `blocked` - rollback and remediation are required.
- [ ] `needs review` - restart verification remains incomplete.

Next stage: governed cloned voice and live-call pilot. Character Hermes remains disabled.
