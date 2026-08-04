# Kyutai low-latency live voice rollout

This branch implements the complete five-PR low-latency voice rollout while keeping `main` unchanged. Parakeet remains the default unless the frontend is explicitly configured to use Kyutai.

## Architecture

```text
Microphone
  -> Omnix negotiated /ws/transcribe protocol
  -> Kyutai adapter on port 5202
  -> moshi-server HTTP build readiness at /api/build_info
  -> persistent MessagePack websocket at /api/asr-streaming
  -> endpoint candidate / authoritative final
  -> side-effect-free LLM speculation
  -> accepted final transcript
  -> normal chat persistence
  -> incremental Qwen TTS clause streaming
  -> persistent PCM websocket + adaptive AudioWorklet buffer
```

The browser-facing STT protocol keeps Omnix ownership of capture epochs, segment identities, sequence ordering, result replay, stale-final rejection, accepted-final routing, and provider fallback decisions.

## PR 1: negotiated provider-neutral STT

The server sends a `ready` contract containing:

- provider and protocol
- sample rate and recommended frame size
- encoding
- selected language
- capabilities
- configuration version

The browser freezes the negotiated contract for the entire capture epoch. A reconnect that advertises a different provider, sample rate, language, or capability set is rejected rather than mixing incompatible sample indexes.

Parakeet continues using 16,000 Hz PCM and its existing segmented finalize-and-transcribe path. Kyutai negotiates 24,000 Hz PCM with 1,920-sample frames.

## PR 2: Kyutai streaming adapter

The adapter connects to the pinned Moshi worker at `ws://127.0.0.1:8090/api/asr-streaming`, matching Kyutai's official delayed-streams client and the path configured by `configs/stt.toml`. Before attempting that MessagePack WebSocket handshake, the adapter checks `http://127.0.0.1:8090/api/build_info`.

This produces a two-stage readiness contract:

1. `/api/build_info` confirms that the Rust worker has finished compiling, starting, and loading enough to answer HTTP.
2. `/api/asr-streaming` must then return the expected MessagePack `Ready` frame.

While the build endpoint is unavailable, readiness is reported as `starting` and no WebSocket attempt is recorded against the circuit breaker. This matters on the first Docker build because the pinned container health check allows a startup period of up to ten minutes.

After readiness, the adapter normalizes:

- partial transcript updates
- timestamped words
- semantic endpoint scores and candidates
- delayed-state flush lifecycle
- authoritative final transcripts

`KYUTAI_STT_PATH` defaults to `/api/asr-streaming`. It remains configurable for future Moshi or proxy variants.

Kyutai decoder state is connection-local. The `client_audio_replay` capability therefore tells the browser to retain acknowledged segment audio until a final result is accepted. After reconnect, Omnix applies cached completed results and replays every still-pending segment from its original sample offset.

The bridge also provides:

- cancellable delayed-state flushes
- a serialized provider action worker
- bounded queues and segment sizes
- malformed audio rejection
- a rolling circuit breaker
- two-stage HTTP and WebSocket readiness probing
- provider and latency diagnostics without raw transcript text

## PR 3: authoritative Kyutai endpointing

Kyutai can become authoritative only after a pre-session gate succeeds. The browser calls:

```text
GET http://127.0.0.1:5202/authorityz?language=en&mode=test
GET http://127.0.0.1:5202/authorityz?language=en&mode=auto
```

The gate requires:

- English or French
- a successful Moshi `/api/build_info` response
- a successful `/api/asr-streaming` `Ready` handshake
- closed circuit breaker
- a recent successful ready handshake, indicating a warm model

`authority=test` enables authoritative endpoint commitment for local latency testing after readiness and warm-model checks. It does not claim that production quality gates have passed.

`authority=auto` additionally requires both environment gates:

```text
KYUTAI_STT_QUALITY_GATE_PASSED=true
KYUTAI_STT_CONTENTION_GATE_PASSED=true
```

The production thresholds encoded by the gate are:

- median speech-end to first audio below 750 ms
- p95 speech-end to first audio below 1,000 ms
- false endpoint rate below 3%
- missed endpoint rate below 5%
- interruption to silence below 250 ms
- TTS-underrun turns below 2%
- no more than 15% p95 regression in downstream LLM/TTS latency under contention

A configured fallback is selected before microphone capture begins. Providers are never switched after partial processing has started. When a qualified Kyutai endpoint candidate crosses the configured threshold, the existing Omnix finalization protocol is invoked and captured continuation audio is held until the accepted final establishes the next turn boundary.

## PR 4: safe LLM speculation

