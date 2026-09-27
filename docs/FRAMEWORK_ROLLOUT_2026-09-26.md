# Framework rollout — 2026-09-26

The nine reported failures are fixed. Real providers passed qualification, and
the native Windows gateway now runs one background worker and two API replicas.
Frontend routing is now enabled and qualified with real providers through port
5173. The remaining routing step from the initial rollout is complete.

The subsequent [framework hardening report](FRAMEWORK_HARDENING_2026-09-26.md)
records the deployed memory lease fix, supported Node runtime, smaller trading
payload, live browser chart fix, restart, and three-minute provider soak. Its
remaining-qualification section supersedes the operational limits below where
those follow-up checks have now been completed.

## Changes and validation

- Three platform tests use explicit in-memory fixtures instead of retired
  SQLite imports. Durable behavior has real PostgreSQL integration coverage.
- The settings mutation test patches functions in the owning settings module.
- Registry/dashboard tests cover the current eleven tools and retain disabled
  defaults, action, execution-count, and error assertions.
- The GitHub bridge test explicitly supplies its fake adapter; production still
  fails closed when its adapter is unavailable.
- The native runtime entry point composes production lazily and uses the
  process-owned PostgreSQL job store for `/events`.
- Event tails are workspace scoped; event reads and cold TTS provider lookup
  run outside the event loop. PostgreSQL event-store errors are handled.
- Market-data calls and Chat session create/delete handlers use FastAPI's
  thread pool. Gateway replicas share the existing GPU TTS service through an
  explicit HTTP facade rather than constructing a GPU model in each process.
- A native supervisor manages worker/API children. Nonblocking Windows pipe
  polling fixes the startup deadlock observed between stdin reading and NumPy
  DLL loading. Isolated cohort startup and clean shutdown passed.
- An additional PCM test's old codec/token expectations were updated to the
  existing contract. The reload test explicitly disables deployed replicas.

**153 focused tests passed** at the initial rollout checkpoint, including the four files
containing the nine reported failures. PostgreSQL tests used a disposable
database. Targeted Ruff checks and compilation with the deployed Python
**3.10.20** passed; pytest used Python **3.11.12**.

The routing follow-up passed **91 focused Python tests** (including the nine
original failure cases) and **20 frontend tests**, plus frontend build/typecheck,
targeted Ruff, deployed-Python compilation, and final diff checks. Regression
coverage uses actual Vite HTTP/SSE/WebSocket proxies and disposable PostgreSQL.

Exported OpenAPI remains unchanged, SHA256:

`61ee02289fb4a157f52c49ff9c39355c25081e1bc891cf3c9f03c43c9b690842`

The full repository suite and browser microphone/playback flows were not run.
An exploratory persistent live-call WebSocket test run stalled and was
interrupted; it is not counted among passing tests. Focused PCM/runtime/
capability tests and the real speech workload passed. Existing FastAPI and
`audioop` deprecation warnings remain.

## Real workloads

Successful qualification used production-composed gateways, actual Codex
authentication, GPU speech, and external market data. It first ran against
disposable PostgreSQL, then against the deployed application. An earlier
sandboxed attempt could not access Codex state or external sockets; it was
repeated with the required external access. No mocked model or market-data
provider was used for successful qualification.

| Workload | Deployed result |
| --- | --- |
| Three concurrent Codex Chat jobs, configured `gpt-5.6-luna` | Completed in 10.01–17.60 s; admission 275–440 ms |
| Duplicate submissions through another replica | Same job ID; one persisted assistant reply per turn |
| Codex SSE Chat | Eight events, persisted reply; first content 21.73 s |
| Qwen GPU synthesis | 3.7 s PCM audio; first audio 1.34 s |
| Nemotron + Parakeet EOU transcription | 0.32 s; validation sentence recovered exactly |
| Binance BTC/USDT | 30 daily bars and polled quote; 0.97 s |
| Yahoo AAPL | 30 daily bars and cached quote; 0.41 s |
| API health during concurrent work | 303 samples, zero errors; p50 2.12 ms, p95 3.44 ms, max 798.42 ms |

Raw evidence:

- [Single-gateway qualification](measurements/gateway-real-provider-qualified-2026-09-26.json)
- [Isolated cohort qualification](measurements/gateway-real-provider-cohort-2026-09-26.json)
- [Deployed workloads](measurements/gateway-real-provider-deployed-2026-09-26.json)
- [Deployment evidence](measurements/gateway-deployment-2026-09-26.json)

Reproduce the workload check:

```text
python scripts/validate_gateway_rollout.py --urls http://127.0.0.1:8000 http://127.0.0.1:8001 http://127.0.0.1:8002 --model gpt-5.6-luna --output resources/artifacts/gateway-provider-check.json
```

The harness creates named synthetic Chat sessions and deletes successful ones
after checking persistence. It submits no orders or trading-control writes.

## Backup, migrations, and deployment

The custom PostgreSQL backup is saved locally at:

`resources/artifacts/backups/omnix-framework-rollout-20260926.dump`

Size: **161,906,679 bytes**. SHA256:

`4c8f15bfe5909275b49126bf18d87866a261ac535c0e179a52d9be35c3788256`

The archive header was verified; a restore rehearsal was not performed. This
backup contains application data and remains in ignored local artifact storage.

