# Service level objectives

Initial objectives for one Omnix installation, set from the WP-6.8 multihost
measurements (`docs/measurements/multihost-topology-2026-10-01.json`: job
submit p95 26 ms, job list p95 33 ms, live-call first audio 27 ms with fake
models) with headroom for real models. Revisit them after a month of
production metrics.

Each objective names the metric it is read from (catalog:
[METRICS.md](METRICS.md)). The alert rules are in
`deploy/observability/alerts.yml` and the dashboard in
`deploy/observability/dashboards/omnix-overview.json`.

| Objective | Target | Window | Measured by |
|---|---|---|---|
| API availability | 99.5% of requests not 5xx (local install); 99.9% hosted | 30 days | `omnix_http_requests_total`, `status_class="5xx"` over all |
| Chat admission | p95 < 50 ms | 5 minutes | `omnix_http_request_duration_seconds`, `route="/api/chat/sessions/{session_id}/messages"`, `method="POST"` (the route returns once the turn is admitted; generation runs as a job) |
| Provider first response | p95 per client within its class: local models < 2 s, hosted models < 5 s | 15 minutes | `omnix_provider_response_seconds` by `client` (time to response headers, which for streaming providers is the first token; see below) |
| Speech first audio | p95 < 1.5 s from the end of the user's speech | 15 minutes | `omnix_speech_turn_seconds`, `stage="first_audio"` (live speech sessions) |
| Interactive job queue age | oldest waiting `chat.generate` job < 30 s | 5 minutes | `omnix_jobs_oldest_waiting_age_seconds{job_type="chat.generate"}` (the oldest job bounds the p95) |
| Background job queue age | oldest waiting job of any type < 5 minutes | 15 minutes | `omnix_jobs_oldest_waiting_age_seconds` |
| Event delivery | outbox events delivered within 1 s; oldest undelivered < 30 s | 5 minutes | `omnix_outbox_oldest_unpublished_age_seconds` |

## What the measurements do not cover yet

- First token: `omnix_provider_response_seconds` times the response headers.
  Providers that stream send headers with the first token; a provider that
  buffers its reply makes this the full response time, which overstates it.
- TTS first audio for live voice calls is in the call's own diagnostics and
  release gates, not in the metrics registry (METRICS.md, Planned).
- Event delivery to browsers: the outbox age covers the relay; the SSE
  stream's own lag is not measured.

## Error budget

At 99.5%, a 30-day window allows 0.5% of requests to fail: for 1 million
requests, 5,000. The alerts page on a fast burn (the 1-hour 5xx ratio above
14.4 times the budget rate, which spends 2% of the month's budget in an hour)
and ticket on a slow burn (the 6-hour ratio above 6 times the budget rate).
