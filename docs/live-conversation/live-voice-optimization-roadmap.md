# Live voice optimization roadmap

This document tracks the Nemotron transcript + Parakeet Realtime EOU + LM Studio + Faster Qwen live-voice path. The goal is to reduce speech-end-to-first-playback latency without weakening turn-boundary correctness or allowing speculative side effects.

## Current STT path

The managed launcher runs `src/nemotron_eou_stt_server.py` on port 5201. Nemotron is authoritative for transcript text and Parakeet Realtime EOU supplies authoritative end-of-turn evidence. The browser negotiates capabilities from the server and uses `authoritative_eou` rather than a provider name to decide whether the fast EOU/speculation path is available.

Default browser configuration:

```text
VITE_ASSISTANT_STT_URL=http://127.0.0.1:5201?language=en&authority=auto&endpoint_threshold=0.5
```

The generic `/authorityz` readiness contract remains because the hybrid STT server implements it. There is no alternate live-STT transport in the managed launcher.

## Phase A: accepted-first TTS scheduling

Implemented on the draft branch:

- accepted speech remains the highest-priority TTS lane
- hidden speculative TTS yields at a smaller provider codec chunk boundary (2 steps by default)
- accepted/promoted synthesis keeps the production request shape
- a superseded speculative stream can release the non-concurrent Faster Qwen lane at a finer safe boundary
- scheduler diagnostics expose queue wait, acquisition, active duration, cancellation, and preemption

Configuration:

```text
OMNIX_LIVE_TTS_SPECULATIVE_CHUNK_STEPS=2
```

Set it back to `4` for an A/B control run.

## Phase B: LM Studio stateful Responses transport

Stateful `/v1/responses` reuse is implemented for accepted live-voice turns only. Omnix still builds the full authoritative prompt every turn; provider state is reused only when the exact prompt prefix, session, and resolved model all match.

Configuration:

```text
OMNIX_LIVE_LMSTUDIO_STATEFUL_RESPONSES=true
OMNIX_LIVE_LMSTUDIO_RESPONSE_STATE_TTL_SECONDS=900
```

The managed launcher defaults stateful Responses to `true` regardless of STT provider. An explicit false value remains an operator opt-out. If `/v1/responses` is unavailable before text is emitted, Omnix invalidates provider state and falls back to the existing chat-completions stream.

Relevant gateway events:

```text
live_chat_lmstudio_response_state_resolved
live_chat_lmstudio_response_state_updated
live_chat_lmstudio_responses_fallback
live_chat_lmstudio_first_provider_text
live_chat_lmstudio_first_client_chunk
live_chat_lmstudio_stream_completed
```

## Phase C: dialogue-context EOT

Already implemented:

- recent assistant-question context can shorten a clearly complete one-word answer
- arbitrary one-word speech, hesitation, corrections, and unfinished clauses remain conservative
- when `authoritative_eou` is negotiated, late Nemotron partial revisions do not restart the full semantic watchdog

## RTX 4090 A/B matrix

Use the same microphone, character, voice, hybrid STT configuration, and utterance script for every row.

| Run | LLM | Stateful Responses | Spec TTS steps | Purpose |
| --- | --- | --- | --- | --- |
| A | current small model | off | 4 | compatibility baseline |
| B | current small model | on | 2 | validate state reuse and instrumentation |
| C | larger target model | off | 2 | measure uncached larger-model TTFT |
| D | larger target model | on | 2 | measure state/cache benefit |

For each run, record at least 10 completed turns and calculate speech-end to first playback, STT finalization, final to first token, first token to first audio/playback, provider first-text latency, Responses state-hit rate, cached-input-token ratio, TTS lane wait, provider-to-first-PCM latency, underruns, and VRAM use.

## Next optimization boundary

Revisit endpointing only if speech-end-to-final remains the dominant contributor after a clean stateful-Responses A/B. Any endpoint change must preserve unfinished-clause and resumed-speech correctness. Keep provider-specific transport details out of the controller; decisions should continue to use negotiated capabilities such as `authoritative_eou`.

## Expected next hardware provenance

Record:

```text
git_sha=<exact PR head>
git_dirty=false
stt_provider=nemotron_parakeet_eou
OMNIX_LIVE_LMSTUDIO_STATEFUL_RESPONSES=true
OMNIX_LIVE_TTS_SPECULATIVE_CHUNK_STEPS=2
```

Do not compare a run as a clean before/after measurement when local provenance does not match the intended PR head.
