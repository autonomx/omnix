# Architecture release gates

`scripts/run_architecture_gates.py:GATES` is the executable manifest. `.github/workflows/architecture-runtime.yml` runs independent PR gates; integration jobs each get a disposable PostgreSQL 17 service. Tests that truncate data refuse arbitrary database names.

| Invariant | Named regression coverage |
| --- | --- |
| Immutable, validated topology | `app/test_runtime_config.py`, `test_production_assembly_bootstraps_before_gateway_composition` (same configuration instance) |
| API rejects singleton/GPU ownership | `test_api_capabilities_exclude_singleton_and_local_gpu_work`, `test_api_rejects_worker_only_feature_lifecycle`, `test_api_lifespan_never_runs_recovery_or_worker_hooks` |
| Every worker declares ownership | `test_gateway_rejects_undeclared_startup_hooks_before_api_can_run_them`, `test_api_audiobook_lifecycle_never_initializes_workers`, `test_audiobook_threads_inherit_ownership_and_stop_after_revocation` |
| Local TTS capability cannot be bypassed | `test_api_cannot_bypass_local_tts_capability_with_another_provider`, `test_api_replica_cannot_construct_local_qwen_tts` |
| One worker, two API replicas | `test_one_worker_two_api_replicas_remote_tts_and_graceful_handoff` |
| Ownership loss and handoff | `test_background_backend_loss_stops_workers_and_allows_successor`, `test_worker_process_crash_releases_singleton_authority`, `test_background_database_mutations_fail_closed_after_ownership_loss` |
| Actual PostgreSQL restart | `certify_postgresql_restart.py`: liveness during database loss, readiness drop, old authority latched, fresh worker/API readiness after restart |
| Stale attempt fencing | `test_expired_job_attempt_is_fenced_after_another_worker_claims`, `test_expiry_after_reply_write_rolls_back_transcript_and_completion` |
| Foreground and internal worker boundary | `persistence/test_internal_job_protocol_integration.py`: service credential, original worker lease, reserved browser admission, exact foreground claim scope, no lease bypass and no generic claim of audit records; `test_foreground_turn_transaction_integration.py`: rejected claims/leases roll back turns and mirrored execution replays once |
| Cancellation terminates after loss | `test_expired_cancel_requested_job_becomes_terminal_canceled`, chat ownership cancellation regression |
| Chat process crash and one recovery | `test_killed_chat_owner_recovers_once_without_duplicate_assistant_output`, `test_recovery_rechecks_liveness_and_emits_one_event_under_racing_gateways` |
| Atomic durable chat and memory | `persistence/test_chat_atomic_scaling_integration.py`, `persistence/test_memory_job_execution_integration.py` |
| PostgreSQL authority, explicit factories | `test_runtime_retirement_integration.py`, `test_active_feature_factories_integration.py` (including durable character memory management), `test_sqlite_runtime_retirement.py` |
| Import isolation | `unit/test_import_isolation.py`, `test_production_import_does_not_import_gateway_or_contact_database` |
| Startup/shutdown ordering | `test_feature_startup_shutdown_order_and_partial_failure`, `app/test_gateway_scaling_lifecycle.py` |
| Event-loop responsiveness | gateway baseline tests; `benchmark_gateway_baseline.py` |
| Shared routing, no replay | `app/test_gateway_route_policy.py`, web `src/test/gateway-routing.test.ts`, generated Nginx check |
| Safe diagnostics/logs | runtime architecture diagnostics and transition redaction tests |
| Compatibility growth | `test_compatibility_modules_are_allowlisted` requires a reviewed inventory entry |
| Web contracts/workspaces | Typecheck, reproducible OpenAPI generation, routing, Chatbot/Audiobook/Trading tests |

Run from repository root:

```text
python scripts/run_architecture_gates.py --group unit
python scripts/run_architecture_gates.py --group postgresql
python scripts/run_architecture_gates.py --group multiprocess
python scripts/run_architecture_gates.py --group persistence-all
npm --prefix src/apps/web run typecheck
npm --prefix src/apps/web run api:check
npm --prefix src/apps/web run test -- src/test/gateway-routing.test.ts src/features/chatbot src/features/audiobook/AudiobookWorkspace.test.tsx src/features/trading
```

