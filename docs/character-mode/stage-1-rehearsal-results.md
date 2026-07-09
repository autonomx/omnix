# Character Mode Stage 1 rehearsal results

Status: passed on the local deployment on 2026-07-09.

Do not paste prompts, transcripts, memory contents, cloned-voice audio, private consent evidence, or access credentials into this document. Generated JSON reports under `resources/data/test-results/` are runtime artifacts and remain ignored by Git.

## Deployment

| Field | Value |
|---|---|
| Date | 2026-07-09 |
| Operator | Local deployment operator; result reported by the repository owner |
| `main` SHA | `be9d3deed14e35da71f08b263771f2fe522cf132` |
| Gateway URL | `http://127.0.0.1:8000` |
| Provider | LM Studio |
| Model | `gemma-4-e4b-uncensored-hauhaucs-aggressive` |
| TTS transport | Gateway PCM websocket at `/api/tts/stream/websocket` |
| Character ID | `stage1-maya` |
| Character profile version | `1` |
| Voice asset ID | None; deployment renderer used |

## Flags

| Flag | Required Stage 1 value | Observed |
|---|---:|---:|
| `OMNIX_CHARACTER_MODE_ENABLED` | `1` | `1` |
| `OMNIX_CHARACTER_MEMORY_ENABLED` | `0` | `0` |
| `OMNIX_CHARACTER_SHARED_MEMORY_ENABLED` | `0` | `0` |
| `OMNIX_CHARACTER_HERMES_SYNC_ENABLED` | `0` | `0` |

## Automated reports

| Artifact | Decision | Notes |
|---|---|---|
| Prepare report | `needs_review` | All live preparation checks passed; restart verification remained intentionally pending |
| Restart-verification report | `pass` | Profile, segment, identity hash, renderer selection, and memory-off state survived restart |

## Automated metrics

| Metric | Result |
|---|---:|
| Runtime preload | `2.786 ms` |
| First streamed text chunk | `3439.552 ms` |
| First streamed audio chunk | `1312.174 ms` |
| First audio chunk bytes | `4800` |
| Response character count | `52` |

## Identity and isolation evidence

- Gateway health passed.
- The versioned `stage1-maya` profile resolved through the trusted server path.
- Selecting a renderer voice without a character remained System Assistant mode.
- Text and live-call runtime used profile version `1` and the same effective identity hash.
- System Assistant and Character Mode transitions created distinct persisted context segments.
- Character memory started at zero records and zero candidates and remained unchanged.
- No memory snapshot was loaded or created.
- Restart verification returned `pass` for the persisted profile, active segment, effective identity hash, voice selection, and memory-off state.

## Browser/operator confirmation

The operator reported the complete Stage 1 rehearsal as passed after the successful prepare and restart-verification runs. Individual browser checklist observations were not attached to the content-free JSON evidence and are therefore not reproduced here.

## Voice governance

No cloned voice was used during this rehearsal, so cloned-voice ownership, consent, provenance, allowed-use, source-hash, and deletion-state checks were not applicable.

## Decision

- [x] `pass` — Stage 1 identity without memory is approved for this local deployment.
- [ ] `blocked` — rollback and remediation are required.
- [ ] `needs review` — one or more live or browser checks remain incomplete.

Decision owner: Local deployment operator

Decision date: 2026-07-09

Next stage: Character Mode Stage 2 read-only character-memory pilot.
