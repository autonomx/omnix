# Framework implementation and baseline — 2026-09-26

## Implemented foundation

This is the first implementation package from the framework review. It establishes
production composition and repeatable measurements; the larger worker, router and
collection refactors remain listed below.

- `app.production` owns production assembly. PostgreSQL bootstrap and hardware
  policy installation precede gateway composition. `main:app`, `launch:app`,
  `app.gateway.main:app`, and the gateway launcher use the same lazy ASGI object.
  Reload initializes the serving child, rather than bootstrapping its parent.
  Imports and the provider-free `create_gateway_app` factory remain database-free.
- `GatewayRuntimeServices` holds process-owned jobs, assets, chat and residency
  services. The main gateway routes reuse these services; transactions remain
  request-scoped and PostgreSQL authority checks remain in place. Other feature
  modules still need migration to explicit service injection.
- Initialization errors fail the ASGI startup handshake. The production ASGI
  wrapper closes the default PostgreSQL pool on lifespan completion.
- `/health` and `/api/health` keep their existing liveness contract. `/ready`
  returns 503 before startup completes, on failed PostgreSQL connectivity,
  incompatible schema/checksums, unavailable authority, or unavailable explicitly
  required workers. Readiness does not apply migrations, initialize authority,
  or create the migration metadata table. Database exception details are redacted.
- `OMNIX_GATEWAY_REQUIRED_WORKERS=tts,stt` optionally gates readiness on those
  configured worker IDs. Missing, failed or mocked required workers fail readiness.
  Optional workers do not gate it. Worker health remains a health contract, not
  proof that a particular model or full generation pipeline is ready.
- Synchronous job mutation/read handlers, asset listing and worker diagnostics
  run through FastAPI's thread pool. Live SSE store polling and store construction
  during recovery run outside the event loop. Worker health probes share a bounded
  four-thread executor and preserve discovery order.
- New asset ingestion uses the existing atomic, checksummed streaming blob writer,
  preserving cleanup when metadata persistence fails.
- PostgreSQL CI no longer compiles the deleted `src/run_app.py`; it now runs the
  startup/readiness regressions. Docker points to the current download-script
  locations and gateway entrypoint, uses `/ready` on port 8000, and no longer
  suppresses dependency installation failures. Compose waits for PostgreSQL health
  and starts one foreground gateway process.

The package-level compatibility factory `app.create_app` remains a provider-free
factory for embedded callers and tests. Production callers should use
`app.production:app` or `create_production_app`.

## Measurements

Environment: Windows build 26200, Python 3.11.12, Docker PostgreSQL 17 Alpine.
Source revision: `d71b55a099a96cad4c4cf7032cccecd2d204cdcf` plus this working-tree
implementation. JSON captures preserve the measured values and benchmark modes.

| Measurement | Before | After |
| --- | ---: | ---: |
| Health p95 alongside a simulated 50 ms job read | 53.55 ms | 6.54 ms |
| Event-loop scheduling delay p95 during a simulated 50 ms SSE poll | 50.55 ms | 0.07 ms |
| PostgreSQL-backed asset listing p95 | 95.25 ms | 4.52 ms |
| Python allocation peak ingesting a 64 MiB file | 64.01 MiB | 2.02 MiB |

The synthetic benchmark runs 30 samples and calls the real gateway handlers using
an in-process ASGI transport. The PostgreSQL benchmark also uses that transport,
with a fresh disposable database named `omnix_refactor_baseline` on port 16432.
It omits background startup hooks to avoid starting trading monitors or external
providers. Asset-list measurements compare the initially repeated repository
construction with the final process-owned service. Both collections are empty;
these measurements do not establish performance for a large populated library.

Fresh PostgreSQL assembly including migrations measured 4.06 seconds. Subsequent
assembly against an already migrated database measured 2.76 seconds. These are
single observations with different schema/cache conditions, not evidence of a
startup speedup. Final job-list p95 was 4.67 ms and liveness p95 was 0.97 ms.

Synthetic health's maximum was 113.34 ms despite its lower p95. Cold thread setup
and host scheduling remain in the measurements; a deployment acceptance test must
also check tail latency. The scheduling-delay metric depends on Windows timer
resolution and should be compared within the same environment.

Blob peaks use `tracemalloc`: Python allocations only, excluding native allocations
and the OS file cache. Both writers produced equal byte sizes and SHA-256 hashes.

### Reproduce

```text
python scripts/benchmark_gateway_baseline.py --output <capture.json>
python scripts/benchmark_blob_memory.py --size-mib 64 --output <capture.json>
```

For PostgreSQL, supply `OMNIX_BENCHMARK_DATABASE_URL` pointing to the explicitly
named disposable `omnix_refactor_baseline` database and run:

```text
python scripts/benchmark_gateway_postgresql.py --output <capture.json>
```

The optional `--local-disposable` flag uses the test container's dedicated local
port and disposable credentials. This benchmark applies migrations to that
database. Do not point it at application data. The container used for this review
was removed after validation; no existing database or volume was modified.

Raw captures are in `docs/measurements`:

- `gateway-before-2026-09-26.json`
- `gateway-after-2026-09-26.json`
- `gateway-postgresql-fresh-2026-09-26.json`
- `gateway-postgresql-services-2026-09-26.json`
- `blob-memory-2026-09-26.json`

## Validation and limits

- 37 focused startup, foundation, retirement and migration tests passed, including
  four real PostgreSQL integration tests. Readiness succeeds when PostgreSQL
  sessions themselves enforce `transaction_read_only=on`.
- 20 asset, streaming-ingestion and blob tests passed.
- Changed/new Python modules passed Ruff and bytecode compilation.
- `docker compose config --quiet` passed.
- Generated OpenAPI was exported and compared: unchanged. `/ready` is an
  operational endpoint excluded from the browser contract.
- Two direct RPG route tests return 404 with both the previous gateway source
  and this implementation. The fresh-import hook test was updated to explicitly
  construct the gateway because production imports now defer assembly.
- The old gateway job suite cannot collect in this environment because its
  `asyncio` marker/plugin is absent. It also imports the retired `SQLiteJobStore`.
  New gateway responsiveness regressions use synchronous pytest entrypoints with
  `asyncio.run`, and PostgreSQL integration tests cover the current backend.
- The CUDA image was not built. Its broad inference dependencies, model downloads
  and repeated package reinstalls still need a separate deployment-image refactor.
  External model workers and populated-library throughput were not benchmarked.

## Next implementation packages

1. Durable execution ownership and lease-aware chat recovery. **Multiple gateway
   processes are still unsafe**: local chat ownership and trading monitors remain
   process-local. Do not raise worker/replica counts based on this package.
2. Move inline execution and unbounded submissions behind supervised, bounded,
   leased workers; provide shared ownership for trading monitors and GPU permits.
3. Replace constructor monkeypatching with explicit router/service registration,
   beginning with library features; expand process-owned service injection.
4. Filtered cursor pagination for assets and recovery scans, with populated-data
   measurements and query plans; preserve tenant scope and stable ordering.
5. Shared event distribution, browser lifecycle cleanup, generated browser
   contracts, and mixed chat/audio/job load tests with throughput and tail-latency
   acceptance gates.

The original framework review remains the detailed backlog and invariant guide.
