# Omnix enterprise architecture review

Date: 2026-09-27
Source revision inspected: `7bd17af08` (branch `main`, clean tree)
Scope: whole repository, assessed as an enterprise application. The review asks three questions:
- Can new features be added as modules without disturbing existing ones?
- How does it perform?
- Can it scale out?

Security, data architecture, operations and delivery are included because they decide whether an application can be deployed in an enterprise at all.

Companion document: [ENTERPRISE_ARCHITECTURE_ROADMAP_2026-09-27.md](ENTERPRISE_ARCHITECTURE_ROADMAP_2026-09-27.md). It is the implementation plan to bring every area to 9/10.

Earlier reviews: [FRAMEWORK_REVIEW_2026-09-26.md](FRAMEWORK_REVIEW_2026-09-26.md) and its follow-up implementation reports. Section 12 gives the status of its findings R1–R15.

---

## 1. Executive summary

### Rating

| Lens | Rating |
|---|---|
| As an enterprise application (multi-user, horizontally scalable, secure, operable) | **4 / 10** |
| As what it was designed to be (single trusted user, local-first workstation) | **6 / 10** |

**The documented architecture is sound.** [SPEC.md](../SPEC.md), [ARCHITECTURE.md](ARCHITECTURE.md) and ADR-0010 to ADR-0014 describe:
- a modular monolith with PostgreSQL as the only authority;
- shared job, asset and event systems;
- typed contracts between browser and backend;
- governed agent capabilities.

**Several platform primitives are better than typical enterprise code:**
- lease and fencing tokens on job execution;
- `FOR UPDATE SKIP LOCKED` job claims;
- chat recovery that checks whether the owning process is still alive;
- atomic chat completion;
- a PostgreSQL advisory lock that gives background work a single owner;
- immutable runtime configuration;
- checksummed migrations;
- atomic SHA-256-verified blob writes;
- executable architecture gates backed by benchmarks.

**The implemented architecture differs from the documented one in two ways, and they cause most other problems.**

1. **Features are extended by patching other code at runtime.** Across backend and frontend, new behaviour is usually added by replacing someone else's functions, methods, globals or `window.fetch` while the app runs, rather than by changing the code that owns the behaviour. The inventory:

   | Location | Count |
   |---|---|
   | `install_*hook`-style installers in the backend | 87 |
   | Installers run each time the gateway app is built (`create_gateway_app`) | ~23 |
   | Import-time patches in trading | 99 (applied by 19 installers) |
   | Silent best-effort RPG session hooks | 19 |
   | RPG runtime parts merged through shared globals | 40 |
   | `sitecustomize.py` | patches every Python process at startup |
   | Frontend files that replace `window.fetch` | 17 |

   One safety control, the automatic paper-trading authorization gate, exists **only** as one of these patches.

2. **The shared kernels depend on the features built on top of them.**
   - About 75% of the shared `jobs` package is feature executors, and `jobs` imports 16 other packages, including `gateway`.
   - `persistence` imports RPG, chat, characters and gateway code. Its unit of work builds 33 repositories per transaction, 14 of them for RPG.
   - `platform/__init__.py` replaces an RPG function when it is imported.
   - There are 17 package-level import cycles.
   - Every `trading` monitor imports the web gateway so it can register itself.

**What follows from these two properties:**
- Behaviour depends on import order and cannot be read from the owning source file.
- Features cannot be disabled, extracted or tested in isolation.
- Safety controls can disappear through a refactor or a different import path.
- Each new feature adds risk that does not stay inside that feature.

**Most performance and scalability limits come from the same accretion:**
- `async` handlers doing synchronous I/O on the event loop;
- migrations and tenant bootstrap running on request paths;
- whole JSON documents rewritten on every change;
- state kept in process memory;
- a single-slot provider cache;
- storage on the local filesystem.

**Security is a hard gate for enterprise use.**
- 767 route handlers have zero authentication or authorization guards.
- Tool and agent approvals are asserted by the client.
- The default launcher exposes the gateway to the LAN through the Vite dev proxy on `0.0.0.0`.
- A value with the format of a real API key is committed to git.

### The ten most important issues

| # | Issue | Area | Finding |
|---|---|---|---|
| 1 | No authentication or authorization on any route; the tenant is one process-wide "local owner" | Security | SEC1 |
| 2 | Approvals asserted by the client (`approved`, `approval_policy` in request bodies); agents run without a sandbox by default | Security | SEC2, AR2 |
| 3 | Committed API-key-format secret; LAN exposure; no CSRF, Origin or Host protection | Security | SEC3, SEC4 |
| 4 | Runtime patching is the main way features are extended, including the trade authorization gate | Modularity | X1, TR1 |
| 5 | Kernel → feature dependencies and 17 package cycles | Modularity | X2 |
| 6 | Migrations and tenant bootstrap on request paths (132 call sites); rolling upgrades impossible | Performance, scalability | PERF2, SCALE4 |
| 7 | 229 `async` handlers that never await, most doing blocking I/O; the RPG turn runs LLM generation on the event loop | Performance | PERF1 |
| 8 | Whole-document persistence (RPG state, settings, whole-workspace chat save with a data-loss race) | Data, performance | DATA3, CM1 |
| 9 | Single worker process owns almost all background work; GPU capacity not coordinated; local-disk blobs | Scalability | SCALE1–SCALE5 |
| 10 | CI never runs the full suite (~10% failing); no type checker; no lockfiles; builds tied to one developer's machine | Delivery | DEL1–DEL3 |

### Immediate actions, independent of the roadmap
1. Rotate the Cerebras credential whose format-matching value is committed in [src/app/data/settings.json](../src/app/data/settings.json) (`cerebras.api_key`, 52 characters, prefix `csk-`). Then remove the file, purge it from history, and add secret scanning.
2. Bind the Vite dev server, STT service, `openai_api.py` and spawned `llama-server` to loopback by default.
3. Stop accepting `approved` and `approval_policy` from request bodies.

---

## 2. Scorecard

### By area

| Area | Score | Target | Main gaps |
|---|---:|---:|---|
| Platform primitives (durability, fencing, configuration) | 7 | 9 | The compat job adapter's fence always passes; no retention; outbox never consumed; event cursor can skip events |
| Modularity and extensibility | 3 | 9 | Patch-based extension; no plugin contracts; static feature list; adding a strategy, provider or capability touches 6–8+ files |
| Dependency direction and composition | 3 | 9 | 17 cycles; kernels import features; ~23 hooks per app build; `shared.py` acts as a global service locator |
| Performance | 4 | 9 | Event-loop blocking; migrations on request paths; whole-document writes; no pooled HTTP |
| Horizontal scalability | 3 | 9 | One worker process; state held in process memory; GPU capacity not coordinated; local blob storage; no rolling upgrades |
| Data architecture | 4 | 9 | 77% of tables use JSONB; no retention; outbox never consumed; migration ordering hazards |
| Security (multi-user) | 2 | 9 | No principal model, authorization, CSRF, Origin or Host checks; client-asserted approvals; committed secret |
| Observability and operations | 3 | 9 | No request IDs, metrics or tracing; 198 `print()` calls; 290 environment variables, ~19 validated |
| Delivery (CI, tests, builds, deployment) | 4 | 9 | Full suite never run in CI; no type checker; no lockfiles; machine-specific scripts; Docker image runs as root on a CUDA devel base |
| Frontend architecture | 4 | 9 | Global patching; no disposal; mostly handwritten API types; override-driven CSS; no error boundaries |

### By subsystem

| Subsystem | Score | One-line assessment |
|---|---:|---|
| Persistence, jobs, events, assets | 4 | Strong building blocks; runtime wiring breaks them (bootstrap on request paths, no retention, the compat fence always passes) |
| Agent runtime and tools | 4 | Excellent authority design; unauthenticated control plane, no default sandbox, god service stitched together with global patch seams |
| Trading | 4 | Paper-only idempotent ledger and fail-closed eligibility; 99 import-time patches, no strategy contract, file-based decision state |
| RPG | 3 | Atomic turn commit and bounded state; built by runtime mutation, determinism claim false, 29% of code unreachable |
| Providers, realtime voice, model services | 4 | Structured outputs and fenced chat jobs; process-local live voice built from patches, unauthenticated model services, single-slot provider cache |
| Web frontend | 4 | Good module catalog, lazy routes and API firewall; global patching runtime, handwritten contracts, CSS built on overrides |

---

## 3. Baseline metrics

These are the numbers the roadmap's ratchet tracks. Most come from static AST and regex scans over git-tracked files at `7bd17af08`; the source column names the exceptions.

| Metric | Value | Source |
|---|---:|---|
| Python under `src/app` (including embedded tests and vendor) | ≈690K lines | line count |
| RPG share of backend (non-test) | ≈376K lines, ~55–60% | line count |
| Python tests | 2,606 files, ≈470K lines, 15,185 test functions | AST |
| Web production TS/TSX | 588 files, ≈112K lines (plus a 25K-line generated file) | line count |
| Web CSS | 163 files, 33.7K lines | line count |
| Git history | 10,934 commits since 2026-02-20; peak 3,237 commits in August 2026 | `git log` |
| Deleted/added line ratio per domain | trading 0.07, persistence 0.05, gateway 0.12, RPG 0.18, agent runtime 0.19 | `git log --numstat`, renames excluded |
| Decorated route handlers | 767 (763 HTTP, 4 WebSocket) | AST |
| `async def` HTTP handlers with no `await` | 229 | AST |
| Handlers with `include_in_schema=False` | 274 decorated (292 occurrences in total) | AST, grep |
| Routes with an auth dependency | 0 | AST |
| `install_*hook/patch` function definitions | 87 | AST |
| Files that assign `FastAPI.__init__` | 48 | grep |
| Trading import-time installers / patches | 20 / 99 | trading audit |
| Package-level import cycles (module-level imports) | 17 | AST import graph |
| `bootstrap_local_tenant(` non-test call sites | 132 (111 in RPG) | grep |
| Environment variable names read / read sites | 290 / 388; ~19 centrally validated | AST |
| `print()` in `src/app` | 198 | AST |
| Silent `except Exception: pass/continue` | 183 | AST |
| `threading.Thread(` constructions / `daemon=True` | 51 / 52 | AST |
| Pooled HTTP clients (`requests.Session`, `httpx.Client`) | 0 | grep |
| Migrations / tables / indexes | 118 / 222 / 201 | SQL scan |
| Tables with JSONB / JSONB columns | 170 (77%) / 525 | SQL scan |
| RLS policies / partitioned tables / `LISTEN`/`NOTIFY` uses / outbox consumers | 0 / 0 / 0 / 0 | SQL and code scan |
| Duplicate migration numeric prefixes | 16 (plus `0008z`) | file names |
| Last full Python suite (from docs) | 13,111 passed, 1,278 failed, 442 skipped, 358 errors | [FRAMEWORK_HARDENING_2026-09-26.md](FRAMEWORK_HARDENING_2026-09-26.md) |
| Test files covered by `pytest.ini` `testpaths` | ≈17% | config |
| CI workflows / running full Python suite / running a type checker | 28 / 0 / 0 | `.github/workflows` |
| Web `!important` | 1,671 | regex |
| Web handwritten API payload types | 272 | AST |
| UI-called `/api` paths present in OpenAPI | 108 of 297 (36%) | path match |
| Web raw `fetch(` outside `src/api` | 76 | regex |
| Web error boundaries | 0 | grep |
| Web modules unreachable from `main.tsx` | 92 (5,575 lines) | import reachability |
| RPG modules unreachable from the gateway | 526 modules, ≈108K lines (29%) | import reachability |
| Largest backend class | `AgentRunService`, 4,556 lines, 73 methods | AST |
| Largest web function | `ChatbotWorkspace`, 2,039 lines | AST |