A stable Kyutai endpoint candidate may start a private LLM generation before the final transcript returns.

Speculative generation is deliberately side-effect-free:

- no user message is persisted
- no assistant message is persisted
- tools are disabled
- memory writes are disabled
- generated text is not shown or spoken before acceptance

The speculative response is reusable only when the final accepted transcript has the exact same normalized words. Differences in case, punctuation, whitespace, and curly apostrophes are allowed; word additions, removals, and substitutions invalidate it. Candidates containing unresolved correction or hesitation markers are not speculated.

When the final matches, the normal chat stream is satisfied from the already-running speculative stream and persistence occurs exactly once through the acceptance route. When it does not match, the speculative request is aborted and the ordinary final-transcript chat request runs.

Disable speculation with:

```text
VITE_LIVE_SPECULATION_ENABLED=false
```

## PR 5: incremental TTS and adaptive playback

The current Qwen provider exposes streaming audio generation for a complete synthesis request, but it does not expose a native decoder session that accepts additional text after decoding has begun. The rollout therefore implements two clearly distinguished capability levels:

1. **Application-level incremental text ingestion:** LLM stream text is committed to TTS continuously using stable clauses, a 12-character minimum, and a 140 ms maximum text-commit deadline.
2. **Native decoder text append:** reported separately by `/api/tts/live-call/capabilities`; it remains false for the current Faster Qwen3 TTS provider unless a provider-native incremental session API is added.

The complete assistant response no longer needs to finish before TTS starts. Each committed clause uses the existing Qwen audio generator, while one persistent live-session websocket, one AudioContext, one AudioWorklet, generation ownership, cancellation, and delivery tracking remain active across the response.

Playback buffering is adaptive. The default policy starts near 260 ms, raises start and rebuffer targets after underruns, and cautiously lowers them after stable turns. The policy is kept locally and emits diagnostics on the existing voice-performance event channel.

Disable adaptive buffering with:

```text
VITE_LIVE_TTS_ADAPTIVE_BUFFER=false
```

Inspect TTS capabilities at:

```text
GET /api/tts/live-call/capabilities
```

Important fields include:

- `incremental_text_ingest`
- `text_commit_deadline_ms`
- `streaming_audio_chunks`
- `native_decoder_text_append`
- `cancellation_generations`
- `adaptive_playback_buffer`

## Reproducible Kyutai upstream setup

The adapter was implemented against:

- Unmute commit `c49982eb3aeaf76633dfe4155fa3b8dcb5b3d962`
- `services/moshi-server/configs/stt.toml` at that commit
- model repository `kyutai/stt-1b-en_fr-candle`
- `model.safetensors` revision `9196091a4634222b56cfd9ba9c22a37b208dd304`
- verified model SHA-256 `b9e97c53229dce728d65c76bfa892f7b563c69d671899f0ebc6518582dddec6f`

From the pinned Unmute checkout, create `docker-compose.omnix-stt.yml`:

```yaml
services:
  stt:
    ports:
      - "8090:8080"
```

Start the upstream service:

```bash
git checkout c49982eb3aeaf76633dfe4155fa3b8dcb5b3d962
docker compose -f docker-compose.yml -f docker-compose.omnix-stt.yml up --build stt
```

Start the Omnix adapter from the Omnix branch:

```bash
python src/kyutai_stt_runtime.py
```

The adapter defaults to port `5202`, upstream URL `ws://127.0.0.1:8090`, upstream path `/api/asr-streaming`, and can run beside Parakeet on `5201`.

## Exact local latency-test configuration

For an English RTX 4090 test with authoritative Kyutai and pre-session Parakeet fallback, start Vite with:

```powershell
$env:VITE_ASSISTANT_STT_URL="http://127.0.0.1:5202?language=en&authority=test&endpoint_threshold=0.75&fallback=http%3A%2F%2F127.0.0.1%3A5201"
$env:VITE_LIVE_SPECULATION_ENABLED="true"
$env:VITE_LIVE_TTS_ADAPTIVE_BUFFER="true"
npm run web:dev
```

For French, replace `language=en` with `language=fr`.

For production-gated selection, use `authority=auto` only after setting the two release-evidence environment variables on the Kyutai adapter process.

Before opening Live Chat, verify the stages in order:

```powershell
Invoke-RestMethod http://127.0.0.1:8090/api/build_info
Invoke-RestMethod http://127.0.0.1:5202/healthz
Invoke-RestMethod "http://127.0.0.1:5202/authorityz?language=en&mode=test"
Invoke-RestMethod http://127.0.0.1:8000/api/tts/live-call/capabilities
```

