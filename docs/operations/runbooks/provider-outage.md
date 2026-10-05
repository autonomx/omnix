# Provider outage and open circuit

Every LLM provider and model-service call goes through a pooled client with
retries and a circuit breaker.

## Symptoms

- `OmnixProviderFailing` (more than 20% of a client's calls fail) or
  `OmnixProviderCircuitOpen`.
- Chat, research or speech requests fail with 502/503 and a code such as
  `market_data_failed` or `image_service_unreachable`.

## Dashboards and metrics

- Omnix overview: *Provider attempts by outcome*, *Provider response p95*.
- `omnix_provider_calls_total{client, outcome}`: `5xx`, `transport_error`
  (no response) or `circuit_open` (refused without being sent);
  `omnix_provider_retries_total`.

## Diagnosis

1. Which client? The `client` label is the provider (`lmstudio`,
   `openrouter`, ...) or service (`tts-service`, `stt-service`, `hermes`).
2. `transport_error`: the endpoint is down or unreachable (local service not
   started, network). `5xx`: the provider is failing. `4xx` rising:
   credentials or quota (401/403/429).
3. Model services: their own `/health`; their errors carry a `request_id` that
   matches the gateway's log lines.
4. The logs carry the cause the response hides (search the code, for example
   `market_data_failed`).

## Remediation

- Local service down: start it (launcher or service process) and confirm its
  `/health`.
- Hosted provider down: switch the session or feature to another configured
  provider; the circuit closes on its own after its cooldown when the provider
  recovers.
- Credentials: rotate the provider key ([Secret rotation](secret-rotation.md)).

## Verification

- `circuit_open` stops increasing and the failure ratio falls under 20%.