Set `OMNIX_TEST_DATABASE_URL` to a disposable database named `omnix_test`; the gate also sets the production database URL within the test subprocess. `--local-disposable` selects only the documented local benchmark container at port 16432. Never point integration tests at an operator database. On Windows use `npm.cmd` if PowerShell blocks `npm.ps1`.

## No runtime patching policy

[ADR 0015](../architecture/ADR-0015-no-runtime-patching.md) requires explicit
extension points and changes in the owning module. Run
`python scripts/architecture_lint.py --check` from the repository root. The gate
checks tracked production Python, including lazy imports, and migration history;
it imports no application code and executes no provider or database work.
Browser patch enforcement belongs to the ESLint gate.

`resources/architecture/lint-baseline.json` records existing violations by rule,
path and fingerprint, with occurrence counts. A new violation fails; a fixed or
reduced violation also fails until the baseline is shrunk with
`python scripts/architecture_lint.py --update-baseline`. That command refuses
increases or changed policy. Adding blank lines cannot alter an exception.
Migration violations cannot be baseline exceptions. Historical checksums come
from the base branch and `resources/architecture/migration-checksums.json` when
the ref is unavailable. CI explicitly supplies the PR base or previous push
commit, so a push cannot use its own new migrations as its comparison base.

The baseline is transitional evidence of remaining work, not permission to add
patches or widen runtime authority. Its initial local measurement and CI wiring
remain subject to the roadmap's canonical environment verification.

For the local disposable profile, create a retained container (restart certification rejects `--rm`):

```text
docker run --detach --name omnix-architecture-test --publish 127.0.0.1:16432:5432 --env POSTGRES_DB=omnix_refactor_baseline --env POSTGRES_USER=omnix_baseline --env POSTGRES_PASSWORD=baseline_disposable postgres:17-alpine
```

Remove that exact disposable container after testing with `docker rm --force omnix-architecture-test`. Never use the operator PostgreSQL container for failure certification.

Reproducible measurements:

```text
python scripts/benchmark_gateway_baseline.py --samples 30 --output artifacts/gateway-baseline.json
python scripts/check_architecture_benchmark.py --baseline resources/benchmarks/gateway/refactor-baseline.json --measured artifacts/gateway-baseline.json
python scripts/benchmark_gateway_postgresql.py --samples 20 --output artifacts/gateway-postgresql.json
python scripts/benchmark_chat_recovery.py --samples 10 --output artifacts/chat-recovery.json
python scripts/benchmark_gateway_scaling.py --workers 3 --submissions 30 --output artifacts/gateway-scaling.json
python scripts/measure_gateway_soak.py --mock-compute --duration-seconds 600 --output artifacts/gateway-soak.json
python scripts/certify_postgresql_restart.py --container omnix-architecture-test --local-disposable --output artifacts/gateway-postgresql-restart.json
```

The PostgreSQL benchmarks also accept `--local-disposable`. The original provider-free baseline records the actual checkout revision/platform and excludes lifespan, database and GPU execution. Its p99 equals max for 30 samples; uninstrumented occupancy and inapplicable recovery are `null`. Subsequent `hardening-*.json` artifacts are separate measurements, not rewritten pre-change results.

The CPU soak starts real production-composed worker + two API processes and a deterministic remote compute fixture. It mixes durable chat writes/reads/idempotent duplicate admission, SSE/job events and binary WebSocket TTS, restarts an API replica, and measures Python heap, threads, asyncio tasks and PostgreSQL pool state. It fails on errors, duplicate outputs, expired leases, pending dispatches/requests, or growth above 64 MiB / 32 threads / 32 tasks after warmup. These generous bounds detect leaks without treating tiny timing changes as failures. Latency comparison permits 5× baseline with a 40 ms absolute floor. GPU throughput and live provider/market behavior require the separate live `measure_gateway_soak.py --model <id>` profile.

Repository administrators should require `architecture-unit`, `architecture-durable (postgresql)`, `architecture-durable (multiprocess)` and `architecture-web` on `main`. The workflow supplies checks; branch protection must be enabled in repository settings. Scheduled/manual soak reports are retained as CI artifacts.