The first command may fail during the initial Docker build or model startup. Do not repeatedly force the WebSocket probe while it is unavailable; the launcher panel refreshes automatically. The exact gateway port may differ in the local Omnix setup.

## Runtime diagnostics

Listen for:

```javascript
window.addEventListener(
  'omnix:assistant-voice-perf',
  event => console.log('[voice-perf]', event.detail),
);
```

Relevant stages include:

- `stt_authority_selected`
- `stt_endpoint_candidate`
- `stt_endpoint_committed`
- `stt_flush_started`
- `stt_flush_completed`
- `stt_provider_final`
- `llm_speculation_started`
- `llm_speculation_cancelled`
- `llm_speculation_reused`
- `llm_speculation_committed`
- `tts_capabilities_negotiated`
- `tts_adaptive_buffer_applied`
- `tts_adaptive_buffer_updated`

These events contain timing, identities, probabilities, capabilities, and character counts but not raw spoken transcript text.

## Environment variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `KYUTAI_STT_URL` | `ws://127.0.0.1:8090` | Upstream moshi-server URL |
| `KYUTAI_STT_PATH` | `/api/asr-streaming` | Moshi MessagePack ASR WebSocket path |
| `KYUTAI_STT_API_KEY` | `public_token` | `kyutai-api-key` header |
| `KYUTAI_STT_BUILD_INFO_TIMEOUT_SECONDS` | `2` | Timeout for the startup `/api/build_info` probe |
| `OMNIX_STT_PORT` | `5202` | Omnix adapter port |
| `OMNIX_STT_CORS_ORIGINS` | local Vite origins | Allowed authority-preflight origins |
| `OMNIX_LIVE_STT_LANGUAGE` | `en` | Default language when URL has none |
| `KYUTAI_STT_CONNECT_TIMEOUT_SECONDS` | `5` | Upstream ready timeout |
| `KYUTAI_STT_FLUSH_TIMEOUT_SECONDS` | `3` | Delayed-state flush timeout |
| `KYUTAI_STT_HEALTH_PROBE_MAX_AGE_SECONDS` | `5` | Successful health-probe cache age |
| `KYUTAI_STT_WARM_MAX_AGE_SECONDS` | `120` | Maximum age of ready handshake for authority |
| `KYUTAI_ENDPOINT_CANDIDATE_THRESHOLD` | `0.75` | Bridge candidate threshold |
| `KYUTAI_STT_QUALITY_GATE_PASSED` | false | Required for `authority=auto` |
| `KYUTAI_STT_CONTENTION_GATE_PASSED` | false | Required for `authority=auto` |
| `KYUTAI_STT_BREAKER_FAILURES` | `3` | Failures required to open breaker |
| `KYUTAI_STT_BREAKER_WINDOW` | `5` | New-session attempt window |
| `KYUTAI_STT_BREAKER_COOLDOWN_SECONDS` | `60` | Initial breaker cooldown |

## Evaluation procedure

Do not use Parakeet as accuracy ground truth. Evaluate both providers against human transcripts containing commands, hesitation, self-correction, incomplete clauses, noise, interruptions, accents, NPC names, numbers, inventory terms, and negation.

Run three separate suites:

1. offline replay for transcript and endpoint accuracy
2. isolated Kyutai live-provider latency
3. production-like contention with Kyutai, the local LLM, and Qwen TTS loaded on the RTX 4090

Track:

- WER and command-intent accuracy
- entity, proper-name, number, and negation accuracy
- first-word latency
- endpoint early/late timing
- false and missed endpoint rates
- speech-end to accepted final
- LLM speculative hit and cancellation rates
- LLM TTFT
- TTS text-commit to first PCM
- speech-end to first audible response
- interruption to silence
- underruns and adaptive-buffer values
- GPU memory and downstream p95 regressions

Raw audio capture for evaluation must remain disabled by default and require an explicit local evaluation setting with bounded retention.

## Current limitations

- Kyutai is still opt-in; Parakeet remains the default configuration.
- `authority=test` is for local measurement, not production promotion.
- `authority=auto` fails closed until quality and contention evidence is explicitly approved.
- Speculation is never allowed to perform tools, memory writes, or other side effects before final-transcript acceptance.
- Qwen TTS now receives LLM text incrementally and streams PCM immediately, but the current provider does not offer native cross-append decoder continuity; this is exposed honestly in the capability contract.
- Real RTX 4090 contention, latency, transcript quality, and interruption measurements still must be run locally before this draft PR is considered release-ready.
