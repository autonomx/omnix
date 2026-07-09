# Character Mode Stage 5 rehearsal results

Status: governed cloned-voice prepare and restart verification passed locally.

## Deployment

| Field | Value |
|---|---|
| Date | 2026-07-09 |
| Voice asset | `voice-cloning:Maya` |
| Consent | User confirmed ownership and approved `character` plus `live_call` use |
| Character | `stage5-maya` |
| Provider | `lmstudio` |
| Model | `gemma-4-e4b-uncensored-hauhaucs-aggressive` |

## Automated evidence

| Check | Result |
|---|---|
| Ownership, consent, provenance, source hash, and uses | Pass |
| Voice-only selection remains System Assistant | Pass |
| Character identity is server resolved | Pass |
| Text and live-call profile version/hash agree | Pass |
| Governed voice resolves for live call | Pass |
| Identity switching creates clean segments | Pass |
| Streamed text | Pass, first token `2524.709 ms` |
| Streamed cloned-voice PCM | Pass, first `4800` bytes at `1315.361 ms` |
| Memory activity during controlled call | Pass, zero records/candidates/snapshots |
| Restart persistence | Pass |
| Temporary sessions removed after evidence capture | Pass, count `2` |

The automated test proves that non-empty PCM was streamed from the governed voice path. It does not claim a human listening assessment of voice quality.

## Deployment defect corrected

The first audio attempt was blocked with `tts_provider_unavailable`. The TTS worker was healthy, but the gateway WebSocket provider lacked the canonical model directory. The launcher now passes `OMNIX_TTS_MODEL_DIR` and `OMNIX_QWEN3_TTS_MODEL_DIR` to the gateway as well as the TTS worker. After launcher restart, gateway model load and graph warmup passed.

## Decision

- [x] `pass` - Stage 5 governed Maya voice and live-call runtime are approved for this deployment.
- [ ] `blocked` - revoke/unlink the voice and remediate before release.
- [ ] `needs review` - restart or audio evidence remains incomplete.

Optional next stage: owner-aware Character Hermes compatibility. It remains disabled until its own pilot passes.
