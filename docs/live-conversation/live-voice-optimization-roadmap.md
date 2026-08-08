# Live voice optimization roadmap

This document continues the Kyutai + LM Studio + Faster Qwen live-voice rollout after the initial five-PR implementation. The goal is to reduce speech-end-to-first-playback latency without weakening turn-boundary correctness or allowing speculative side effects.

## Current evidence boundary

The most recent RTX 4090 validation before these roadmap changes used a small LM Studio model and showed that raw speculative LLM first text was already fast (roughly 76–117 ms), while authoritative endpoint/finalization and first-PCM generation remained much larger contributors. The changes below therefore target endpoint-safe reuse, provider prompt state, and non-concurrent TTS scheduling rather than globally shortening silence thresholds.

No post-roadmap hardware latency improvement is claimed until the exact branch head is retested locally.

## Phase A: accepted-first TTS scheduling

Implemented on the draft branch:

- accepted speech remains the highest-priority TTS lane
- hidden speculative TTS yields at a smaller provider codec chunk boundary (2 steps by default)
- accepted/promoted synthesis keeps the production 4-step request shape
- a superseded speculative stream can therefore release the non-concurrent Faster Qwen lane at a finer safe boundary
- scheduler diagnostics now expose queue wait, acquisition, active duration, cancellation, and preemption

Configuration:

```text
OMNIX_LIVE_TTS_SPECULATIVE_CHUNK_STEPS=2
```

Set it back to `4` for an A/B control run.

Relevant gateway log events:

```text
tts_lane_ticket_enqueued
tts_lane_ticket_acquired
tts_lane_stream_started
speculative_tts_preempt_requested
tts_lane_ticket_released
```

For each accepted turn, compare `wait_ms` on the accepted ticket with the speculative ticket's `active_ms`. If accepted wait remains significant after the 2-step policy, the next TTS phase is cooperative decoder cancellation between codec steps. Do not add lower-level CUDA interruption unless these measurements show that scheduler wait is still material.

## Phase B: LM Studio stateful Responses transport

Implemented on the draft branch for accepted live-voice turns only.

LM Studio's OpenAI-compatible `/v1/responses` endpoint supports `previous_response_id` and assistant messages in an initial request. Omnix uses that state only as an optimization; the normal rendered Omnix prompt remains authoritative.

The state cache is deliberately fail-closed:

1. Omnix builds the full normal provider prompt every turn.
2. The exact role/content prefix before the current user message is fingerprinted locally.
3. A previous LM Studio response is reused only when:
   - the session matches
   - the currently resolved model matches
   - the exact prompt prefix matches the state expected after the prior assistant reply
4. Any character/persona, memory, task, system-prompt, history-window, or model change invalidates the state and sends the full prompt again.
5. Successful accepted replies update the expected prefix and response ID.

Speculative LLM generations do **not** use or advance provider response state. If an accepted speculative turn changes the transcript while the provider state is behind, the next accepted normal turn fails the exact-prefix check and reseeds safely.

Configuration:

```text
OMNIX_LIVE_LMSTUDIO_STATEFUL_RESPONSES=true
OMNIX_LIVE_LMSTUDIO_RESPONSE_STATE_TTL_SECONDS=900
```

The managed launcher enables the first setting by default on this isolated Kyutai test branch. Set it to `false` for a control run. If `/v1/responses` is unavailable before any text is emitted, Omnix invalidates the state and falls back to the existing chat-completions stream.

Relevant gateway events:

```text
live_chat_lmstudio_response_state_resolved
live_chat_lmstudio_response_state_updated
live_chat_lmstudio_responses_fallback
live_chat_lmstudio_first_provider_text
live_chat_lmstudio_first_client_chunk
live_chat_lmstudio_stream_completed
```

On a state hit, inspect:

- `state_hit`
- `input_tokens`
- `cached_input_tokens`
- `prompt_cache_hit_ratio`
- `provider_first_text_ms`
- `first_client_chunk_ms`

LM Studio Responses usage can expose cached input tokens, making this the preferred large-model validation path over inferring cache behavior from wall-clock latency alone.

## Phase C: dialogue-context EOT

Already implemented before Phases A/B:

- a content-free summary of the immediately previous assistant turn records whether it asked a question or created a response obligation
- a one-word answer to that question may use the bounded clear-turn fast path
- arbitrary one-word speech, hesitation, corrections, and unfinished clauses remain conservative

Do not globally lower the semantic wait window until the updated hardware run shows where endpoint latency remains after this context-aware path.

## RTX 4090 A/B matrix

Use the same microphone, character, voice, STT authority mode, and utterance script for every row.

| Run | LLM | Stateful Responses | Spec TTS steps | Purpose |
| --- | --- | --- | --- | --- |
| A | current small model | off | 4 | compatibility baseline |
| B | current small model | on | 2 | validate no regression and instrumentation |
| C | larger target model | off | 2 | measure uncached larger-model TTFT |
| D | larger target model | on | 2 | measure state/cache benefit |

For each run, record at least 10 completed turns and include both short answers and multi-clause questions/statements.

Calculate:

- speech-end to accepted final
- speech-end to first audio
- speech-end to first playback
- final to first token
- first token to first audio/playback
- LLM provider first-text latency
- Responses state-hit rate
- cached-input-token ratio on state hits
- TTS accepted-ticket queue wait
- TTS provider request to first raw PCM
- speculative TTS preemption duration
- underrun rate
- false/missed endpoint observations
- VRAM usage and any contention-related outliers

## Promotion criteria for the next code phase

### Add cooperative Faster Qwen decoder cancellation only if

accepted TTS tickets still wait materially behind superseded speculative generation after the 2-step policy. The vendored streaming generator has codec-step boundaries where a cooperative stop check can be inserted without interrupting an in-flight CUDA kernel.

### Revisit endpointing only if

speech-end-to-final remains the dominant median/p95 contributor after dialogue-context EOT. Any next endpoint change must preserve the unfinished-clause and resumed-speech cases that previously produced false endpoints. A speculative delayed-state flush is not currently safe because the Kyutai flush advances decoder state with zero frames; it must not be used as a non-committing transcript peek without a separate snapshot/rollback contract.

### Promote stateful Responses beyond test mode only if

- exact-prefix state hits are observed on real live turns
- cached input tokens are non-zero on supported LM Studio builds/models
- output remains semantically identical to the full-prompt control for the test corpus
- state invalidates correctly after persona/memory/history changes
- no meaningful TTFT or stability regression appears on state misses

## Expected next hardware provenance

For the next local run, record:

```text
git_sha=<exact PR head>
git_dirty=false
authority=test
endpoint_threshold=0.75
OMNIX_LIVE_LMSTUDIO_STATEFUL_RESPONSES=true
OMNIX_LIVE_TTS_SPECULATIVE_CHUNK_STEPS=2
```

Do not compare the result as a clean before/after latency measurement if the local tree is dirty or the runtime provenance SHA does not match the intended PR head.