---

## 4. Strengths to preserve

Each of these is a real asset. The roadmap builds on them and must not regress them.

- **PostgreSQL authority, fail-closed.**
  - Typed SQLSTATE error mapping: [persistence/database.py](../src/app/persistence/database.py).
  - Authority gate: [persistence/authority.py](../src/app/persistence/authority.py).
  - `/ready` never migrates and redacts errors: [production.py:26-54](../src/app/production.py#L26-L54), [gateway/main.py:260-275](../src/app/gateway/main.py#L260-L275).
- **Job execution fencing in the repository layer.**
  - `SKIP LOCKED` claim: [job_repository.py:249-271](../src/app/persistence/job_repository.py#L249-L271).
  - Token-checked transitions, attempts, dead letters and job events written in one transaction: [execution_repositories.py](../src/app/persistence/execution_repositories.py).
  - The durable worker renews leases and fences failures by the original lease: [durable_feature_worker.py](../src/app/jobs/durable_feature_worker.py).
- **Chat execution.**
  - Admission locks the session row.
  - Duplicate submissions across processes are idempotent.
  - Recovery checks whether the owning process is alive, and processes rows in creation order.
  - Reply, job status and terminal event commit atomically.
  - See [chat_execution.py](../src/app/persistence/chat_execution.py), [generation_jobs.py](../src/app/chat/generation_jobs.py) and migrations 0096 and 0097.
- **Worker and API roles.**
  - One background owner per workspace via `pg_try_advisory_lock`, with supervision of the lock connection.
  - API processes cannot start singleton work.
  - See [background_runtime.py](../src/app/gateway/background_runtime.py) and [runtime_capabilities.py](../src/app/runtime_capabilities.py).
- **Immutable runtime configuration.**
  - [runtime_config.py](../src/app/runtime_config.py) is frozen and bound once per process.
  - It validates URLs and never echoes credentials.
- **Agent authority model.**
  - Profile ceilings: [profiles.py](../src/app/agent_runtime/profiles.py).
  - Child-run narrowing: [subagents.py](../src/app/agent_runtime/subagents.py).
  - Broker checks RunSpec membership first and binds approvals to the exact input: [broker_api.py](../src/app/agent_runtime/broker_api.py).
  - Durable budgets that lock rows and fail closed: [budget.py](../src/app/agent_runtime/budget.py).
  - Safe, verified, idempotent workspace promotion: [workspace_promotion.py](../src/app/agent_runtime/workspace_promotion.py).
  - Subprocess calls all have timeouts, allow-listed environments, and no `shell=True` in the agent runtime.
- **Trading safety invariants.**
  - Idempotent paper ledger with row locks: [paper_repository.py](../src/app/trading/paper_repository.py).
  - IBKR rejected as an execution binding: [binding_authority.py](../src/app/trading/binding_authority.py).
  - Fail-closed eligibility: [execution.py](../src/app/trading/execution.py).
  - No broker `placeOrder` call exists.
  - Provider HTTP runtime with semaphore, backoff, circuit breaker and request coalescing: [providers/http_runtime.py](../src/app/trading/providers/http_runtime.py).
- **Structured LLM outputs.** Versioned contracts with semantic validation, retry budget and size limits: [providers/structured](../src/app/providers/structured).
- **Outbox and inbox schema.** Ordered claims, per-consumer dedup and dead letters (migration 0011). The design is good; it is simply not used yet.
- **Atomic blob store.** Temp file, fsync, atomic replace, path-traversal guard and streaming put: [blob_store.py](../src/app/persistence/blob_store.py).
- **Audiobook as the reference feature.**
  - Explicit registrar, sync handlers, a `BackgroundWorker`, lease-fenced render workers per resource class, a content-addressed cache, and a standalone worker entrypoint.
  - See [audiobook/routes.py](../src/app/audiobook/routes.py) and [audiobook/worker.py](../src/app/audiobook/worker.py).
- **Frontend shell.**
  - Typed module catalog and lazy workspaces: [modules.ts](../src/apps/web/src/app/modules.ts), [ModuleWorkspace.tsx](../src/apps/web/src/features/ModuleWorkspace.tsx).
  - Per-module API firewall: [viewApiScope.ts](../src/apps/web/src/app/viewApiScope.ts).
  - SSE client with backoff, jitter and replay: [events/eventClient.ts](../src/apps/web/src/events/eventClient.ts).
  - Strict TypeScript, and `api:check` runs on PRs.
- **Engineering discipline.** ADRs, [OMNIX_RUNTIME_INVARIANTS.md](architecture/OMNIX_RUNTIME_INVARIANTS.md), [architecture gates](testing/ARCHITECTURE_GATES.md), reproducible benchmark harnesses, and measurement artifacts under [docs/measurements](measurements).

---

## 5. Cross-cutting findings

### X1 — Runtime patching is the main way features are extended (Critical)

**What.** New behaviour is added by replacing other modules' functions, class methods, globals, or browser globals at import time or app-build time. The owning code is not changed.

**Evidence** (✔ = checked directly by the reviewer):

| Location | Mechanism | Evidence |
|---|---|---|
| Gateway | `create_gateway_app` → `_install_required_rpg_turn_hooks` → `initialize_gateway_runtime_hooks()` installs ~20 live-chat hooks, then 5 RPG turn hooks | [gateway/\_\_init\_\_.py:8-14](../src/app/gateway/__init__.py#L8-L14), [runtime_hooks.py:83-150](../src/app/gateway/runtime_hooks.py#L83-L150) ✔ |
| Gateway → persistence | Replaces `PostgresChatSessionStore.get_session`, `begin_user_message` and `complete_streamed_reply` on the class | [live_chat_postgres_fast_path.py:535-586](../src/app/gateway/live_chat_postgres_fast_path.py#L535-L586) ✔ |
| Gateway → chat | `PromptChatSessionStore.stream_provider_reply_chunks` is wrapped 5 times; `LMStudioProvider.chat_completion` twice; Starlette `StreamingResponse.__init__` globally | providers audit (`live_chat_low_latency_stream.py`, `live_chat_live_voice_profile.py`, `live_chat_provider_metrics.py`, `live_chat_provider_routing.py`, `live_chat_stream_retry.py`, `live_sse_transport.py:374`) |
| Platform kernel | Replaces `app.rpg.session.new_game.create_new_game_session` as an import side effect | [platform/\_\_init\_\_.py:1-11](../src/app/platform/__init__.py#L1-L11) ✔ |
| Jobs kernel | Installs 7 execution patches on `InMemoryJobStore` at import time | [jobs/\_\_init\_\_.py:48-55](../src/app/jobs/__init__.py#L48-L55) ✔ |
| Composition root | `install_rpg_turn_job_guard(PostgresJobStoreAdapter)`, `install_rpg_debug_job_hook(...)`, `install_live_agent_store_hooks(...)` decorate adapter classes | [runtime_composition.py:6-30](../src/app/runtime_composition.py#L6-L30) ✔ |
| Trading | 19 installers run on any `app.trading` import (99 patches across 84 targets); comments say correctness depends on the order; `TradingStrategyMonitor._evaluate_candidates` is wrapped 5 times | [trading/\_\_init\_\_.py:51-75](../src/app/trading/__init__.py#L51-L75) ✔ |
| Trading safety | The AUTO_PAPER authorization gate (kill switch, entry window, qualification, profile match) exists only as a replacement of `_run_config` | [trading_data_hardening.py:596-614](../src/app/trading/trading_data_hardening.py#L596-L614) ✔ |
| RPG | 40 numbered runtime parts; globals merged and copied back into every part | [rpg/session/runtime.py](../src/app/rpg/session/runtime.py) |
| RPG | 19 best-effort hooks that swallow every exception (`except Exception: return`) | [rpg/session/\_\_init\_\_.py:67-105](../src/app/rpg/session/__init__.py#L67-L105) ✔ |
| RPG | 246 star imports; 4 `sys.meta_path` import hooks; `apply_turn` rebound by 9 modules | RPG audit |
| Every Python process | `sitecustomize.py` sets `builtins.opening_bonus` to hide a `NameError` and adds methods to `LMStudioProvider` | [src/sitecustomize.py](../src/sitecustomize.py) ✔ |
| Agent runtime | `AgentRunService.__getattribute__` rewrites `service_core` module globals on every attribute access; `review_orchestration` swaps globals inside try/finally, which is not thread-safe | [service.py:548-574](../src/app/agent_runtime/service.py#L548-L574), [review_orchestration.py:213-221](../src/app/agent_runtime/review_orchestration.py#L213-L221) |
| Legacy | 48 files still carry `FastAPI.__init__` patchers (most are no longer called); 87 `install_*hook/patch` functions exist | AST scan ✔ |
| Frontend | 17 files replace `window.fetch`; `voiceJobListGuard` replaces `omnixApiClient.listJobs` for the whole app and turns errors into `{jobs: []}`; 55 `window.__omnix*` flags act as a registry; `viewRuntime` drops every cleanup function | [voiceJobListGuard.ts:15-29](../src/apps/web/src/features/voice/voiceJobListGuard.ts#L15-L29) ✔, [viewRuntime.ts:11-48](../src/apps/web/src/app/viewRuntime.ts#L11-L48) ✔ |

**Why it matters.**
- *Correctness and audit.* What runs cannot be determined from the source of the function being called.
- *Safety.* Controls can be bypassed by a different import order or a direct import.
- *Silent degradation.* Best-effort installers fail without reporting it.
- *Testing.* Tests exercise a different composition than production, and `sitecustomize.py` changes the code under test.
- *Extensibility.* Every new feature must understand the existing wrapper chains.
- *Contradiction.* [OMNIX_RUNTIME_INVARIANTS.md](architecture/OMNIX_RUNTIME_INVARIANTS.md) says "Do not replace imported feature classes/functions". The architecture gates do not detect any of these patterns.

**Recommendation.**
- Adopt a written **no-runtime-patching policy** and enforce it with a ratcheting AST lint.
- Fold each wrapper chain into its owning code, in the original composition order.
- Before each fold, write characterization tests that capture current behaviour.
- Where plug-in behaviour is genuinely needed, use explicit extension points: registries, ordered pipeline stages, middleware, dependency injection.

### X2 — Kernel packages depend on feature packages (Critical)

**Evidence.**

1. **`jobs` is a feature dumping ground.**
   - It imports 16 packages, including rpg, research, chat, characters, image, providers, platform and gateway.
   - About 75% of its 5,615 lines are feature executors: `image_inline.py`, `voice_inline.py`, `research_inline.py`, `inline_feature_jobs.py` (story, podcast and RPG narration), `rpg_last10_report.py`, `rpg_debug_job_hook.py`.
   - `jobs/models.py:146-152` imports platform defaults.
   - `durable_feature_worker.py:15` imports the gateway.
   - Job dispatch is a hard-coded if/else ([durable_feature_worker.py:336-360](../src/app/jobs/durable_feature_worker.py#L336-L360)) ✔.
2. **`persistence` imports domain and transport code.**
   - It imports rpg (16 imports), chat, characters, assistant_memory, assistant_tools and gateway.
   - A persistence class subclasses a gateway store (`document_feature_compat.py:8,14`).
   - It builds gateway turn records (`rpg_turn_service.py:41`).
   - Its unit of work builds 33 repositories per transaction, 14 of them RPG (`unit_of_work.py:45-60,148-184`), so every unit-of-work user imports RPG code.
3. **`platform` imports RPG at module level.** It hosts six `rpg_*_compat.py` modules and patches RPG on import ✔.
4. **Trading imports the gateway.** All 22 module-level `app.gateway` imports are `BackgroundWorker`/`register_background_worker`, used only by `register_*(gateway: FastAPI)` functions. 39 trading modules import FastAPI.
5. **17 package-level cycles among module-level imports:**
   - agent_runtime↔assistant_tools
   - assist_core↔assistant_tools
   - assistant_context↔research
   - assistant_memory↔chat
   - assistant_memory↔characters
   - characters↔chat
   - chat↔testing
   - gateway↔jobs
   - gateway↔platform
   - gateway↔persistence
   - jobs↔testing
   - jobs↔persistence
   - jobs↔rpg
   - jobs↔research
   - persistence↔rpg (16 imports one way, 113 the other)
   - persistence↔research
   - persistence↔providers
6. **Cycles within RPG.** Including lazy imports, the largest cycle inside RPG spans 448 modules and 129K lines.

**Why it matters.**
- No feature can be disabled, extracted, versioned or tested without the kernel.
- Import cost and blast radius grow with every feature: importing anything in trading loads about 426 modules.
- The gateway boot eagerly imports about 242K lines of RPG.

**Recommendation.**
- Enforce a layered architecture: kernel ← features ← composition root.
- Features register job handlers, repositories, routers, workers and outbox consumers through a `FeatureModule` contract.
- Move feature code out of `jobs`, `persistence` and `platform`.
- Move `BackgroundWorker` into a neutral runtime package.
- Break cycles with contract packages, e.g. `app.conversation.contracts` for chat, memory and characters.
- Enforce all of this with a boundary lint whose baseline may only shrink.

### X3 — The gateway is a dumping ground, and the feature registry is not a module boundary (High)

**Evidence.**
- The gateway has 107 files and 233 route handlers.
- 48 of its files (15.3K of 26.4K lines, 58%) are live-voice and TTS domain logic.
- It holds 24 RPG route modules.
- [feature_registry.py](../src/app/gateway/feature_registry.py) is a hard-coded tuple of 45 `(module, registrar)` strings.
  - Each registrar receives the whole FastAPI app and can add middleware or rewrite routes, as `blocking_route_offload`, `rpg_turn_job_mirror._install_middleware` and `live_sse_transport` do.
  - Features cannot be enabled or disabled by configuration, and there is no per-feature router prefix or dependency set.
- [gateway/main.py](../src/app/gateway/main.py) re-exports about 160 symbols from `core_services.py` and still defines about 40 inline routes. Those include 21 RPG compatibility routes that take `dict[str, Any]` bodies and use `POST` for reads.
- It still has to delete routes that hooks installed and re-register them (`_remove_hook_installed_assistant_context_routes`).

**Recommendation.**
- The gateway becomes a composition root plus transport concerns only.
- Domain logic moves into feature packages; live voice gets an `app/live_voice` package.
- Features contribute `APIRouter`s that the composition root mounts with a prefix and security dependencies.
- The enabled-feature list comes from configuration.

### X4 — `shared.py` is a legacy global service locator with file fallbacks (High)

**Evidence.** [src/app/shared.py](../src/app/shared.py) (847 lines) is imported by 20 packages. It holds:
- resource paths;
- constants;
- default settings;
- settings, sessions and secrets I/O;
- process-global provider singletons (`get_provider`, `get_tts_provider`, `get_stt_provider`);
- text utilities.

Three concrete problems:
1. **Silent file fallback.** When the PostgreSQL callbacks have not been installed first, `load_settings`/`save_settings`/`load_secrets`/`save_secrets` read and write `resources/data/settings.json`, `sessions.json` and **`secrets.json`** ✔ ([shared.py:244-412](../src/app/shared.py#L244-L412)). Fail-closed behaviour therefore depends on bootstrap order, which contradicts ADR-0010 for any process that imports `shared` without bootstrapping.
2. **Whole-document settings.** `save_settings` calls `load_settings()` twice and rewrites the entire document.
3. **Single-slot provider cache.** `get_provider` has one unlocked slot. It re-reads settings and secrets on every call, and **closes the evicted instance even while another request is using it** ✔ ([shared.py:594-610](../src/app/shared.py#L594-L610)). Two concurrent sessions on different providers keep evicting each other.

**Recommendation.** Decompose it:
- paths → runtime paths;
- settings → a typed settings service with optimistic concurrency;
- secrets → the secret store only (no plaintext files);
- providers → a provider service with a keyed, reference-counted cache;
- utilities → `app.text`.

Remove the document callbacks and all file fallbacks.

### X5 — Contracts are mostly untyped (High)

**Evidence.**
- 274 handlers are excluded from OpenAPI, including every characters and assistant-memory route, 102 of 112 gateway RPG routes (among them the turn route the web client calls), and 16 trading routes.
- Only 36% of the `/api` paths the UI calls exist in the schema.
- RPG uses `Dict[str, Any]` 13,403 times against 74 Pydantic models, and redefines `_safe_dict` in 513 files.
- The web has 272 handwritten payload types.
- 85 `as T` casts with no runtime validation; Zod is a dependency but is never imported.
- 24 web files define their own request helper.
- `client.ts:889-966` constructs a "completed" `JobRecord` with `as unknown as JobRecord`.

**Recommendation.**
- Every browser route gets request and response models and appears in the schema; other routes are classified as internal, with auth.
- One client typed against the generated `paths`.
- Runtime validation at stream and event boundaries.
- Typed domain models replace dict plumbing in RPG.

### X6 — Dead, duplicate and parallel implementations (Medium)

**Evidence.**
- **RPG:**
  - 29% (≈108K lines) unreachable from the gateway; 82K of that is reached only by tests, 21.6K by nothing.
  - `rpg/api` (7.2K lines) duplicates mounted routes.
  - 48 class names are defined in more than one file (4 `ActionResolver`, 3 `NarrativeDirector`).
  - 7 files are hidden behind same-named packages.
- **Memory:** v1 (6.7K lines) and v2 (8.5K lines) both exist in full.
- **Trading:** AI shadow v1, v2 and v3 all run by default at 15-second intervals, and 21 files carry version suffixes.
- **Characters:** 19 deployment-rehearsal harness files (5.1K lines) ship inside the domain package.
- **assist_core:** 7 modules are never imported.
- **Web:** 92 unreachable modules (5.6K lines), with 72 test files that test only them.
- **Other dead or stub code:**
  - `live_chat_speculative_tts.py` (667 lines) is never referenced.
  - `/v1/realtime` is mounted but is a stub that echoes text and emits fake audio.
  - `openai_api.py` is a placeholder.

**Recommendation.**
- Build a reachability report into the repository.
- Delete verified-dead code through a documented deletion protocol.
- Retire parallel versions behind configuration, with operator approval for strategy versions.

### X7 — How the code grew explains the architecture (Context)

**Evidence.**
- 10,934 commits in about 7 months, peaking at more than 100 commits a day in August.
- Deleted/added line ratios per domain are 0.05–0.19. Healthy long-lived codebases usually sit well above that as refactoring removes code; that comparison is a qualitative benchmark, not a measurement.
- RPG, the largest domain, has had almost no changes since July 2026. It is roughly 55–60% of backend code and marked "work in progress".
- Module names reveal the pattern: `*_fixes`, `*_refinements`, `*_hardening`, `*_reliability`, `*LayoutFix.css`, `*_compat`.

**Implication.** Without automated guardrails, any cleanup will erode again at this commit rate. The roadmap therefore puts ratchets and lints **before** refactors.

---

## 6. Security findings

### SEC1 — No identity, authentication or authorization (Critical)

**Evidence.**
- There are 0 `Depends(`/`dependencies=` auth guards across 767 route decorators.
- The only middleware is request metrics plus CORS ([gateway/main.py:229-243](../src/app/gateway/main.py#L229-L243)) ✔.
- Every request runs as `local_tenant_context()`, a hard-coded owner/admin/member of `workspace:local` ([persistence/tenant.py:79-85](../src/app/persistence/tenant.py#L79-L85)) ✔.
- 20 repositories default to it.
- `TrustedPrincipal` exists but is never used.
- Internal Hermes routes are only hidden from the OpenAPI schema.
- The worker protocol routes `/api/jobs/claim|complete|fail` are public ([core_jobs_routes.py:74-92](../src/app/gateway/core_jobs_routes.py#L74-L92)).
- The Nginx example proxies all of `/api/*` without auth, over plain HTTP.

**Impact.** Anything that can reach a gateway port can:
- read and modify every record;
- run Gmail, GitHub, browser and Kasa tools;
- start agent runs that execute code;
- change credentials and settings;
- finalize jobs.

No action is attributable to a person.

**Recommendation.**
- Pluggable authentication: a `local` mode with an install token and session cookie, and an `oidc` mode.
- A per-request principal and `TenantContext` dependency, denied by default.
- An RBAC permission catalog.
- Row-level security.
- Authenticated internal APIs for the worker protocol and model services.

### SEC2 — Approvals are asserted by the client (Critical)

**Evidence.**
- [assistant_tools/gate.py:48](../src/app/assistant_tools/gate.py#L48) takes `approval_policy` from the request body. Line 62 makes the tool executable when `request.approved` is true ✔.
- The web client sends `approved: true` ([assistantToolConfigClient.ts:164-174](../src/apps/web/src/features/chatbot/assistantToolConfigClient.ts#L164-L174)) ✔.
- The ledger then records the approval as coming from the "user" (`hermes_bridge.py:138`).
- Agent runs:
  - The client chooses `approval_policy="allow_automatic"`, `allowed_paths=["**"]`, the workspace root and the isolation level (`agent_runtime/api.py:56-75`).
  - Approvals are resolved through `POST /api/agent-runs/{id}/commands` and recorded as `{"source":"agent_run_command"}` with no approver.
  - The broker and model gateway trust only the run id. The agent has that id in its environment, and approval ids are deterministic and echoed back to it.

**Impact.** "Approval cannot expand grants" holds inside the broker, but anything outside it — including test code the agent writes and runs — can approve the agent's own requests.

**Recommendation.**
- Record approvals server-side, bound to an authenticated approver, a proposal digest and an expiry.
- Remove `approved`/`approval_policy` from public request models.
- Give the broker and model gateway HMAC-signed run tokens that shell children do not inherit.

### SEC3 — Exposure to the LAN, any web page, and DNS rebinding (Critical)

**Evidence.**
- The launcher runs `npm run web:dev`, which is `vite --host 0.0.0.0` ([src/apps/web/package.json](../src/apps/web/package.json)) ✔. It proxies `/api`, `/events` and WebSockets to the gateway, which defeats the gateway's 127.0.0.1 bind.
- STT binds `0.0.0.0` with `allow_origins=["*"]` plus `allow_credentials=True` and no auth ([nemotron_eou_stt_server.py:29-35,192](../src/nemotron_eou_stt_server.py#L29-L35)) ✔.
- `openai_api.py` and spawned `llama-server` also bind `0.0.0.0`.
- No CSRF protection, no Origin check on WebSockets, no Host allow-list.
- 35 parameterless POST routes can be triggered by a cross-site "simple request" with no preflight, e.g. launcher `stop-all`, image import and Codex login.

**Recommendation.**
- Loopback by default, with explicit opt-in for LAN access.
- Host allow-list.
- Origin check on state-changing HTTP and on WebSocket upgrades.
- A required custom request header, or a CSRF token, on every state-changing request.

### SEC4 — Committed secret (Critical)

**Evidence.** [src/app/data/settings.json](../src/app/data/settings.json) is tracked ✔. Its `cerebras.api_key` is a 52-character value with the `csk-` prefix ✔; the value is not reproduced here.
- The file is orphaned: the runtime reads `resources/data/settings.json`.
- It has been in history since at least commit `637220e19`.
- It ships in Docker images via `COPY . .`.

**Recommendation.**
- Rotate the credential (human action).
- Delete the file.
- Purge history (human-coordinated).
- Add gitleaks to pre-commit and CI.

### SEC5 — Unauthenticated model services and worker endpoints (High)

**Evidence.**
- TTS, STT and image services have no auth.
- The TTS service returns tracebacks in error responses (`src/tts_server.py:583`).
- STT reads whole uploads with no size cap.
- The compat job adapter's fencing check always passes (see PJ3), so any HTTP client can complete or fail any job.

**Recommendation.**
- Service tokens (or mTLS) between gateway and model services, with loopback binding.
- An internal router for the worker protocol that requires a service token and a lease token.
- Size limits on uploads.
- Generic error bodies that carry a request id.

### SEC6 — Agent execution is not sandboxed and network policy is not enforced (High)

**Evidence.**
- The default `supervised_worktree` is a plain `Popen` ([isolation.py:45-50](../src/app/agent_runtime/isolation.py#L45-L50)).
- `network_policy="broker-only"` is only exported as an environment variable and logged.
- The command prefixes `python -m pytest` and `npm run build` are treated as safe, so they run agent-written code with no approval.
- `HOME` is passed through to the agent.
- There is no allow-list of workspace roots.
- `browser.open` with `workspace_preview` runs agent-controlled `npm run dev` on the host from the gateway process, even under `docker_strong`.
- There is no global cap on Pi processes.

**Recommendation.**
- Mutating profiles run sandboxed by default, with egress only through a broker proxy.
- Workspace-root allow-list.
- Global run semaphore.
- The preview server runs inside the sandbox.
- Unsandboxed mode is an explicit, documented operator opt-in.

### SEC7 — Settings allow SSRF and destructive side effects; information disclosure (Medium)

**Evidence.**
- `POST /api/settings` accepts a raw dict, and provider `base_url` values are not validated.
- The llama.cpp provider runs `kill -9` on whatever owns the configured port, and accepts absolute model paths.
- `GET /api/assets` returns absolute `storage_path` values.
- `/docs` is enabled.
- Raw exception text is returned to clients in several places.
- There is no global exception handler (only the launcher has one).

**Recommendation.**
- Typed settings with URL validation; block link-local and metadata addresses.
- Never kill arbitrary processes.
- Return asset ids, not paths.
- A problem+json error envelope.
- Protect or disable `/docs` in production.

### SEC8 — No audit trail for sensitive actions (Medium)

**Evidence.** Beyond the bootstrap spam (DATA/OPS), there are only 9 audit write sites. Settings, credential, approval and trading-control changes are not audited.

**Recommendation.** Emit append-only audit events with principal, action, target, outcome and request id for every sensitive action.

---

## 7. Performance findings

### PERF1 — The event loop is blocked by synchronous work (Critical)

**Evidence.**
- 229 `async def` HTTP handlers never await ✔. They call synchronous PostgreSQL-backed services directly, for example `service_factory().list(...)` in [characters/api.py:129-130](../src/app/characters/api.py#L129-L130) ✔.

  | Package | Async handlers that never await |
  |---|---|
  | characters | 41 of 41 |
  | assistant_memory | 25 of 25 |
  | gateway | 68 |
  | trading | 31 (36 of 120 per the trading audit) |
  | RPG gateway routes | 76 of 78 async handlers don't offload |
  | image | 13 |
- The compensating [blocking_route_offload.py](../src/app/gateway/blocking_route_offload.py) covers 8 routes. It works by replacing `route.dependant.call` and runs coroutines in a new event loop per call via `asyncio.run` ✔.
- The RPG turn pipeline offloads only `apply_turn`. Session load, canonical narrative generation, shadow narrative generation (sampled at 100% by default) and the full-state save all run on the loop.
- The TTS service runs synchronous CUDA synthesis inside `async` handlers.
- A cold TTS provider lookup can block the live-call websocket loop.

**Impact.** One RPG turn or slow query stalls live voice frames, SSE and lock supervision for everyone in the process.

**Recommendation.**
- Handlers doing synchronous I/O become `def` (FastAPI's thread pool) or offload explicitly.
- LLM generation moves to jobs or bounded executors.
- Add a lint rule that forbids an `async` handler without `await`, with a ratchet down to 0.
- Delete `blocking_route_offload`.
- Add an event-loop-lag SLO test.

### PERF2 — Migrations and tenant bootstrap run on request paths (Critical)

**Evidence.**
- `bootstrap_local_tenant` calls `apply_migrations` and appends a `workspace.local_bootstrap` audit row on every call ✔ ([identity_service.py:19-35](../src/app/persistence/identity_service.py#L19-L35)).
- It has 132 non-test call sites, 111 in RPG, including once per RPG turn, on plain reads, and in every `rpg_compat` function. [rpg/worlds/postgres_service.py](../src/app/rpg/worlds/postgres_service.py) alone calls it 10 times ✔.
- Each call hashes all 118 migration files twice, takes one global `pg_advisory_xact_lock`, runs about 17 statements, and writes an audit row.
- Compat store constructors and uncached factories trigger it too. That includes every character-mode chat prompt via [runtime_composition.py:45-62](../src/app/runtime_composition.py#L45-L62).

**Impact.**
- All processes serialize on one lock.
- Reads write to the database.
- The audit table fills with noise.
- The runtime database role needs DDL rights.
- Rolling upgrades are impossible (SCALE4).

**Recommendation.**
- Migrations become a one-shot release step.
- Tenant context is resolved once at startup (later, per request) and injected.
- Remove every bootstrap call from domain and compat code.

### PERF3 — Whole-document persistence (High)

**Evidence.**
- **RPG, per stateful turn:**
  - reads the full `state_jsonb` with `FOR UPDATE`, re-hashes it, rewrites it in full, snapshots it in full, then `save_session` rewrites it again;
  - serializes canonical JSON about 5 times;
  - listing sessions loads up to 1,000 full documents and slices in Python.
- **Settings:** one global document, read and rewritten whole.
- **Chat:** `save_sessions` rewrites up to 200 sessions with full transcripts and soft-deletes any active session missing from the list (CM1).
- **Document store:** writes are last-writer-wins.

**Recommendation.**
- Targeted row mutations.
- Typed hot sub-state, with deltas and periodic snapshots.
- Summary columns for list views.
- Optimistic concurrency (a revision column) on document tables.

### PERF4 — Provider transport and caching (High)

**Evidence.**
- Zero pooled HTTP clients; 35 direct `requests.<verb>()` calls create a new connection each time.
- `max_retries` is defined but never used.
- A single 300 s timeout covers connect and read.
- A circuit breaker exists only for live STT.
- Cancellation exists only for LM Studio, through a private `_cancel_event` kwarg.
- Single-slot provider cache (X4).
- The Codex provider holds one lock for an entire streamed turn. Cancelling any chat job terminates the shared Codex process, and by inference that can kill another job's turn.
- The agent capability registry and MCP policy are rebuilt from disk about 10 times per broker call.

**Recommendation.**
- A `ProviderSpec` registry.
- One pooled `httpx.Client` per provider, with separate connect and read timeouts.
- Retry and circuit-breaker middleware for idempotent calls.
- A cancellation token protocol.
- A keyed, reference-counted provider cache.
- One Codex turn per request.
- Cache capability data, invalidating only when it changes.

### PERF5 — Event delivery polls per subscriber and can skip events (High)

**Evidence.**
- Each SSE subscriber polls the database every second on a thread ([live_job_events.py:70-100](../src/app/gateway/live_job_events.py#L70-L100)).
- There is no `LISTEN`/`NOTIFY` anywhere.
- The cursor is `id > last` on an identity column, so an event whose transaction commits after a later id has already been read is skipped for good.
- The Docker default entrypoint serves a different, less resilient `/events` implementation than `runtime_app.py`.
- In the web app, the shared SSE client is used only by Platform; elsewhere there are 28 `setInterval` pollers and 48 `refetchInterval` settings.

**Recommendation.**
- One reader per process, fanning out to subscribers, woken by `NOTIFY`.
- A commit-safe cursor using a transaction-id column checked against the snapshot xmin.
- Bounded subscriber queues.
- One implementation.
- Web features subscribe to events instead of polling.

### PERF6 — Event logs are used as query stores (High)

**Evidence.**
- **Agent runtime:**
  - Every streamed token delta (`message_update`) is persisted.
  - Each append locks the run row `FOR UPDATE`, computes `MAX(sequence)+1`, and inserts an event row plus an outbox row.
  - One RLock shared by all runs is held during persistence, Pi spawns, git diff capture and promotion.
  - 11 call sites use `list_events(after_sequence=0, limit=5000)`, which returns only the **oldest** 5,000 events. Acceptance, validation and the promotion marker would silently ignore later events.
- **Trading:**
  - Monitors read 20K–50K events per cycle.
  - Qualification uses an ascending `LIMIT 20000`, silently dropping the newest evidence.
  - The paper authorization wrapper loads 20,000 events on every buy.

**Recommendation.**
- Stop persisting token deltas.
- Per-run sequencing without a run-row lock.
- Typed projection tables with indexes, or paged queries, for decisions.
- Per-run locking.

### PERF7 — Media is buffered and base64-encoded (Medium)

**Evidence.**
- The TTS service builds a whole WAV before replying, and the gateway facade reads the whole response before re-framing it.
- The TTS client base64-encodes audio.
- STT audio travels as base64 inside JSON frames.
- TTS results store base64 WAV in the job row's `output_refs`, and voice samples ride in `input_payload`.
- Generated audio is stored three times: a `voice_studio` file, a blob copy, and base64 in the job row.
- Uploads are read whole.

**Recommendation.**
- Binary streaming end to end.
- Store assets through the blob store and put only asset references in job rows.
- Streamed uploads with size caps.

### PERF8 — Frontend rendering (Medium)

**Evidence.**
- No list virtualization.
- `watch('content')` at the top of Chat re-renders on every keystroke, and each render re-parses the markdown of every message.
- A 1-second clock state re-renders each chart panel.
- `pixi.js` is loaded statically with Chat.
- 24 stylesheets (8.1K lines) are loaded up front.
- At least 12 document-wide `MutationObserver`s with `subtree:true`, and six panels that poll `innerText` every 1–1.5 s.
- Zero uses of `React.memo`.

**Recommendation.** Covered by the frontend work in the roadmap: virtualization, memoized markdown, lazy avatars, removing DOM scraping, and CSS loaded with its feature.

---

## 8. Scalability findings

### SCALE1 — One worker process owns almost everything (High)

**Evidence.** The single worker-role gateway runs:
- every monitor (about 21 trading monitors on by default);
- recovery and schedulers;
- most trading HTTP (only `GET /api/trading/(bars|quotes)` goes to API replicas);
- all live voice (pinned by `X-Omnix-Gateway-Affinity: worker`);
- local TTS.

TTS synthesis is serialized per process ([tts_priority.py](../src/app/providers/tts_priority.py), [live_voice_execution_lane.py](../src/app/gateway/live_voice_execution_lane.py)). By inference, capacity is about 1–2 simultaneously speaking calls per worker/GPU.

**Recommendation.**
- Separate the singleton scheduler from job execution.
- Job worker pools by resource class, which can run on any host.
- Scheduled tasks each take their own advisory lock, so they can spread across schedulers.
- Live voice on API replicas with session-affine routing when remote TTS is configured.

### SCALE2 — State that must be shared is held in process memory (High)

**Evidence.**
- **Agent runtime:**
  - global RLock;
  - in-memory registry of Pi sessions;
  - supervisor daemon threads that start lazily on first `get()`, so nothing is recovered after a restart until something calls the service;
  - a command for a Pi session hosted in another process updates the database but never reaches Pi.
- **RPG:**
  - session and submission locks in in-memory maps;
  - narration jobs inside the session JSON, served by an in-process thread.
- **Chat:**
  - the whole-workspace save race (CM1);
  - speculation caches.
- **Memory:** jobs run on a process-local executor that never replays abandoned work.
- **Trading:** range-backtest results and the execution-plane instruments are unbounded in-memory maps.

**Recommendation.** Keep durable state in PostgreSQL; process caches may exist only as optimizations. Maintain an inventory of process-local state, allowing only approved exceptions.

### SCALE3 — GPU capacity is not owned across processes (High; R5 open)

**Evidence.**
- Limits are per-process, per-feature semaphores: chat 4, image 2, memory 1, world-forge 4.
- SSE chat, live voice and speculation bypass all of them.
- The image service itself has no limit.
- Job claims drop residency information (`job_compat.py:139`).
- The worker gateway can load local TTS while the launcher also starts `tts_server.py`, and an optional live lane loads a third copy.

**Recommendation.** PostgreSQL-leased device permits per device and model class, with priority realtime > interactive > batch, and a single owner per model.

### SCALE4 — Rolling upgrades are impossible (High)

**Evidence.**
- Running processes apply migrations (PERF2).
- Any applied schema version the code doesn't know raises `MigrationDriftError`, so older replicas fail as soon as a newer one migrates.
- The schema ceiling is `9999`, so there is no real N/N-1 compatibility contract.

**Recommendation.**
- Migrations as a release step.
- An expand/contract policy.
- An explicit compatibility window.
- Graceful drain.

### SCALE5 — Blob storage is tied to the local filesystem (High)

**Evidence.**
- The `BlobStore` protocol in [persistence/contracts.py](../src/app/persistence/contracts.py) is imported by no module.
- `LocalBlobStore` is constructed directly in 7 files.
- Absolute `storage_path` values are read in 21 files across 9 packages.
- Voice clones are discovered by scanning directories.
- Image assets point at the image service's own disk.

**Recommendation.**
- Use the protocol everywhere.
- Store blob keys, never paths.
- Add an S3-compatible adapter (with MinIO for tests).
- Keep the local adapter as the default.

### SCALE6 — Single tenant only (Medium)

**Evidence.**
- The workspace is hard-coded `workspace:local` and pinned per adapter.
- Row-level security is explicitly deferred (migration 0012, line 101).
- Workspace filtering is a per-query convention.
- Positive: the schema already uses composite `(workspace_id, id)` foreign keys.

**Recommendation.** A per-request `TenantContext`, row-level security set per transaction, and isolation tests.

### SCALE7 — No connection budget across processes (Medium)

**Evidence.**
- Each process has its own pool, default maximum 10, with no budget across processes.
- The worker permanently holds one pooled connection for its advisory lock.
- Each unit of work spends 3 extra round trips on authority checks.
- Compat operations open 2–4 transactions each.

**Recommendation.**
- Configure a per-role pool budget from the database's `max_connections`.
- A dedicated connection, outside the pool, for the advisory lock.
- One authority check per transaction.

---

## 9. Data architecture findings

### DATA1 — No retention, so append-heavy tables grow without bound (High)

**Evidence.**
- Retention policies are seeded (migration 0016), but `PostgresLifecycleRepository` is used only by one test.
- Nothing deletes:
  - jobs, attempts or dead letters;
  - job events;
  - audit events;
  - RPG turns, interactions or snapshots;
  - agent events;
  - trading events;
  - runtime nodes.
- `omnix_rpg_snapshots` is never read.
- The capacity limits in migration 0016 are never enforced.

**Recommendation.** A retention worker (worker role) that executes the policies in batches and records its runs. Partition the highest-volume tables once measured thresholds are crossed.

### DATA2 — The outbox is written but never read (High)

**Evidence.**
- Every RPG turn and agent-runtime event writes to the outbox.
- `claim_batch` ([outbox_repository.py](../src/app/persistence/outbox_repository.py)) has no production caller.
- Cleanup removes only rows marked `published`, which never happens.

**Recommendation.** Either build a relay with registered consumers and `NOTIFY`, or stop writing event types that have no consumer. The roadmap chooses the relay.

### DATA3 — JSONB document modelling on hot paths (Medium)

**Evidence.**
- 170 of 222 tables (77%) have JSONB; there are 525 JSONB columns, and 48 tables have 4 or more.
- There are only 2 GIN indexes in the whole schema.
- History search runs `COUNT(*)` plus an unindexed `ILIKE` on every turn.
- The conversation-summary lookup scans up to 5,000 documents in Python.

**Recommendation.**
- Promote fields that are queried or updated into typed columns.
- Validate document shapes.
- Use `pg_trgm` or full-text indexes for search.
- Add optimistic concurrency.

### DATA4 — Migration discipline (Medium)

**Evidence.**
- 16 numeric prefixes are duplicated, plus `0008z`.
- Pending migrations are computed as a set difference, so a late-added low number applies out of order.
- All pending migrations run in one transaction, with no `CONCURRENTLY`.
- Migration 0083 was edited after being applied; a legacy checksum allow-list exists.
- The runtime role needs DDL rights, contradicting the `migration_role_separate` policy in migration 0012.

**Recommendation.**
- Strict ordering, with a gate that forbids new duplicate prefixes and out-of-order additions.
- Support for non-transactional `CONCURRENTLY` migrations.
- Expand/contract phase metadata.
- Separate migration and runtime database roles.

### DATA5 — Unbounded and capped queries (Medium)

**Evidence.**
- 29 of 63 `fetchall()` calls in persistence, jobs and assets have no `LIMIT`.
- 28 sites cap results at 500. That includes asset listing (R6), with the image gallery filtering the capped list in Python.
- Duplicate checks scan the 500 most recent jobs.
- Every 250 ms, each job claim runs a workspace-wide `UPDATE` to release expired leases.

**Recommendation.**
- Cursor pagination through repository, service and API.
- Filters pushed down to SQL.
- Targeted queries for active work.
- Lease release on a scheduled interval.

---

## 10. Observability, operations and delivery findings

### OPS1 — Logging, metrics and tracing are bespoke and not correlated (High)

**Evidence.**
- **Logging:**
  - No central logging configuration.
  - At least 8 separate file sinks; `app/logging.py` has no retention.
  - 198 `print()` calls, 353 logger calls, and 183 silently swallowed exceptions.
  - No request-ID middleware; correlation IDs exist only inside domain events.
- **Metrics and tracing:**
  - Metrics are three in-process counters (`platform/runtime_diagnostics.py`).
  - No Prometheus, OpenTelemetry or tracing.
- **Privacy:**
  - Agent debug logs capture prompts and are documented as opt-in, but `start_all.bat` turns them on.
  - Voice logs store unsalted SHA-256 fingerprints of text, which the project's own content-free policy strips elsewhere.

**Recommendation.**
- Central structured logging with context variables (request id, job id, run id, workspace id).
- A Prometheus metrics catalog.
- Optional OpenTelemetry tracing.
- A problem+json error envelope carrying the request id.

### OPS2 — Configuration sprawl (Medium)

**Evidence.**
- 290 environment variable names are read at 388 sites in 178 files, plus 103 reads with non-literal names.
- About 19 are validated centrally.
- There are 59 ad hoc env helper functions.
- 44 `*_ENABLED`/`*_MODE` flags exist with no registry.
- `OMNIX_PERSISTENCE_MODE` is re-read in 26 trading monitors.
- The Hermes endpoint appears under 3 names on 2 ports.

**Recommendation.**
- A typed configuration package; each feature declares its config model through `FeatureModule`.
- All environment reads go through it, with a ratchet on direct `os.environ` reads.

### OPS3 — Read paths write to the database (Medium)

**Evidence.** Bootstrap on read paths writes `workspace.local_bootstrap` audit rows and runs DDL checks (PERF2), which floods the audit log.

**Recommendation.** Covered by PERF2.

### DEL1 — CI does not gate the product (High)

**Evidence.**
- **Workflows:**
  - Of 28 workflows, 8 are manual-only, 12 are path-filtered and 6 run on every PR.
  - None runs the full Python suite.
  - CI installs ad hoc, unpinned package lists, never `requirements.txt`.
  - Two workflows downgrade typecheck failures to warnings.
  - `vite build` is not run.
  - The mocked app-shell Playwright spec never runs.
  - One self-committing workflow with `contents: write` was never removed.
- **Lint and types:**
  - Ruff runs only on enumerated files; `ruff.toml` selects no rules, it only lists per-file ignores.
  - There is no mypy or pyright, so undefined names survive (e.g. `npc_initiative.py:416`, which `sitecustomize.py` hides).
- **Versions:**
  - CI uses Python 3.12 while deployment uses 3.10.
  - Trading imports `StrEnum` only because `trading/__init__.py` patches the standard-library `enum` module.
  - Node floats at "22", and 11 of 13 workflows use `npm install` rather than `npm ci`.

**Recommendation.**
- One required CI pipeline: lint, type, unit (sharded), PostgreSQL integration, web (lint, test, build, api:check, e2e shell), security scans.
- A nightly full suite.
- Pinned toolchains.

### DEL2 — The test estate is unhealthy (High)

**Evidence.**
- **Collection:**
  - `pytest.ini` `testpaths = e2e api integration unit` covers about 17% of test files ✔.
  - The last full run had 1,278 failed and 358 errors.
- **Root conftest:**
  - Imports Playwright unconditionally.
  - Points at the retired Flask port 5000.
  - Resets a globally monkeypatched `Path.write_text` before every test.
  - Its `flask_app` fixture builds the production PostgreSQL app, so dependent tests error instead of skipping.
- **Stale and fragile tests:**
  - 77 files reference retired contracts, e.g. `SQLiteJobStore`, Flask `test_client`, FastAPI's nonexistent `config` attribute.
  - 55 fixed-duration sleeps in 33 files.
  - Tests are generated from 187 `.pyfrag` fragments.
  - 106 tests live inside `src/app/rpg`.
- **Balance:**
  - RPG accounts for 52% of test files; assistant tools (Gmail, GitHub, browser, Kasa) have 16.
  - The web app has 4 Playwright specs and no ESLint.
- **Broken runner:** the root `run_tests.py` is pasted prose and raises `SyntaxError`.

**Recommendation.**
- Triage every failure into fix, rewrite, or delete-with-justification.
- A quarantine list with owners, driven to zero.
- Collect the full tree.
- Replace sleeps with deterministic synchronization.
- Move tests out of `src/app`.

### DEL3 — Builds are not reproducible (High)

**Evidence.**
- **Python dependencies:**
  - No `pyproject.toml`, lockfile or constraints.
  - Five requirement files.
  - `requirements.txt` mixes gateway, ML (diffusers, transformers, deepfilternet, onnxruntime) and test dependencies (pytest, playwright), with `>=` ranges.
- **Dockerfile:**
  - Single stage on `cuda:12.4.0-devel`, running as root.
  - Installs torch 2.5.1, then force-reinstalls 2.6.0.
  - Forces transformers 4.46.3, while the TTS requirements file pins 4.57.3.
  - Bakes the Parakeet model and a Mistral-7B GGUF into the gateway image and swallows download errors.
- **Setup:**
  - `setup.bat` installs torch 2.5.1+cu124, then installs a file requiring `torch>=2.6`.
  - psycopg is never installed on the setup path, although PostgreSQL is mandatory.

**Recommendation.**
- Per-runtime hashed lockfiles.
- A slim, non-root, multi-stage gateway image, with separate GPU service images on CUDA runtime bases.
- Model acquisition outside image builds.
- One supported Python version.

### DEL4 — Deployment is tied to one machine (Medium)

**Evidence.**
- `C:\Users\unx47\…` is hard-coded in `start_all.bat:8-10`, `launcher/service_manager.py:452-454` and `setup.bat:10`.
- `start_all.sh` is broken: it kills ports 5000/8000, runs a nonexistent `app.py`, and an unquoted `>=0.2.4` becomes a shell redirect.
- Compose defaults the database password to `omnix`.
- The Nginx example serves plain HTTP with no auth or rate limiting, and lets the client choose the backend through a header.
- Ports clash: 8001 is used by `openai_api.py` and an API replica; 8080 by llama-server and Nginx.

**Recommendation.**
- Parameterize the launcher.
- Repair or delete stale scripts.
- Compose profiles with required secrets.
- A hardened ingress.

### DEL5 — Repository hygiene (Low)

**Evidence.**
- 16.7 MB of voice-clone WAVs, some named after real people — a consent and licensing risk.
- Runtime trading activity logs committed under `resources/trading/`.
- The git pack is 240 MiB, of which about 194 MB is history-only blobs (`src/tests.zip`, `src/app/rpg.zip`, test result zips, node_modules binaries).
- `src/temp_debug_presentation.py` is debug debris.
- `src/__init__.py` imports modules that don't exist.
- The dead `llamacpp_installer.py` would install unverified wheels from personal GitHub repos.
- `generate_certs.py` hard-codes a LAN IP.

**Recommendation.** Remove runtime data from git, make an explicit consent decision about voice data, and plan a history purge coordinated by a human.

---

## 11. Subsystem reviews

### 11.1 Persistence, jobs, events and assets — 4/10

Strengths are listed in section 4. Findings not covered above:

- **PJ1 — Tenant bootstrap everywhere (Critical).** See PERF2. There are 18 `ensure_postgresql_runtime_ready` calls. `database.transaction()` skips the authority check and has 123 call sites. The retry helper `run_transaction` has 0 callers.
- **PJ2 — Whole-workspace chat save (High).** See CM1.
- **PJ3 — Job fencing gaps (High).**
  - `job_compat.complete_job`/`fail_job` read the current owner and lease token from the row, then pass the same values into the fenced repository call, so the check always passes ✔ ([job_compat.py:219-299](../src/app/persistence/job_compat.py#L219-L299)).
  - `CompleteJobRequest` has no token field.
  - The durable worker verifies the lease in one transaction and finalizes in another.
  - `update_progress`, `update_job_input`, `update_job_stages`, `finalize_cancel` and `delete_job` are not fenced.
  - The log update rewrites job metadata without a row lock and can erase concurrent cancel metadata.
  - There is no status CHECK constraint.
  - Retry delay is 0, with no backoff.
  - Priority has no aging.
  - One pool of 4 is shared by all resource classes.
- **PJ4 — Raw SQL on platform tables from features (Medium).** 98 raw SQL statements against the jobs table sit in 21 files, 57 of them outside persistence (e.g. a raw `DELETE` in `rpg/worlds/generation_worker.py:210`). There are 416 `from app.persistence` imports across 186 files.
- **PJ5 — Compat adapters lose provenance (Medium).** `asset_compat` drops `source_job_id` and owner, and its update path spans 3 non-atomic transactions. The `/events` stream differs between entrypoints.
- **PJ6 — Compat share (Info).** 17 `*_compat.py` files (4,502 lines, 22% of persistence) and 21 `rpg_*` files (25.6% of persistence).

### 11.2 Agent runtime and assistant tools — 4/10

- **AR1 — God service held together by global patch seams (High).**
  - `AgentRunService` spans `service_core.py:219-2699` and a subclass in `service.py:565-2639`: 4,556 lines, 73 methods, 11 overrides, including a near-copy of `start_child`.
  - It covers lifecycle, steering, git diff capture, promotion, GitHub binding, supervision and the quality state machine.
  - SQL outside repositories: `service_core` 10 statements, `planning_api` 4, `budget` 3; `workflow_runtime` has 51 and no repository.
  - `chat_bridge.py` is orchestration: it routes 5 lanes, and `route_typed_chat_turn` alone is 735 lines. It duplicates the regex intent logic in `profiles`, `router` and the semantic classifier.
- **AR2 — The broker is not the single choke point (High).**
  - `hermes_assistant_tool_execute_payload` is reached from 9 call sites: broker, chat_bridge (2), task_graph_runtime, workflow_runtime, the assistant_tools route, `live_agent_planner`, and `chat/live_agent_store` (2).
  - Only the broker applies RunSpec, resource-scope, durable-execution and evidence rules.
  - Workflows can be registered over unauthenticated HTTP.
  - Unmapped tools fail open: dispatch returns `adapter_status: pending` with no error.
  - Local tools are policed only by the in-process TypeScript guard.
  - The broker endpoint does not charge tool budget or wall time.
- **AR3 — Durability and concurrency (Medium/High).** See PERF6 and SCALE2. Also:
  - `update_state` has no lease-token fencing.
  - `start_child` holds the parent row `FOR UPDATE` while creating a worktree and possibly running `npm ci` for up to 900 s.
  - `POST /api/agent-runs` does worktree creation, dependency install and Pi spawn inside the request thread.
  - 27 silent `except Exception` blocks.
- **AR4 — Extensibility is code-first (Medium).**
  - A new capability touches `capabilities.py`, `profiles.py`, a new adapter, the if/elif in `hermes_bridge.py`, `config_store.py` and `evidence.py` — and more for worker-zone capabilities.
  - A new profile touches profiles (including a regex selector), the semantic classifier, evidence, task_graph, chat_bridge, and 50 hard-coded `"coding"` checks across 18 files.
  - Only MCP tools and workflows are declared as data.
- **AR5 — Four overlapping packages (Medium).**
  - `assist_core` is 103 micro-modules (median 33 lines): 62 are `hermes_*`, 37 of those `hermes_rpg_*`, and 7 are never imported.
  - `assistant_context` is a route grab-bag that registers memory, character, avatar, desktop and TTS routes.
  - The canonical capability registry lives in agent_runtime but is projected from assistant_tools.
  - `assistant_turn_routes.py` and `assistant_context_routes.py` are unused.
- **AR6 — Catalog drift (Low).**
  - `gmail.send_email` is issued to a profile but not implemented.
  - Gmail silently falls back to a fake adapter when credentials are missing.
  - The default budget limits set no token or cost cap.

### 11.3 Trading — 4/10

- **TR1 — Import-time patches define production behaviour, including entry authorization (Critical).** See X1.
  - `evaluate_gap_pullback` is rebound in six modules.
  - `alpaca_iex._parse_timestamp` is patched.
  - 11 modules are named `*_fixes/_refinements/_hardening/_reliability`.
- **TR2 — No strategy or monitor contract (High).**
  - Strategy kinds are a closed `Literal["gap_pullback_v1","stoch_rsi_5m_v1"]` with a union and an if/else row mapper (`strategy_repository.py:30,34,113-117`). Adding one touches 8 or more backend modules plus the frontend.
  - Every other capability — AI shadow v1/v2/v3, deep recovery, prospective gap/economic, Solana, interday discovery — is its own module with a copy-pasted start/stop/loop monitor.
  - [trading_routes.py](../src/app/gateway/trading_routes.py) hard-wires 18 routers and 22 monitors ✔.
  - There are 83 `strategy_*` modules (42.5K lines).
- **TR3 — One worker, one event loop, blocking work (High).**
  - CPU-bound Decimal evaluators run on the loop, processing candidates one at a time.
  - The execution-observation monitor fans out one `to_thread` call per candidate every 3 s onto the default executor, behind a 4-slot provider semaphore.
- **TR4 — Risk is not enforced at one place, and the ledger accepts exposure nobody intended (High).**
  - `place_order` checks only cash, idempotency and the account `enabled` flag.
  - Risk checks are spread across four callers.
  - The patched authorization wrapper skips sells and uses the latest risk decision for the instrument rather than the order's own attempt.
  - A sell on a flat position opens a short and credits cash, although shorting is documented as deferred.
  - The kill switch is per strategy only; the global stop is an environment variable plus a restart.
  - Order replace is a cancel and a place in separate transactions.
- **TR5 — Decision inputs live in local JSON files, outside PostgreSQL and outside lock protection (High).**
  - Yahoo 1-minute evidence, IBKR promotion evidence, disk caches, and a climatology file read by relative path.
  - The premarket handoff is fetched from GitHub `main` by running `gh api` from a monitor, on by default.
  - Yahoo stamps `received_at=now` even on cache hits, and `received_at` is part of the revision identity. Every call therefore appends a new revision per bar and rewrites the whole symbol-day file.
  - This contradicts ADR-0004 §6.
- **TR6 — Nominal provider abstraction (Medium).**
  - The 4-method `MarketDataProvider` Protocol; a registry that hard-codes factories and branches on provider name.
  - Rate limiting is only reactive.
  - One circuit breaker per provider is shared by protective exits and research polling, so by inference exits can starve under 429s.
  - The browser stream opens one upstream Binance socket per client and does not reconnect.
  - The IBKR tick path does file-locked JSON read-modify-write on the network thread.
- **TR7 — Lock protection is check-then-act (Medium).** Each background DB acquisition runs `SELECT 1` on the lock connection under a mutex, which is likely a serialization point. The check is skipped entirely in raw threads. There is no lease epoch or fencing token on mutations.
- **TR8 — AI influence is broader than documented (Medium).**
  - The intraday LLM runs inline before proposals, so order latency depends on LLM latency.
  - Research features acquired under Hermes planning can add +1 quality score each, enough to push a marginal setup over the entry threshold.
  - `OMNIX_TRADING_OPERATIONS.md:172` says AI output is not imported by `strategy_monitor.py`; it is.
  - No path from AI output to an order was found.
- **TR9 — Hygiene (Low).**
  - 77 modules each define their own Eastern-time zone.
  - 38 hard-coded `time(16,0)` session closes ignore early closes.
  - Unbounded in-memory maps.
  - Indicators recompute the full series in pure Python.
  - The web app has ten copies of a `requestJson` helper and 88 hard-coded `/api/trading` paths.

### 11.4 RPG — 3/10

- **RPG1 — Player actions use an unseeded RNG (Critical).**
  - [action_resolver.py](../src/app/rpg/action_resolver.py)'s own docstring says "No randomness without explicit seed".
  - The main-path caller `runtime_part09.py:469` calls `resolve_player_action(gated_state, action)` with no seed ✔.
  - `_make_rng(None)` therefore returns an OS-entropy `random.Random()` ✔, which is used for attack and skill rolls.
  - Replay, state-hash certification, dispute auditing and the README's determinism claim all fail on the main path.
- **RPG2 — Behaviour assembled by runtime mutation (Critical).** See X1.
  - `_apply_turn_authoritative` is defined 15 times and is 965 lines.
  - `apply_turn` is 796 lines.
  - 18 places where one part reassigns another part's attributes.
  - The 1,000-line cap in `check_rpg_file_lines.py` probably drove mechanical slicing into numbered parts (inferred).
- **RPG3 — The turn route blocks the event loop (High).** See PERF1.
- **RPG4 — Whole-document state with write amplification (High).**
  - See PERF3.
  - A save at the same revision with a different hash silently bumps the revision.
  - Narration jobs live inside the session JSON.
- **RPG5 — No inward-pointing core; cycles with platform code (High).**
  - 166 import statements into persistence and about 107 raw `connection.execute` calls against 19 `omnix_rpg_*` tables.
  - RPG edits the platform `omnix_jobs` table directly with UPDATE and DELETE, and monkeypatches the job store for every job type.
  - Positive: the gameplay packages (combat, economy, items, world, social — 311 modules, 62.6K lines) import no platform packages and make no global `random` or `uuid4` calls.
- **RPG6 — Dead and duplicate code (High).** See X6. Also:
  - The Hermes approved flow runs turns through the old `rpg/pipeline.py` and its in-memory `_game_store`, not the real runtime.
  - 58 test-harness, report and autoplay modules (about 13.7K lines) ship in the package.
- **RPG7 — Single-process assumptions (Medium).**
  - `ProfileBoundProvider` sets model, temperature and timeout on the shared cached provider, probably leaking RPG settings into other features.
  - It guesses call signatures by catching `TypeError`.
- **RPG8 — LLM fan-out (Medium).**
  - A foreground turn can make about 5–6 sequential LLM calls: first call, advisories that are on by default, narration, and the canonical and shadow writers.
  - Each call has a 90 s timeout with 2 retries.
  - There is no caching beyond replay records.
- **Reachability method.**
  - An AST import graph over `src` and `scripts`, starting from `app.production`, `app.gateway.main` and `main`.
  - Edges include lazy imports, relative imports, star imports, parent `__init__` execution, and string module paths in modules that call `import_module`.
  - Result: 71.3% of RPG lines reachable, which is an upper bound.
  - Eager import at boot is about 943 modules / 242K lines.
  - Without the string edges only 37% of lines are reachable, so the 40 parts and 19 hooks pull in about a third of the code.

### 11.5 Providers, realtime voice and model services — 4/10

- **PR1 — Live voice is built from runtime patches in the gateway (High).** See X1 and X3. `assistant_context/__init__.py:23-41` (a domain package) imports gateway routes.
- **PR2 — Live calls run in one process and TTS is serialized (High).**
  - Flow:
    1. The browser streams microphone audio straight to STT on `ws://host:5201`.
    2. The final transcript goes to the chat SSE route, pinned to the worker.
    3. Speculative LLM calls run on stable partial transcripts.
    4. PCM frames return over `/api/tts/live-call/websocket`.
  - Per call: an unbounded request queue, one producer thread per phrase, and one bridge thread per SSE turn.
  - See SCALE1.
- **PR3 — Model services block, buffer and have no auth (High).** See SEC5 and PERF7. Also:
  - The voice-clone client sends multipart form data to a JSON endpoint (`tts_http_client.py:296-301` vs `tts_server.py:591-592`).
  - `/v1/realtime` is a production-mounted stub, and its TTS adapter posts to a nonexistent `/tts`, silently falling back to synthetic audio.
- **PR4 — Provider selection and caching (High).**
  - See X4 and PERF4.
  - Registration is glob auto-discovery that imports every module and prints, then swallows, errors.
  - `faster-qwen3-tts` is registered by two classes; which one wins depends on unsorted file order.
  - 43 provider-name conditionals in 27 files.
  - 49 `get_provider(` call sites.
- **PR5 — The llama.cpp provider manages processes unsafely (Medium).** It kills whatever owns the port with `kill -9`, spawns `--host 0.0.0.0` without draining stdout, and does so on any call, ignoring `auto_start`.
- **PR6 — Prompts are scattered (Medium).**
  - 117 inline prompt strings across 71 files.
  - `app/prompts` is used only by `/api/prompts/render`.
  - Only 11 modules use structured contracts.
  - Prompt versions are ad hoc strings.

### 11.6 Chat, memory and characters

- **CM1 — Whole-workspace chat save can soft-delete or drop sessions (High).**
  - `chat_compat.load` pulls the 200 newest sessions with full transcripts.
  - `save_sessions` soft-deletes any active session not in that list.
  - It is still used by:
    - `set_session_interaction`;
    - the `append_user_message` save;
    - interrupted-reply saves;
    - proactive `append_assistant_message`;
    - about 30 other call sites.
  - The only guard is one lock per process.
  - Inferred race: a session created between the load and the save on another replica is soft-deleted, and sessions older than the newest 200 return 404 or lose writes.
  - Targeted single-session writes exist only as a gateway patch.
- **CM2 — Chat execution (Medium).**
  - Each generation runs on its own thread, polling `get_job` every 100 ms.
  - Cancelled non-Codex calls keep running.
  - The SSE route bypasses admission, idempotency, interruption and ownership (`core_chat_routes.py:185-242`).
  - The context budget is a fixed 65,536-token estimate, not the model's context size.
  - Every `get_session` deep-copies the transcript into the speculation cache.
- **CM3 — Two memory systems and a three-way cycle (Medium).**
  - v1 and v2 each have their own consolidation, policy and temporal modules. Authority is a durable epoch defaulting to v1 (migration 0079).
  - chat → memory has 15 imports; memory → chat 10; characters → memory 6.
  - Recommendation: shared conversation contracts and a transcript-reader port; prompt orchestration above all three; complete the v2 cutover and delete v1.

### 11.7 Web frontend — 4/10

- **FE1 — The browser runtime is unmanaged global patching (Critical; R8 not fixed).**
  - `viewRuntime` makes 47 initializer calls: 37 return a cleanup that is dropped, 10 return nothing. 9 more modules install themselves on import.
  - [router.tsx:82-85](../src/apps/web/src/app/router.tsx#L82-L85) starts the runtime in an effect with no cleanup.
  - There are 15 live fetch wrappers. One (`assistant-context-controller.ts:114-119,229-244`) rewrites chat POSTs to another endpoint and changes the body.
  - Importing `characterClient.ts` installs avatar and viseme bridges and the Live2D renderer.
  - Adding disposal naively is unsafe: the existing cleanups restore a fetch reference captured at install time, which would drop any wrapper installed later.
- **FE2 — React and imperative controllers write to the same DOM (High).**
  - `researchProgressController.ts:553-598` injects `<article>` nodes into React's transcript.
  - `ChatbotWorkspace` reads DOM selects, deletes injected rows and branches on window flags.
  - Storyteller panels scrape `innerText` and poll every 1–1.5 s.
  - There are 4 extra `createRoot` islands outside the main provider tree.
- **FE3 — The API contract is mostly handwritten (High; R12 not fixed).** See X5.
- **FE4 — No error boundaries (High).** No router `errorComponent`, no `error`/`unhandledrejection` handlers; runtime initialization failures only reach `console.error`. One render error or failed chunk load blanks the app.
- **FE5 — Oversized components (High).**
  - `ChatbotWorkspace`: one 2,039-line function with 29 `useState`, 25 `useRef` and 24 effects.
  - `TradingChartPanel`: 1,740 lines with 44 state hooks.
  - `AudiobookWorkspace`: 1,353 lines with 60 `useState`.
  - The whole app has only 21 custom hooks and 0 uses of `React.memo`.
- **FE6 — CSS works by overrides (High).**
  - 163 global stylesheets and 0 CSS modules.
  - 1,671 `!important`.
  - Themes are 686 attribute-selector overrides; `liquid-glass-theme.css` targets 221 feature class names.
  - 125 CSS custom properties against 6,675 hard-coded color literals.
  - [main.tsx:12-35](../src/apps/web/src/main.tsx#L12-L35) loads 24 stylesheets eagerly, with themes after features ✔.
  - Mantine's custom palette is never used.
- **FE7 — Feature boundaries (Medium).**
  - chatbot and assistant-workspace import each other (21 edges one way, 13 back).
  - `app` imports 41 assistant-workspace modules.
  - `shared` is 2 files; `settings` is the de facto shared kernel and imports `storyteller`.
  - No ESLint.
  - Adding a module touches 6–7 files, and a forgotten `ROUTE_MODULES` entry silently gets Chat's API allow-list.
- **FE8 — Event plumbing (Medium).**
  - 61 files dispatch window `CustomEvent`s.
  - There are 67 event names; 25 are declared in more than one place, and `'omnix:assistant-voice-perf'` in 29 files.
- **FE9 — Dead code and test gaps (Medium).**
  - 92 unreachable modules.
  - Tests by feature: storyteller 2, audiobook 1, podcast 1, live-speech 0, conversation-production 0.
  - `renderWithTheme` is defined 13 times.
  - 65 test files build their own `QueryClient`.

---

## 12. Status of the 2026-09-26 findings

| Item | Status | Notes |
|---|---|---|
| R1 production entrypoint | Partial | One production composition. The Docker default and the native launcher serve different `/events` implementations. |
| R2 async boundaries | Partial | Allow-list offload of 8 routes; 229 async handlers still never await |
| R3 chat recovery ownership | **Fixed** | Owner-aware, paginated, rechecks liveness |
| R4 submission vs execution | Partial | The durable worker runs feature jobs. Memory, compaction, SSE and live chat, and in-memory inline paths remain. |
| R5 scheduling and GPU | Partial | Monitor singleton fixed; GPU permits open |
| R6 collection pagination | Open for assets and jobs; fixed for chat | Asset cap of 500 remains |
| R7 explicit composition | Partial | Composition root exists; ~23 hooks and class patches remain in the production path |
| R8 browser lifecycle | Open | Counts unchanged (17 / 19 / 28) |
| R9 SSE fan-out | Open | Event-loop offload fixed; per-subscriber polling remains |
| R10 repository startup work | Open, broader than reported | 132 bootstrap call sites |
| R11 large facades | Open | |
| R12 generated contracts | Open | 36% of UI paths are typed |
| R13 stale deploy and test entrypoints | Partial | Dockerfile, compose and persistence compile step repaired; `pytest.ini`, `start_all.sh` and `run_tests.py` still stale |
| R14 media buffering | Partial | New asset ingestion streams; WAV/base64 paths remain |
| R15 measurement and deployment ceiling | Partial | Benchmarks exist; no correlation IDs, metrics or tracing |

---

## 13. Target architecture

**Keep a modular monolith. Do not split into microservices.** The problems are boundaries and wiring, not deployment units. Target properties:

1. **Layers, enforced in CI.**
   - `kernel`: runtime config, database, unit of work, tenant, auth, jobs engine, events, assets and blob store, provider port, settings registry, observability.
   - `features`: chat, live_voice, characters, memory, rpg, trading, agents, audiobook, image, voice, research, storyteller/podcast, hermes.
   - `composition root`: gateway app assembly, worker assembly.
   - The kernel imports no feature. Features import only the kernel and declared contracts.
2. **A `FeatureModule` contract.** Each feature declares:
   - id and config model;
   - routers (mounted by the root with a prefix plus auth and permission dependencies);
   - job handlers with resource classes;
   - background workers and scheduled tasks;
   - repositories registered with the unit of work;
   - outbox consumers;
   - settings entries;
   - capabilities;
   - a migration namespace;
   - web module metadata.

   Features are enabled from configuration.
3. **Explicit extension points instead of patches.**
   - Registries: job handlers, strategies, provider specs, capability executors, outbox consumers.
   - Ordered pipeline stages for the RPG turn and the live-voice turn.
   - Transport middleware.
4. **Execution plane.**
   - Stateless API replicas.
   - Singleton-free scheduling (a per-task advisory lock).
   - Job worker pools by resource class that can run on any host.
   - PostgreSQL-leased device permits.
   - Live voice with session-affine routing and a streaming TTS service with admission control.
5. **Data.**
   - Migrations as a release step, with expand/contract.
   - Retention.
   - An outbox relay plus `NOTIFY` fan-out.
   - A commit-safe event cursor.
   - Typed hot state and targeted writes.
   - The blob protocol, with an S3-compatible adapter.
   - Row-level security.
6. **Security.**
   - Authentication modes `local` (install token plus session cookie) and `oidc`.
   - Per-request principal and tenant; RBAC permissions on every route.
   - Approvals bound to a principal.
   - Run-scoped signed tokens.
   - Sandbox by default.
   - Service-to-service auth.
   - Secret scanning.
7. **Observability.**
   - Structured logs with correlation.
   - Prometheus metrics.
   - Optional OpenTelemetry tracing.
   - problem+json errors.
   - SLOs and runbooks.
8. **Frontend.**
   - A module manifest with `activate`/`dispose`.
   - One typed client with middleware.
   - React owns the DOM.
   - Error boundaries.
   - CSS layers, tokens and CSS modules.
   - ESLint boundaries.

---

## 14. Method, verification and limitations

**Method.**
- The reviewer read the core composition (`production.py`, `runtime_*`, `gateway/main.py`, `feature_registry.py`, `lifecycle.py`, `runtime_hooks.py`, `shared.py`, `platform/__init__.py`).
- The reviewer ran repository-wide AST scans: package import graph, route handler analysis, patch patterns, and git churn.
- Seven parallel read-only subsystem audits covered persistence and jobs, agent runtime, RPG, trading, web, providers and realtime, and security/ops/CI.

**Verification.** Findings marked ✔ were re-checked directly in the source by the reviewer:
- client-asserted approvals;
- trading import-time installers and the patched authorization gate;
- migrations in `bootstrap_local_tenant` and its RPG call counts;
- the compat job fence that always passes;
- `viewRuntime` dropping cleanups and the `listJobs` replacement;
- the provider cache that evicts instances in use;
- STT binding and CORS;
- `sitecustomize` patches;
- the unseeded RPG RNG;
- the committed key's presence and format;
- the platform import-time patch;
- chat store class patching;
- `async` handlers doing synchronous I/O.

Other findings come from the subsystem audits, which cite file and line evidence; some items are explicitly marked "inferred".

**Limitations.**
- This is a static review. No load tests, query plans, profiling, GPU runs or test executions were performed for it.
- Capacity statements such as "1–2 concurrent speaking calls per GPU" are inferences from code.
- Line numbers refer to `7bd17af08` and will drift.
- The docs' test-suite numbers are from 2026-09-26 and were not re-run.
