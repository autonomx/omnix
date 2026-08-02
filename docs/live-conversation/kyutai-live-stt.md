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
- selected language
- capabilities: continuous words, word timestamps, semantic endpointing, delayed flush, authoritative final transcription, and client audio replay

The browser freezes the negotiated provider and audio format for the complete capture epoch. A reconnect that advertises a different contract is rejected rather than mixing sample indexes or providers mid-utterance.

Kyutai decoder state is connection-local. The `client_audio_replay` capability therefore tells the browser to retain acknowledged segment audio until the authoritative result commits. After a reconnect, Omnix waits for `session_ready`, applies any cached completed results, and then replays every still-pending Kyutai segment from its original `captureStartSample`. Parakeet continues pruning acknowledged frames because its existing backend owns persistent segment state and result replay.

Parakeet advertises its actual capabilities through the same handshake while continuing to use 16,000 Hz PCM and the existing finalize-and-transcribe implementation.

## Reproducible upstream setup

The adapter was implemented against these upstream artifacts:

- Unmute repository commit: `c49982eb3aeaf76633dfe4155fa3b8dcb5b3d962`
- Moshi configuration: `services/moshi-server/configs/stt.toml` at that commit
- Kyutai model repository: `kyutai/stt-1b-en_fr-candle`
- Verified `model.safetensors` revision: `9196091a4634222b56cfd9ba9c22a37b208dd304`
- Verified `model.safetensors` SHA-256: `b9e97c53229dce728d65c76bfa892f7b563c69d671899f0ebc6518582dddec6f`

The upstream configuration uses six delayed ASR tokens, batch size one, and `/api/asr-streaming`. Pin the tokenizer and Mimi/audio-tokenizer artifacts in the deployment manifest as well; do not rely on moving Hugging Face defaults.

From a checkout of the pinned Unmute commit, the upstream compose service is named `stt` and runs:

```text
worker --config configs/stt.toml
```

The upstream compose file keeps the service on its internal Docker network at port `8080`. To run the Omnix adapter on the host, add a local compose override such as:

```yaml
services:
  stt:
    ports:
      - "8090:8080"
```

Then start the pinned STT service:

```bash
git checkout c49982eb3aeaf76633dfe4155fa3b8dcb5b3d962
docker compose -f docker-compose.yml -f docker-compose.omnix-stt.yml up --build stt
```

Start the Omnix adapter separately:

```bash
python src/kyutai_stt_runtime.py
```

The adapter defaults to port `5202` and upstream URL `ws://127.0.0.1:8090`, allowing it to run beside the current Parakeet service on `5201`.

## Provider and language selection

Configure the live-chat STT service URL to use the Kyutai adapter only for an explicit proof-of-concept session:

```text
http://127.0.0.1:5202?language=en
http://127.0.0.1:5202?language=fr
```

The browser converts the URL to `/ws/transcribe` while preserving only the `language` query parameter. Other query parameters are discarded. The negotiated language is then frozen with the rest of the capture contract.

### Environment variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `KYUTAI_STT_URL` | `ws://127.0.0.1:8090` | Upstream moshi-server base URL |
| `KYUTAI_STT_API_KEY` | `public_token` | `kyutai-api-key` header |
| `OMNIX_STT_PORT` | `5202` | Omnix adapter port |
| `OMNIX_LIVE_STT_LANGUAGE` | `en` | Default session language when the URL does not select one |
| `KYUTAI_STT_CONNECT_TIMEOUT_SECONDS` | `5` | Upstream ready timeout |
| `KYUTAI_STT_FLUSH_TIMEOUT_SECONDS` | `3` | Delayed-state flush timeout |
| `KYUTAI_STT_HEALTH_PROBE_MAX_AGE_SECONDS` | `5` | Maximum age of a cached successful upstream health probe |
| `KYUTAI_ENDPOINT_CANDIDATE_THRESHOLD` | `0.75` | Observational endpoint candidate threshold |
| `KYUTAI_STT_BREAKER_FAILURES` | `3` | Failures required to open the circuit |
| `KYUTAI_STT_BREAKER_WINDOW` | `5` | New-session attempt window |
| `KYUTAI_STT_BREAKER_COOLDOWN_SECONDS` | `60` | Initial open-circuit cooldown |

## PR 2 behavior

This proof of concept does not automatically commit a turn from Kyutai's endpoint score. It emits:

- `partial`
- `word` with start and end timestamps
- `endpoint_score`
- `endpoint_candidate`
- `flush_started`
- `flush_completed`
- `flush_cancelled`

The existing browser silence/finalization path remains authoritative during this stage. When Omnix sends `finalize`, the bridge queues the action behind preceding audio, pads any incomplete frame, submits zero frames to advance Kyutai's delayed decoder state, waits for the model timeline to catch up, and then publishes the normal Omnix `result_available` payload.

The browser receive loop and provider action worker are independent. A `cancel_flush` message can therefore be read while the worker is waiting for delayed model state. Cancellation wakes the flush immediately and marks the failed source sequence so later accepted results are not permanently blocked.

Audio is processed through a stateful streaming resampler so interpolation state and sample counts remain continuous across browser audio chunks.

Each Kyutai result includes provider identity and metrics:

- flush wall time
- modeled delayed time
- standard real-time factor (`wall time / modeled audio time`)
- total finalization time

## Runtime diagnostics

Negotiation, session restoration, timestamped words, endpoint scores, endpoint candidates, flush lifecycle, provider finals, and provider errors are emitted through Omnix's existing `omnix:assistant-voice-perf` event channel.

These events include identities, timing, probabilities, capabilities, language, and character counts, but not raw transcript text. Existing diagnostics consumers can therefore record Kyutai performance without adding a second telemetry path or leaking spoken content.

## Health and fallback

`GET /healthz` performs or reuses a recent real upstream connection probe. A newly started adapter with no reachable `moshi-server` reports `ok: false`; an open or half-open circuit is not reported healthy.

The breaker opens after three failed new-session attempts within five attempts. Protocol, schema, configuration, and authentication failures are treated as non-transient and can open it immediately. While open, new Kyutai sessions are rejected so the caller can select Parakeet before starting a new capture epoch. After the cooldown, one half-open probe is allowed. Providers are never switched in the middle of an utterance.

## Resource limits

The bridge enforces:

- maximum decoded audio-frame size of two seconds
- maximum audio per segment of 15 seconds
- maximum open segments per connection
- bounded provider action queue
- bounded completed-result replay cache

Malformed base64, partial PCM samples, sample gaps, identity changes, and invalid finalize ranges produce normalized `segment_error` responses rather than reaching the upstream model.

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
- reconnect recovery rate
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
