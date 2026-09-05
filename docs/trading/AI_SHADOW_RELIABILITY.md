# AI Shadow Reliability Boundary

The Finviz AI-shadow arms are research-only. They never own AUTO PAPER or live-order authority. Deterministic strategy evaluation, risk checks, paper-order creation, and protection remain separate from this reliability layer.

## Why this exists

The September 3, 2026 shadow run exposed two dominant failure classes:

- Codex app-server emitted reconnect/error notifications during a sustained websocket/backend outage. Some notifications were retryable (`willRetry=true`) but Omnix treated every `error` event as terminal.
- AI-shadow requested JSON through prompt instructions, then parsed it strictly. Codex supports native `turn/start.outputSchema`, so prompt-only JSON was unnecessarily fragile.

Repeated polling also retried failed causal market minutes before durable error checkpoints were added.

## Provider protocol hardening

`app.providers.codex_reliability` installs narrow adapters over `ChatGPTCodexProvider`:

- retryable Codex `error` notifications with `willRetry=true` are consumed as transport progress and the same turn continues;
- terminal `error` and `turn/failed` notifications remain fail-closed;
- Omnix `response_format=json_schema` is projected onto Codex `turn/start.outputSchema`;
- `json_object` receives a generic native object schema as a compatibility improvement;
- existing provider process lifecycle, thread identity, tool bridge, tracing, and timeout ownership remain unchanged.

## Dedicated trading-research provider lane

`app.trading.ai_shadow_reliability` clones the configured foreground LLM provider into a separate long-lived provider instance for AI-shadow research.

This isolates background trading research from Chat, Agent, routing, and other foreground LLM traffic. A slow or unhealthy trading turn therefore cannot monopolize the foreground Codex app-server lock.

The dedicated provider is retired and reconstructed once after a terminal transport failure. The retry is bounded by one total-call deadline; there is no unbounded transport loop.

## Native output contract and repair

Production AI-shadow calls use the Pydantic-generated `AIShadowBatchResponse` JSON Schema as the native structured-output contract.

Responses are classified into distinct failure classes:

- `ai_shadow_output_empty`
- `ai_shadow_output_syntax_error`
- `ai_shadow_output_truncated`
- `ai_shadow_output_schema_error`
- `ai_shadow_output_duplicate_decisions`
- `ai_shadow_output_unexpected_decisions`
- `ai_shadow_output_missing_decisions`

A formatting/schema/decision-set failure gets exactly one bounded regeneration attempt. The retry does not reuse malformed model text; it regenerates the complete response from the original causal evidence with a repair instruction. If the second response fails, the persisted monitor error is `ai_shadow_output_repair_exhausted` and includes the initial and final failure classes.

## Transport recovery and circuit breaker

A terminal transport failure gets one provider-process recovery attempt. If both attempts fail, the error is `ai_shadow_transport_exhausted` and the shared AI-shadow provider circuit opens.

Backoff is exponential and capped:

1. 2 minutes
2. 5 minutes
3. 10 minutes
4. 10 minutes for subsequent failures

While open, AI-shadow evaluations fail locally with `ai_shadow_provider_circuit_open`; no external LLM request is made. Deterministic trading continues normally.

`app.trading.ai_shadow_circuit_persistence` persists open/recovered state as research-only `ai_shadow_provider_health` strategy events. On restart, the circuit restores an unexpired open interval and its failure count. Persistence is best-effort: a database failure cannot block deterministic trading.

## Causal-minute checkpointing

The AI-shadow monitor separately persists complete/error batch checkpoints per policy and causal market minute. Once a minute has failed, 15-second monitor polls do not re-call the provider for that same causal minute.

The provider circuit operates above those checkpoints and limits calls across new minutes during a sustained provider outage.

## Authority boundary

None of these components can create trading authority. Provider-health events and AI-shadow results always remain research-only with `execution_authority=false`.

The AI layer may propose normalized shadow actions for comparison. Deterministic code continues to own position-state normalization and simulated shadow fills, and the separate deterministic AUTO PAPER runtime remains the only paper-order authority.

## Required tests

The Trading CI gate runs both the trading suite and the Codex reliability fault tests. Coverage includes:

- `willRetry=true` reconnect notification followed by successful turn completion;
- terminal Codex error still failing closed;
- native `outputSchema` projection;
- malformed JSON repair;
- schema validation repair;
- missing-decision classification;
- dedicated provider isolation;
- bounded transport recovery;
- a simulated 30-minute provider outage with bounded external calls;
- durable circuit open/recovery state without execution authority.
