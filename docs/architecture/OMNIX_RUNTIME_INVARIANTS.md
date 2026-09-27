# Omnix runtime invariants

These are implementation contracts, checked by the [architecture gates](../testing/ARCHITECTURE_GATES.md). Runtime authority and issued agent capabilities remain authoritative; process capabilities never grant agent or trading authority.

The [no runtime patching policy](ADR-0015-no-runtime-patching.md) is enforced by
`python scripts/architecture_lint.py --check`, using a shrinking inventory of
existing violations. The lint never grants execution authority or replaces the
durable runtime checks below.

| Boundary | Required behavior |
| --- | --- |
| Structured authority | PostgreSQL is the only production authority. Database failure never selects a file, SQLite, or memory fallback. Legacy test/import persistence requires explicit opt-in. SQLite extraction runs only through `persistence/legacy_export.py`. |
| Configuration | Production binds one frozen `RuntimeConfig` before feature imports. Changing environment variables after composition cannot change role, service topology, required workers, or replica origins. Invalid URLs and contradictory ownership fail startup without echoing credentials. |
| Background ownership | At most one worker/control process per workspace holds the PostgreSQL advisory lock. API processes never acquire it. Connection loss permanently revokes that process's ownership and stops its workers. Restart with a fresh process to recover. |
| Capabilities | `RuntimeCapabilities` derives its small process capability set from configuration. Background workers declare ownership at registration. Scheduler/recovery/local TTS capabilities are absent on API replicas. Request chat dispatch is allowed on APIs under durable execution ownership. |
| GPU compute | API processes cannot construct a local CUDA/Qwen provider. With a configured endpoint they use remote TTS; otherwise speech stays worker-routed. The worker can use local TTS or an explicitly selected remote service. |
| Job execution | Claims carry worker identity, attempt and lease tokens. Completion, failure, renewal and cancellation validate ownership. Expired attempt A cannot finalize after B claims. Cancellation followed by worker loss and expiry ends in `canceled`, not an indefinite retry. |
| Chat execution | Submission/idempotency and owner identity are durable. Live owners are preserved across gateways; expired process identities cannot be revived. Recovery finalizes an abandoned generation once without committing a duplicate assistant message. Chat transcript and completion share one transaction. |
| Foreground job finalization | Unleased transitions require either an inline `chat.generate` job with its matching live gateway identity, or an `rpg.turn.foreground_record` linked to the exact started submission and its original claim token. All worker lease columns must be absent. Compatibility flags alone never authorize completion or failure; browser job admission cannot select foreground execution authority. RPG turn persistence uses the caller's original claim and worker credentials, never credentials borrowed from a row. |
| Transactions | Request transactions remain scoped to the existing unit of work. Sharing rejects different databases, tenants and threads. Production service factories own repositories, never an open request transaction. |
| Event loop | Blocking PostgreSQL/provider reads execute through sync routes or bounded thread offload. Slow job/SSE polling must not stall liveness. |
| Lifecycle | Feature startup follows descriptor order; shutdown reverses it, including partially started features. Singleton background callbacks run only with live authority. Shutdown releases execution identities and advisory ownership. |
| Health | `/health` is liveness; `/ready` requires completed startup, PostgreSQL authority/schema, execution identity and role-specific ownership. Required external workers must be healthy and real; optional GPU services do not block readiness. |
| Routing | [Shared route policy](../../deploy/gateway-route-policy.json) owns the allowlist. Unclassified writes/control stay on the worker. Streaming connections remain on one selected upstream. Failed writes are never automatically replayed. |
| Diagnostics | The `runtime` object returned by `/api/diagnostics` reports local identity, ownership, queues, leases, recovery and providers. Durable counts are workspace-scoped. Unknown remote readiness is `null`; raw exceptions, credentials and credential-bearing URLs are not exposed. |

Register new background services with `BackgroundWorker` and `register_background_worker`; use `FeatureLifecycle` for process-local services. Production feature composition rejects new undeclared FastAPI startup/shutdown hooks before they can execute. Obtain production persistence through explicit constructor injection or `runtime_composition` defaults. Do not replace imported feature classes/functions or mutate standard-library persistence functions.