The old gateway was stopped through the existing launcher. Forward migration
execution verified **0097_chat_session_coordination**, with no pending
migrations or checksum drift. That schema was already applied when cutover
began, so `applied_now` was empty.

| Process | Port | PID at rollout | Role |
| --- | --- | --- | --- |
| Gateway supervisor | — | 220536 | Child supervision |
| Primary gateway | 8000 | 221092 | worker |
| API replica | 8001 | 221628 | api |
| API replica | 8002 | 222576 | api |

All three `/ready` endpoints passed. PostgreSQL confirmed three live gateway
identities and **one** background-worker advisory-lock owner. Launcher, web,
TTS, STT, Hermes, and image service processes were preserved.

The local setting `resources/data/gateway-deployment.json` contains
`{"api_replicas": 2}` and is read on gateway startup. Existing launcher
start/stop/restart controls supervise the cohort. Manual launches can specify
`--api-replicas 2`; development reload requires `--api-replicas 0`.
`OMNIX_GATEWAY_API_REPLICAS` takes precedence over the local file.

## Frontend routing follow-up

The existing Vite server now selects a fixed proxy target for each request,
alternating between the two APIs for the qualified Chat session/message
contract, standalone speech streams, job/event reads, and market-data reads.
SSE stays incremental, downstream cancellation closes its upstream request,
and each WebSocket remains on one target until closed. Failed writes are not
replayed. Worker controls, live-call coordination, and unqualified feature
extensions use the worker. Same-origin live voice Chat supplies worker affinity;
the existing direct local live voice transport also stays on the worker.

The routing module reads the local replica setting at startup. Explicit
`VITE_GATEWAY_ORIGIN`/E2E overrides retain a single target unless
`OMNIX_GATEWAY_API_ORIGINS` supplies a comma-separated API origin list. An empty
origin list disables balancing. Restart the frontend after changing deployment
configuration. Both development and preview servers use this routing policy;
static assets alone do not implement backend routing.

Real routing qualification exposed two additional persistence issues:

- Session create/delete used a recent-workspace snapshot that could delete
  neighboring sessions or reject their concurrent transcript changes. PostgreSQL
  now inserts or soft-deletes only the requested session. Greeting insertion is
  atomic, and tests exceed the sidebar's 200-session page size.
- Runtime initialization could request the migration advisory lock after Chat
  domain locks, producing a deadlock. Inside a shared application transaction,
  migration calls verify compatibility without running migrations. Forward
  migration execution remains outside that transaction. Assistant-turn writes
  now use individual module records and remember persisted changes after commit.
  Existing legacy turn documents remain readable, while replicas preserve each
  other's independent turn records.

All three concurrent real Codex jobs then completed in **11.54–24.77 s**, with
**147–276 ms** admission. SSE Chat used **api-1** and persisted its reply; first
content took **27.71 s**. Qwen PCM WebSocket used **api-2**, delivered 32 frames,
and recovered the validation sentence through real STT. First audio was
**1.33 s**. Binance and Yahoo market reads passed. Both API routes served
**124 recorded workload responses**, and frontend health recorded **123 samples,
zero errors**, p50 **4.96 ms**, p95 **20.19 ms**, max **738.37 ms**.

Evidence:

- [Successful routed workloads](measurements/gateway-real-provider-routed-2026-09-26.json)
- [Current process, migration, and ownership verification](measurements/gateway-routed-deployment-2026-09-26.json)
- [Initial snapshot failure](measurements/gateway-real-provider-routed-initial-2026-09-26.json)
- [Migration/turn lock contention before the fix](measurements/gateway-real-provider-routed-lock-contention-2026-09-26.json)

Reproduce through the frontend:

```text
python scripts/validate_gateway_rollout.py --urls http://127.0.0.1:5173 --model gpt-5.6-luna --require-api-routes --output resources/artifacts/gateway-routed-check.json
```

The gateway was restarted through the launcher after checking for active Chat
jobs. STT, TTS, web, Hermes, and image service processes were preserved. Current
verification confirms three live gateway identities, exactly one background
worker lock owner, and no pending migrations or checksum drift. No additional
schema migration was required for the routing fixes.

## Operational limits

- Qualified frontend routes balance across 8001/8002. Stateful live voice and
  worker controls remain on 8000; additional feature routes require their own
  ownership review before entering the replica allowlist.
- This is one host sharing resources and external GPU services. These short
  checks do not establish multiple-host failover or sustained capacity.
- The existing TTS HTTP endpoint buffers a WAV before gateway PCM frames are
  delivered. First-audio measurements include that buffering; the facade does
  not add decoder continuation or a new GPU streaming endpoint.
- Provider/model/reasoning settings were preserved. Streaming Chat first-content
  latency remains material despite responsive API health checks.
- Trading qualification covers real market-data reads. Funded brokerage
  execution, microphone conversations, interruption during playback, and
  long-duration soak testing were not qualified.
- Worker ownership adds no trading or agent grants. APIs do not automatically
  promote themselves. A child-process failure stops the supervised cohort;
  restart through the existing launcher.
- Frontend build passes with existing warnings: Node 22.9 is below Vite's
  supported 22.12 baseline, and the trading bundle exceeds the chunk-size warning
  threshold. No dependency upgrade or bundle restructuring was included here.

The temporary candidate and supervised qualification children were stopped.
The disposable PostgreSQL validation container was removed after regression
checks. Production PostgreSQL and its persistent volume remain intact.
