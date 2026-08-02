# Kyutai live STT proof of concept

This integration adds an optional Omnix-compatible adapter for Kyutai's streaming speech-to-text service. It is intentionally additive: Parakeet remains the default and its existing segmented scheduling/finalization path is unchanged.

## Architecture

```text
Browser
  -> existing Omnix /ws/transcribe JSON protocol
  -> kyutai_stt_runtime.py
  -> persistent MessagePack WebSocket
  -> Kyutai moshi-server /api/asr-streaming
```

The browser-facing protocol keeps Omnix ownership of capture epochs, segment identity, sequence ordering, result replay, stale-final rejection, and accepted-final routing. Kyutai-specific `prs[2]` values are normalized to provider-neutral `endpoint_score` messages.

## Negotiated capture contract

The adapter sends this information in the initial `ready` message:

- provider: `kyutai`
- protocol: `segmented-v1`
- sample rate: 24,000 Hz
- recommended frame size: 1,920 samples (80 ms)
- encoding: little-endian PCM16
- capabilities: continuous words, word timestamps, semantic endpointing, delayed flush, and authoritative final transcription

The browser freezes the negotiated provider and audio format for the complete capture epoch. A reconnect that advertises a different contract is rejected rather than mixing sample indexes or providers mid-utterance.

Parakeet now advertises its actual capabilities through the same handshake while continuing to use 16,000 Hz PCM and the existing finalize-and-transcribe implementation.

## Runtime setup

Run Kyutai's `moshi-server` separately, using the low-delay English/French STT configuration from the Unmute project. The supplied Unmute configuration points at `kyutai/stt-1b-en_fr-candle`, uses six delayed ASR tokens, and serves the streaming endpoint at `/api/asr-streaming`.

Start the Omnix adapter:

```bash
python src/kyutai_stt_runtime.py
```

The adapter defaults to port `5202` so it can run alongside the current Parakeet service on `5201`. Configure the live-chat STT service URL to use `http://127.0.0.1:5202` for an opt-in Kyutai session.

### Environment variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `KYUTAI_STT_URL` | `ws://127.0.0.1:8090` | Upstream moshi-server base URL |
| `KYUTAI_STT_API_KEY` | `public_token` | `kyutai-api-key` header |
| `OMNIX_STT_PORT` | `5202` | Omnix adapter port |
| `OMNIX_LIVE_STT_LANGUAGE` | `en` | Default session language |
| `KYUTAI_STT_CONNECT_TIMEOUT_SECONDS` | `5` | Upstream ready timeout |
| `KYUTAI_STT_FLUSH_TIMEOUT_SECONDS` | `3` | Delayed-state flush timeout |
| `KYUTAI_ENDPOINT_CANDIDATE_THRESHOLD` | `0.75` | Observational endpoint candidate threshold |
| `KYUTAI_STT_BREAKER_FAILURES` | `3` | Failures required to open the circuit |
| `KYUTAI_STT_BREAKER_WINDOW` | `5` | New-session attempt window |
| `KYUTAI_STT_BREAKER_COOLDOWN_SECONDS` | `60` | Initial open-circuit cooldown |

## PR 2 behavior

This proof of concept does not automatically commit a turn from Kyutai's endpoint score. It emits:

- `partial`
- `endpoint_score`
- `endpoint_candidate`
- `flush_started`
- `flush_completed`
- `flush_cancelled`

The existing browser silence/finalization path remains authoritative during this stage. When Omnix sends `finalize`, the adapter pads any incomplete frame, submits zero frames to advance Kyutai's delayed decoder state, waits for the model timeline to catch up, and then publishes the normal Omnix `result_available` payload.

Each Kyutai result includes provider metrics:

- flush wall time
- modeled delayed time
- flush real-time factor
- total finalization time

## Health and fallback

`GET /healthz` reports recent readiness, last error, supported languages, negotiated audio format, and circuit-breaker state.

The breaker opens after three failed new-session attempts within five attempts. While open, new Kyutai sessions are rejected so the caller can select Parakeet before starting a new capture epoch. After the cooldown, one half-open probe is allowed. Providers are never switched in the middle of an utterance.

## Language scope

The initial low-delay model is limited to English and French. Unsupported languages are rejected before connecting upstream. Japanese and other languages must continue using the existing provider until a suitable streaming model is added.

## Evaluation plan

Do not use Parakeet as accuracy ground truth. Evaluate both systems against human transcripts using a labeled set containing:

- short commands and questions
- hesitation and self-correction
- incomplete clauses
- background noise and interruptions
- English and French accents
- NPC names, locations, inventory items, numbers, and negation

Track at minimum:

- Kyutai and Parakeet WER against human labels
- entity, proper-name, number, negation, and command-intent accuracy
- first-word latency
- endpoint early/late timing
- false and missed endpoint rates
- flush wall time and real-time factor
- GPU memory
- LLM TTFT regression
- TTS first-PCM regression

Use three separate runs: offline replay for accuracy, isolated live-provider performance, and a production-like contention test with STT, LLM, and TTS active. Full dual-provider shadowing on one GPU can distort the latency measurement.

Raw audio capture for evaluation must remain disabled by default and require an explicit local evaluation setting with bounded retention.

## Current limitations

- Kyutai is opt-in and is not the default provider.
- Endpoint candidates are observational; server-owned automatic endpoint commitment belongs to the next rollout stage.
- The adapter does not add LLM speculation.
- Phrase-at-a-time Qwen TTS remains the larger response-onset floor.
- Running moshi-server on the same RTX 4090 as the LLM and TTS must be benchmarked before production use.
