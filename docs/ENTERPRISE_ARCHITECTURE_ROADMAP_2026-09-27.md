# Omnix enterprise architecture roadmap: path to 9/10 in every area

- **Date:** 2026-09-27
- **Baseline revision:** `7bd17af08`
- **Findings source:** [ENTERPRISE_ARCHITECTURE_REVIEW_2026-09-27.md](ENTERPRISE_ARCHITECTURE_REVIEW_2026-09-27.md)

Finding IDs such as X1, SEC2, PERF1, PJ3, AR2, TR4, RPG1, PR4, CM1 and FE1 refer to that review.

**Audience:** an autonomous or semi-autonomous coding agent (LLM) that will carry out this plan in the Omnix repository, plus the humans who supervise it. The document is meant to be self-contained. Where a design decision matters, it has already been made here, so the implementer should not have to invent architecture. If reality contradicts this document, follow the escalation rules in §1.6.

---

## Contents

0. How to use this document
1. Rules of engagement (read before every work package)
2. Definition of 9/10 (target scorecard and exit metrics)
3. Program structure and dependency graph
4. Work packages
   - Phase 0 — Containment of critical security exposure
   - Phase 1 — Baseline, measurement and guardrails
   - Phase 2 — Kernel, composition and dependency direction
   - Phase 3 — Removal of runtime patching
   - Phase 4 — Identity, authorization, tenancy and agent safety
   - Phase 5 — Data and persistence
   - Phase 6 — Execution plane and horizontal scalability
   - Phase 7 — Performance
   - Phase 8 — Domain restructuring
   - Phase 9 — Frontend architecture
   - Phase 10 — Observability and operations
   - Phase 11 — Deployment and delivery
   - Phase 12 — Certification
5. Appendices
   - A. Runtime patch inventory and target owners
   - B. Package cycles and their resolutions
   - C. Permission catalog (starter)
   - D. Layer map for the architecture lint
   - E. Ratchet metrics: definitions, baselines, targets
   - F. Characterization-test recipe
   - G. Dead-code deletion protocol
   - H. ADRs to write
   - I. Validation command reference

---

## 0. How to use this document

1. Work packages (WPs) are the unit of work. Each WP has an ID (`WP-<phase>.<n>`), the findings it addresses, dependencies, a goal, fixed design decisions, steps, starting files, acceptance criteria, tests, validation commands, documentation updates, and human gates.
2. Execute WPs in dependency order (§3). WPs with no dependency on each other may run in parallel on separate branches.
3. One WP produces one or more pull requests.
   - Keep each PR focused and reviewable: aim for ≤ ~1,500 changed lines, excluding pure file moves and generated files.
   - When a WP lists "split into PRs", follow that split.
4. Line numbers in this document refer to `7bd17af08` and will drift. Locate code by symbol name and file, then confirm by reading it.
5. Keep two living files, created in WP-0.0:
   - `docs/roadmap/PROGRESS.md` — per-WP status, PR links, metric deltas, deviations, blocked items.
   - `docs/roadmap/DECISIONS.md` — any deviation from a design decision in this document, with rationale.
6. Where "the ratchet" is mentioned, it means the metrics and lint baselines created in WP-1.1 and WP-1.2. They may only improve. Every PR must leave them equal or better, and must lower the baseline when it removes violations.

---

## 1. Rules of engagement

### 1.1 Non-negotiable invariants

These come from AGENTS.md, ADR-0010 to ADR-0014 and [OMNIX_RUNTIME_INVARIANTS.md](architecture/OMNIX_RUNTIME_INVARIANTS.md). No WP may violate them.

1. **PostgreSQL is the only production authority for structured state.** Never add a fallback to files, SQLite or memory when the database is unavailable. Fail closed.
2. **Agent capability profiles are ceilings, not grants.**
   - Approval policy must never expand issued capabilities.
   - Coordinator, reviewer and subagent authority stays explicitly narrowed.
   - Evidence stays bound to subject, task revision and workspace state.
   - LLM output is evidence or a proposal; deterministic code owns authority and completion.
3. **Trading.**
   - AI or shadow analysis is research.
   - Do not add broker order placement.
   - Do not widen paper or live execution authority.
   - Do not make any AI output able to trigger an order.
   - Keep IBKR data-only.
4. **Durable leases and fencing stay.** Every job finalization validates owner and lease token. A stale attempt must never finalize.
5. **Migrations are forward-only.** Never edit an applied migration file; checksums are enforced. Add a new migration instead.
6. **Worker/API roles.** Singleton background work runs only under background ownership. API replicas never construct local CUDA TTS.
7. **RPG authority.** The simulation owns game truth. AI narrates or proposes; the UI never invents committed state.
8. **Browser contracts.** When backend request or response schemas change, regenerate `src/apps/web/src/api/generated/openapi.json` and `types.ts` in the same PR (`npm --prefix src/apps/web run api:generate`).

### 1.2 Working method for every WP

Follow AGENTS.md §"Engineering workflow":

1. **Read before editing.** Read the WP, the referenced findings in the review, the relevant ADRs, and the current code: modules, callers, tests, registrations, schemas, migrations and generated contracts.
2. **Identify the owning layer** and preserve its invariants.
3. **Characterize first.** If the WP changes code that sits behind a runtime patch or wrapper chain, write characterization tests first (Appendix F) and commit them before refactoring.
4. **Make the smallest coherent change.**
   - Prefer updating all importers in the same PR over leaving a compatibility shim.
   - If a shim is unavoidable, register it in `docs/architecture/compatibility-inventory.json` with a deletion WP.
5. **Add or update focused regression tests** for changed behaviour.
6. **Review your own diff.** Inspect the complete diff and search for impacted call sites.
7. **Run validation after the final change** (Appendix I). Earlier passing runs are stale once code changes.
8. **Update documentation** (ARCHITECTURE.md, invariants, ADRs, operations docs) when a contract changes. After editing a Markdown source that has an HTML counterpart, run `python docs/render_docs.py`.
9. **Update the ratchet baselines downward** when you remove violations. Record metric deltas in PROGRESS.md.

### 1.3 Shell and environment constraints (from AGENTS.md)

- Avoid shell composition (`;`, `&&`, pipes, redirection, command substitution). Issue commands separately.
- Run commands from the repository root. Prefer package-prefix options (`npm --prefix src/apps/web …`) over `cd`.
- Python code runs with `PYTHONPATH=src`.
- **PostgreSQL integration tests must use a disposable database** named `omnix_test` or `omnix_refactor_baseline`, via `OMNIX_TEST_DATABASE_URL`. Never point tests at an operator database. See [ARCHITECTURE_GATES.md](testing/ARCHITECTURE_GATES.md).
- Windows is a primary operator platform. Keep `.bat` launchers working, and test path handling with both separators.

### 1.4 Testing rules

- Never delete, skip or weaken a test just to get green. Every removal or quarantine needs a written reason recorded in the quarantine file (WP-1.4) or in PROGRESS.md.
- A test for a retired contract may be deleted only when:
  - the behaviour is intentionally gone, or
  - an equivalent test on the current contract exists; cite it.
- New tests must be deterministic: no fixed sleeps, no wall-clock dependence, no network. Use fakes for providers.
- Performance WPs must record before/after measurements with the existing harnesses (Appendix I) and store the JSON under `docs/measurements/` with the date in the file name.

### 1.5 Human-gated actions

**Stop and ask a human** before doing any of these. Record the request in PROGRESS.md under "Blocked".

1. Rotating or revoking any real credential, including the committed Cerebras key.
2. Rewriting git history, force-pushing, or purging blobs.
3. Deleting real user data: voice-clone recordings, trading logs or records, chat or RPG data in any real database.
4. Running migrations or data backfills against any non-disposable database.
5. Flipping the memory v2 authority epoch in a real deployment.
6. Changing a trading strategy's default from enabled to disabled, or deleting a strategy version.
7. Changing the default authentication mode for existing installations, or any change that locks out an existing operator.
8. Enabling network exposure beyond loopback in defaults.
9. Adding a new third-party service dependency (SaaS) or a license-incompatible package.
10. Anything that would submit real broker orders. This is always forbidden in this roadmap.

### 1.6 Escalation

Stop the WP and write a "Blocked" entry in PROGRESS.md (what, why, options, recommendation) when:

- a fixed design decision here is infeasible or clearly wrong for the current code;
- a step would violate §1.1;
- a characterization test reveals behaviour that looks like a bug you would have to preserve. Record the question: preserve or fix?
- a dependency WP is incomplete.

Minor adaptations do not need to stop the WP; log them in DECISIONS.md. Examples: different file names, splitting a module differently while meeting the acceptance criteria.

### 1.7 New dependencies approved by this roadmap

Adding these is explicitly in scope when their WP says so. Pin them in the lock files (WP-1.3):

| Kind | Packages |
|---|---|
| Python, development | `mypy`, `pip-tools`, `pytest-xdist` |
| Python, runtime | `httpx`, `PyJWT[crypto]`, `prometheus-client` |
| Python, optional extras | OpenTelemetry (`opentelemetry-sdk`, `opentelemetry-instrumentation-fastapi`, `opentelemetry-instrumentation-psycopg`, `opentelemetry-instrumentation-httpx`, `opentelemetry-exporter-otlp`); `boto3` (for the S3 blob adapter); `keyring` |
| Web | `eslint`, `typescript-eslint`, `eslint-plugin-react-hooks`, `openapi-fetch`, `@tanstack/react-virtual` |
| Tooling (CI only) | `gitleaks`, `pip-audit`, `trivy` |

Any other new dependency: log it in DECISIONS.md with a justification, and prefer the standard library or existing dependencies.

---

## 2. Definition of 9/10

### 2.1 Area targets

A score of 9 requires every exit metric in its row to hold. Measure with `scripts/architecture_metrics.py` (WP-1.1) and the tests named in the WPs.

| Area | Baseline | 9/10 means | Exit metrics (all required) |
|---|---:|---|---|
| **Platform primitives** | 7 | Every durable mutation is fenced; lifecycle is complete | All job mutators fenced by (worker, lease token) inside the same statement. Retention executes every policy. Outbox has a consumer (or no write) for every event type. Event cursor is commit-safe. Migrations run only as a release step. Row-level security on all tenant tables. |
| **Modularity and extensibility** | 3 | Features are self-contained modules registered through one contract; adding or removing one is configuration | Every feature ships a `FeatureModule`. The kernel lists no feature by name except the catalog. Each optional feature can be disabled and the app boots with its tests passing (matrix test). A job type, strategy, provider or capability can be added by editing only its feature package plus one registration line (documented recipe plus test). No non-generated file over 1,200 lines; ≤ 20 functions over 150 lines, each documented. |
| **Dependency direction and composition** | 3 | Layers are enforced and there is no hidden composition | 0 package cycles. Architecture lint passes with an empty baseline. 0 foreign-attribute assignments (runtime patches). 0 `install_*hook` functions. 0 `FastAPI.__init__` patchers. No `sitecustomize.py`/`usercustomize.py`. `shared.py` deleted. |
| **Performance** | 4 | The event loop is never blocked; hot paths are bounded and measured | 0 async handlers doing synchronous I/O. Event-loop lag p99 < 20 ms under the mixed benchmark. Chat admission p95 < 50 ms. RPG turn overhead excluding LLM p95 < 150 ms with a 1 MB state. Idle SSE database reads independent of subscriber count. Pooled HTTP clients everywhere. No per-token persistence. Every list endpoint paginated, p95 < 100 ms at 100k rows. |
| **Horizontal scalability** | 3 | Stateless APIs, workers that scale out, capacity coordinated across processes | Multi-host test (containers): 2 API replicas + 2 job workers + 1 scheduler + S3-compatible blob store all pass. GPU permits enforced across processes. Rolling-upgrade test N → N+1 with zero failed requests. Live-voice capacity scales with TTS service capacity. No unapproved process-local state. |
| **Data architecture** | 4 | Bounded growth; typed hot data; safe schema evolution | Retention keeps tables bounded (test). Outbox lag metric exposed. Queried/updated JSON fields promoted to typed columns. Optimistic concurrency on document tables. Migration lint in CI. 0 unbounded `fetchall()` in repositories. Restore rehearsal passes. |
| **Security (multi-user)** | 2 | Authenticated, authorized, isolated, auditable | 100% of routes authenticated except a declared public list (test). A permission on every route (test). RLS on all tenant tables (test). CSRF, Origin and Host enforced. Approvals bound to a principal. Agent sandbox by default with egress control. Service-to-service auth. No plaintext secrets; secret scanning in CI. ASVS L2 checklist ≥ 90% passing with the rest documented. Threat model maintained. |
| **Observability and operations** | 3 | Every request and job is traceable and measurable | JSON logs with request, job, run and workspace ids. 0 `print()` in `src/app`. `/metrics` with a documented catalog. Optional OpenTelemetry tracing. SLOs, alerts and runbooks exist. All environment reads go through the config package. |
| **Delivery** | 4 | Everything is tested on every change; builds are reproducible | Full Python suite green on every PR (parallel) with an empty quarantine. mypy clean on the kernel and at agreed strictness elsewhere. Ruff rule set repo-wide. Locked dependencies. One Python version. Reproducible, non-root, multi-stage images. CI < 30 min. Web lint, test, build and e2e shell in CI. |
| **Frontend** | 4 | Modules have a lifecycle; contracts are typed; the UI is resilient | Navigating Chat → Trading → Chat leaves listener, timer and observer counts stable (test). 0 `window.fetch` assignments. 100% of API calls through the typed client. 0 handwritten types for schema routes. Error boundaries per route. `!important` ≤ 50. ESLint 0 errors / 0 warnings. Tests for every feature. Long lists virtualized. |

### 2.2 Subsystem targets

Each subsystem reaches 9 when the WPs listed here are complete and their acceptance criteria hold.

| Subsystem | Required WPs |
|---|---|
| Persistence, jobs, events, assets | 0.5, 2.4, 2.5, 2.6, 5.1–5.11, 6.1, 6.2 |
| Agent runtime and tools | 0.4, 3.6, 4.5, 4.6, 4.7, 6.5, 7.4, 8.2 |
| Trading | 3.4, 6.3, 7.5, 8.3 |
| RPG | 2.7, 3.3 (a–e), 5.6, 7.1, 8.6 |
| Providers, realtime, model services | 0.2, 0.5, 3.2, 6.2, 6.4, 7.2, 7.3, 8.4 |
| Chat, memory, characters | 3.1, 2.9, 5.7, 8.5 |
| Web frontend | 1.7, 9.1–9.10 |

---

## 3. Program structure and dependency graph

```text
Phase 0  Containment ─────────────────────────────────────────────┐
  WP-0.0 progress files                                           │
  WP-0.1 secrets    WP-0.2 loopback    WP-0.3 request guard       │
  WP-0.4 server-side approvals (interim)   WP-0.5 internal APIs   │
                                                                  ▼
Phase 1  Baseline & guardrails (must finish before Phases 2–3 refactors)
  WP-1.1 metrics ratchet ─► WP-1.2 architecture lint
  WP-1.3 toolchain/locks ─► WP-1.4 test triage ─► WP-1.5 CI ─► WP-1.6 mypy
  WP-1.7 ESLint (web)
        │
        ├──────────────► Phase 4 (auth can start after 1.5; uses middleware, not 2.2)
        ├──────────────► Phase 9 (frontend can start after 1.7)
        ├──────────────► Phase 10.1/10.2 (logging, request id can start after 1.5)
        ├──────────────► Phase 11 (images/compose can start after 1.3)
        ├──────────────► WP-7.1 (event-loop correctness can start after 1.2)
        ▼
Phase 2  Kernel & composition
  WP-2.1 runtime pkg ─► WP-2.2 FeatureModule (per-feature PRs)
  WP-2.3 config/settings    WP-2.4 migrations off request path
  WP-2.2 ─► WP-2.5 jobs inversion ─► WP-2.6 persistence inversion
  WP-2.2 ─► WP-2.7 platform cleanup
  WP-2.3 + WP-7.2(part A) ─► WP-2.8 shared.py removal
  all above ─► WP-2.9 cycles to zero
        ▼
Phase 3  Remove runtime patching (each after WP-3.0 characterization)
  3.1 chat store (after 2.6 chat part) ─► 3.2 live voice package
  3.3a RPG determinism ─► 3.3b ─► 3.3c ─► 3.3d ─► 3.3e ─► 3.7 sitecustomize
  3.4 trading overlays   3.5 composition patches (after 2.5)   3.6 agent seams
  3.8 legacy patcher deletion (last)
        ▼
Phase 5  Data (after 2.4, 2.6)     Phase 6  Execution (after 2.5, 5.1)
Phase 7  Performance (7.1 early; others after owners are refactored)
Phase 8  Domains (after respective Phase 3 items)
        ▼
Phase 12 Certification (after everything)
```

**Recommended order for a single implementer:**

0.0 → 0.1–0.5 → 1.1 → 1.2 → 1.3 → 1.4 → 1.5 → 1.6 → 1.7 → 7.1 → 2.1 → 2.3 → 2.4 → 2.2 (audiobook pilot, then remaining features) → 4.1–4.4 → 2.5 → 2.6 → 2.7 → 3.0 → 3.1 → 3.2 → 3.3a–e → 3.4 → 3.5 → 3.6 → 3.7 → 2.8 → 2.9 → 3.8 → 4.5–4.11 → 5.x → 6.x → 7.2–7.8 → 8.x → 9.x (can interleave) → 10.x → 11.x → 12.1.

---

## 4. Work packages

### Phase 0 — Containment of critical security exposure

#### WP-0.0 — Progress and decision logs

- **Goal:** create the living tracking files.
- **Steps:**
  1. Create `docs/roadmap/PROGRESS.md` with:
     - a table with columns: WP, status (not started / in progress / done / blocked), PRs, date, metric deltas, notes;
     - a "Blocked" section;
     - a "Human actions requested" section.
  2. Create `docs/roadmap/DECISIONS.md` for deviations.
- **Acceptance:** both files exist and are linked from this roadmap's header note in PROGRESS.md.

#### WP-0.1 — Secret containment (repository side)

- **Addresses:** SEC4.
- **Depends on:** WP-0.0.
- **Goal:** remove the committed credential-format value from the working tree, prevent recurrence, and request rotation and purge.
- **Steps:**
  1. Confirm that `src/app/data/settings.json` is not read at runtime. Search for `app/data`, `data/settings.json` and `DATA_DIR`; the runtime reads `resources/data/settings.json` per `shared.py:20`.
  2. If it is unused, delete it with `git rm` and add `src/app/data/*.json` to `.gitignore`. If it is used, replace the key value with an empty string and log in DECISIONS.md why the file remains.
  3. Add `.gitleaks.toml` with default rules plus custom rules for the `csk-` (Cerebras), `sk-` (OpenAI-style), `sk-or-` (OpenRouter), `hf_` (Hugging Face), GitHub token and Google OAuth client-secret patterns.
  4. Add `.pre-commit-config.yaml` with the gitleaks hook.
  5. Add a gitleaks CI job (it becomes part of `ci.yml` in WP-1.5; for now add `.github/workflows/secret-scan.yml` on `pull_request` and `push`).
  6. Scan the current tree. For every hit, either remove it or add a justified allow-list entry.
- **Human gates:** rotate the Cerebras credential; purge history (`git filter-repo`) and force-push. Write both requests in PROGRESS.md "Human actions requested", with exact file and commit references (commit `637220e19` is the earliest known).
- **Acceptance:** gitleaks passes on the working tree; CI runs it on PRs.

#### WP-0.2 — Loopback by default for every listener

- **Addresses:** SEC3, PR3, PR5.
- **Depends on:** WP-0.0.
- **Goal:** no Omnix-started listener binds to all interfaces unless the operator opts in explicitly.
- **Design:**
  - A single setting, `OMNIX_BIND_HOST` (default `127.0.0.1`), read through a small helper `app/runtime/net.py: bind_host() -> str`. That module is created here and moves into the config package in WP-2.3.
  - LAN exposure requires `OMNIX_BIND_HOST=0.0.0.0` **and** `OMNIX_ALLOW_LAN=true`. Log a startup warning when both are set.
  - CORS: never combine `allow_origins=["*"]` with `allow_credentials=True`. Allowed origins come from `OMNIX_ALLOWED_ORIGINS` (default: `http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173,http://127.0.0.1:4173`).
- **Files to change:**
  - `src/apps/web/package.json`: `dev` and `preview` use `--host 127.0.0.1`; add `dev:lan` and `preview:lan` scripts that keep `0.0.0.0`.
  - `src/apps/web/vite.config.ts`: if `server.host` or `preview.host` is set, align it.
  - `src/nemotron_eou_stt_server.py` (bind at line ~192, CORS at 29-35), `src/parakeet_stt_server.py`, `src/tts_server.py`, `src/openai_api.py` (also move its default port off 8001, which API replicas use; pick 8101 and update docs), `src/app/image_service_app.py`.
  - `src/app/providers/llamacpp_provider.py`: spawn `--host 127.0.0.1`.
  - `src/app/launcher/service_manager.py`, `start_all.bat`, `start_all.sh`, `src/launch.py`: pass or honor the bind host.
  - Documentation: `docs/SETUP.md`, `docs/OPERATIONS.md`, `README.md` port table.
- **Tests:**
  - A unit test for `bind_host()` covering defaults and the opt-in behaviour.
  - A static test that scans `src/**/*.py` and `package.json` for `0.0.0.0` literals outside `bind_host()` and the `*:lan` scripts, and fails on any.
- **Acceptance:** the static test passes; services start on loopback; the Windows launcher still starts the cohort. Manually verify, or with an existing launcher test if present.

#### WP-0.3 — Request guard: Host allow-list, Origin checks, CSRF header

- **Addresses:** SEC3.
- **Depends on:** WP-0.2.
- **Goal:** block DNS rebinding, cross-site drive-by requests and cross-origin WebSocket use against the gateway, the launcher control app and model services.
- **Design:** an ASGI middleware at `src/app/security/request_guard.py`. The `app/security` package is created here.
  1. **Host allow-list.** Reject any request whose `Host` header is not in `OMNIX_ALLOWED_HOSTS` with 421 Misdirected Request. Default: `localhost`, `127.0.0.1`, `[::1]`, each with and without port. The list is extended by configured public hostnames.
  2. **State-changing HTTP** (POST, PUT, PATCH, DELETE):
     - if `Origin` is present, it must be in `OMNIX_ALLOWED_ORIGINS`, otherwise 403;
     - in all cases the header `X-Omnix-Client` must be present (any non-empty value), otherwise 403 with body `{"detail":"missing_client_header"}`. Browsers cannot send custom headers cross-origin without a CORS preflight, and the CORS policy won't allow it.
  3. **WebSocket upgrade.** If `Origin` is present it must be allowed; non-browser clients without `Origin` are allowed until WP-4.1 adds auth.
  4. **Exempt paths:** `GET` and `HEAD` requests, `/health`, `/ready`.
  5. The CORS middleware allows the header `X-Omnix-Client`.
- **Web client:** in `src/apps/web/src/app/viewApiScope.ts` (the firewall already wraps `fetch`), add `X-Omnix-Client: web` to every same-origin request to `/api`, `/events`, `/ready` and `/health` that has a state-changing method. Do not create a second fetch wrapper. EventSource (GET) and WebSocket need no header.
- **Other ASGI apps:**
  - Apply the same middleware to `src/app/launcher/control_app.py` and to the model services (`tts_server.py`, the STT servers, `image_service_app.py`).
  - Their gateway-side clients (`src/app/tts_http_client.py`, `src/app/image_http_client.py`, `src/app/providers/qwen_http_gateway.py`, STT clients) send `X-Omnix-Client: gateway`.
- **Tests:** in `src/tests/security/test_request_guard.py`, each of the following must be rejected, while allowed-origin and header-bearing requests pass:
  - wrong Host → 421;
  - cross-site POST without the header → 403;
  - POST with a disallowed Origin → 403;
  - WebSocket with a disallowed Origin → rejected.

  Add a web unit test that the firewall adds the header.
- **Acceptance:** tests pass. The existing web e2e and Vitest suites pass. The generated OpenAPI is unchanged; this is middleware only.

#### WP-0.4 — Server-side approvals (interim, before principals exist)

- **Addresses:** SEC2, AR2 (partial).
- **Depends on:** WP-0.3.
- **Goal:** no single client request can both propose and self-approve a state-changing tool or agent action, and approval policy can no longer be loosened by request fields.
- **Design:**
  - **New migration** `NNNN_capability_approvals.sql` (next free number; see WP-2.4 ordering rules) with table `omnix_capability_approvals`:
    - columns: `id` (text pk), `workspace_id`, `subject_type` (`tool_proposal` | `agent_request`), `subject_id`, `capability_id`, `proposal_digest` (sha256 hex of the canonical JSON of capability id + action + input + session), `requested_by`, `decision` (`pending` | `approved` | `denied` | `expired` | `consumed`), `decided_by`, `reason`, `created_at`, `decided_at`, `expires_at`, `consumed_at`;
    - composite foreign key to workspaces, as in migration 0012.
  - **Tool flow.** Replace the single execute call with three:
    1. `POST /api/assistant/tools/proposals` runs the existing review (`assistant_tools/gate.py`), persists the proposal and returns `proposal_id`, `approval_required` and `expires_at`.
    2. `POST /api/assistant/tools/proposals/{id}/approve` or `/deny`.
    3. `POST /api/assistant/tools/proposals/{id}/execute`, which verifies: the proposal exists and has not expired; the digest matches the stored input; if approval is required, `decision == approved`; the proposal has not been consumed. It then marks the proposal consumed in the same transaction as the execution ledger write.
  - **Remove from public request models** (`assistant_tools/models.py`): `approved` and `approval_policy` on the envelope. Approval policy is resolved only from server configuration (`gate.py` line ~48 must no longer read `request.approval_policy`). Keep the old `/api/hermes/assistant/tools/execute` route only as an internal route for the Hermes sidecar, protected by the service token from WP-0.5, and route it through the same proposal/approval check.
  - **Agent runs** (`agent_runtime/api.py`, `contracts.py`):
    - A client-supplied `approval_policy` may only tighten the profile default. Reject any looser value with 422.
    - `allowed_paths` must be a subset of the profile ceiling.
    - `workspace_root` must be under an allow-listed root (`OMNIX_AGENT_WORKSPACE_ROOTS`, default: the repository root and `resources/agent_workspaces`).
    - The isolation level may only be raised, not lowered.
  - **Approval ids:** generate them randomly (`secrets.token_urlsafe(24)`). Do not derive them deterministically, and never include them in agent-visible tool results. Adjust `broker_api.py` (~575-583) and `pi_guard_extension.ts` (~544).
  - **Web:** update `src/apps/web/src/features/chatbot/assistantToolConfigClient.ts` (currently sends `approved: true`) and the approval UI to call propose → approve → execute. Delete the `approved: true` literal.
- **Tests:**
  - execute without approval fails when approval is required;
  - execute with a changed input (digest mismatch) fails;
  - double execute fails;
  - expired approval fails;
  - `approval_policy` in the body is rejected (422) or ignored — assert which, and prefer 422;
  - an agent run with a looser policy is rejected;
  - approval ids are unpredictable.
- **Acceptance:** tests pass; `grep -rn "approved: true" src/apps/web/src` returns nothing; OpenAPI and generated types updated.

#### WP-0.5 — Internal endpoints, service tokens, and a real fence on job completion

- **Addresses:** SEC5, PJ3 (partial).
- **Depends on:** WP-0.3.
- **Goal:** the worker protocol and model services require a service credential, and job completion or failure requires the caller's lease token.
- **Design:**
  - **Service token.**
    - `OMNIX_SERVICE_TOKEN`: at least 32 random bytes, URL-safe.
    - In local mode, if it is unset, the launcher generates one at first start and stores it with the provider secret store (DPAPI on Windows; a 0600 file under `resources/data/secure/` on POSIX, until WP-4.9). It then passes it to child processes through the environment.
    - Compare with `hmac.compare_digest`. Header: `X-Omnix-Service-Token`.
  - **Internal router.**
    - Move `/api/jobs/claim`, `/api/jobs/{id}/complete` and `/api/jobs/{id}/fail` from `gateway/core_jobs_routes.py` to an internal router under `/internal/jobs/...` that requires the service token.
    - Keep the old paths returning 410 Gone for one release, with a log line.
    - Search for callers first (`grep -rn "/api/jobs/claim"` across `src`, `scripts` and the web). Update every caller.
  - **Fence.**
    - Add `worker_id: str` and `lease_token: str` to `CompleteJobRequest` and `FailJobRequest` in `jobs/models.py`. They are required when the job has an active lease.
    - `persistence/job_compat.py` `complete_job`/`fail_job` must use the **request's** worker id and token, not the ones read from the row (currently lines ~219-299).
    - The `_runs_without_worker_lease` branch stays only for job types that are genuinely unleased (inline chat owned by a gateway identity, which has its own owner check).
  - **Model services:**
    - Require the service token on every non-health route.
    - The gateway clients send it.
    - Error bodies become `{"error": "<code>", "request_id": "<id>"}` with no traceback (e.g. `tts_server.py:583`).
    - Add upload size limits: `OMNIX_MAX_UPLOAD_BYTES`, default 50 MiB, enforced while streaming.
- **Tests:**
  - completing with a wrong token raises `JobClaimConflict` (HTTP 409);
  - completing after another worker claimed fails;
  - internal routes without the token → 401;
  - model service without the token → 401;
  - no traceback text in any error response (assert "Traceback" is absent).
- **Acceptance:** tests pass; the existing durable worker and audiobook worker tests pass; architecture gates `unit` and `postgresql` pass.

---

### Phase 1 — Baseline, measurement and guardrails

#### WP-1.1 — Architecture metrics and ratchet

- **Addresses:** X7 (the guardrail premise); used by every WP.
- **Depends on:** WP-0.0.
- **Goal:** a single command computes every tracked metric, compares it with a committed baseline, and fails if anything got worse.
- **Design:**
  - `scripts/architecture_metrics.py`, standard library only (AST and regex).
    - Output: JSON to stdout or `--output`.
    - `--check` compares with `resources/architecture/metrics-baseline.json` and fails if any metric is worse than its baseline in its direction.
    - `--update-baseline` rewrites the baseline, but only when every metric is equal or better. It refuses otherwise.
  - Metric definitions are in Appendix E. Each metric has `value`, `direction` (`lower` or `higher`) and `target`.
  - Scope: tracked files only (`git ls-files`). Exclude `src/apps/web/src/api/generated/**`, vendor directories and `node_modules`.
- **Steps:**
  1. Implement every metric in Appendix E, including the web metrics (TypeScript/CSS via regex).
  2. Generate the initial baseline at the current HEAD and commit it.
  3. Add a `metrics` job to CI: `secret-scan.yml` for now, `ci.yml` in WP-1.5.
  4. Add `src/tests/scripts/test_architecture_metrics.py` with fixtures for each metric detector (small synthetic files).
- **Acceptance:** `python scripts/architecture_metrics.py --check` passes at HEAD; detector unit tests pass; the baseline is committed.

#### WP-1.2 — Architecture lint (boundaries and runtime-patch ban) with a shrinking baseline

- **Addresses:** X1, X2 (enforcement).
- **Depends on:** WP-1.1.
- **Goal:** stop new violations immediately, while existing ones are burned down.
- **Design:**
  - `scripts/architecture_lint.py`, standard library only.
    - Configuration: `resources/architecture/layers.toml` (Appendix D).
    - Baseline: `resources/architecture/lint-baseline.json`.
    - Baseline entries are keyed by `(rule, path, fingerprint)`, where the fingerprint is a stable string such as the qualified target name or the imported module, never a line number.
    - The check fails on new violations **and** on stale baseline entries, so the baseline must shrink when violations are fixed.
  - Rules:

    | Rule | Meaning |
    |---|---|
    | AL001 | Layer violation: an import not allowed by `layers.toml`, including lazy imports inside functions. |
    | AL002 | Top-level package import cycle (module-level imports). |
    | AL003 | Foreign attribute assignment: `X.attr = …`, `setattr(X, …)` or `del X.attr` where `X` is an imported module, an imported class, `builtins`, `sys.modules[...]`, `FastAPI`, `APIRouter`, `StreamingResponse`, or any class not defined in the current module. Also flags `sys.meta_path.insert/append`, assignment to `sys.modules[...]`, and assignment to `window.fetch` (web handled by ESLint). |
    | AL004 | A function named `install_*`/`_install_*`/`patch_*` whose body contains AL003. |
    | AL005 | `async def` route handler (decorated `@<x>.get/post/put/patch/delete/api_route`) containing no `await`/`async for`/`async with`. |
    | AL006 | SQL string touching platform tables (`omnix_jobs`, `omnix_job_events`, `omnix_job_attempts`, `omnix_outbox`, `omnix_audit_events`, `omnix_workspaces`, `omnix_users`, `omnix_workspace_memberships`) outside the owning kernel repository modules listed in `layers.toml`. |
    | AL007 | `os.environ`/`os.getenv` outside `app/config/**` and `app/runtime/net.py` (until WP-2.3 moves it). |
    | AL008 | `print(` in `src/app/**`. |
    | AL009 | Silent broad except: `except Exception`/bare `except` whose body is only `pass`, `continue`, `return`, `return None` or `...` with no logging call. |
    | AL010 | `from x import *` in `src/app/**`. |
    | AL011 | `LocalBlobStore(` construction outside the kernel storage module. |
    | AL012 | `local_tenant_context(` or `bootstrap_local_tenant(` outside `app/security/**`, `app/persistence/identity_service.py`, the composition root, CLI modules and tests. |
    | AL013 | Nondeterminism in the RPG core: `random.<fn>(` module-level calls, `random.Random()` without a seed argument, `time.time(`, `datetime.now(`, `datetime.utcnow(`, `uuid.uuid4(` inside the RPG core packages listed in `layers.toml` (`rpg_core`). |
    | AL014 | Migration files: new duplicate numeric prefix; a new file sorting before the highest file on the base branch; edit of an existing migration (compare against `git show origin/main:<path>` when available, otherwise against the checksum registry). |

- **Steps:**
  1. Implement the rules with unit tests on synthetic modules in `src/tests/scripts/test_architecture_lint.py`.
  2. Generate the baseline at HEAD and commit it.
  3. Wire `python scripts/architecture_lint.py --check` into CI.
  4. Add to `docs/testing/ARCHITECTURE_GATES.md` a "No runtime patching policy" section, and update [OMNIX_RUNTIME_INVARIANTS.md](architecture/OMNIX_RUNTIME_INVARIANTS.md) to reference the lint.
  5. Write ADR-0015, "No runtime patching; explicit extension points" (Appendix H).
- **Acceptance:** lint passes at HEAD with the baseline; a synthetic new violation fails CI (unit test); ADR-0015 accepted.

#### WP-1.3 — Python toolchain, packaging and locked dependencies

- **Addresses:** DEL3, DEL1 (version skew).
- **Depends on:** WP-0.0.
- **Goal:** one supported Python version, per-runtime hashed locks, and tool configuration in `pyproject.toml`.
- **Design:**
  - **Supported Python: 3.11** for every runtime (gateway, workers, model services, CI, Docker, setup scripts).
  - `pyproject.toml` at the repository root:
    - `[project]` with `name = "omnix"` and `requires-python = ">=3.11,<3.12"`. Dependencies are listed by the `requirements/*.in` files, not here.
    - `[tool.ruff]` (migrate from `ruff.toml`, then delete `ruff.toml`): `target-version = "py311"`, `select = ["F", "E9", "W6", "B006", "B008", "B017", "PLE", "UP006", "UP007"]`, per-file ignores carried over.
    - `[tool.mypy]` (WP-1.6).
    - `[tool.pytest.ini_options]` (WP-1.4 moves configuration here from `src/tests/pytest.ini`).
  - **Per-runtime lock sets** in a new top-level `requirements/` directory:
    - `gateway.in`: fastapi, uvicorn[standard], pydantic, psycopg[binary], psycopg-pool, httpx, requests (until WP-7.2 removes it), python-multipart, websockets, numpy, soundfile, pydub, PyPDF2, python-docx, pandas (if still needed — verify imports), python-kasa, huggingface_hub (only if the gateway downloads models — verify), PyJWT[crypto], prometheus-client.
    - `worker.in`: `-r gateway.in` plus job-execution-only dependencies.
    - `tts.in`: torch, transformers, onnxruntime, sox, librosa, deepfilternet and the faster-qwen3-tts requirements. Reconcile with `src/requirements-rpg-tts.txt`.
    - `stt.in`: nemo_toolkit[asr] and its pins.
    - `image.in`: diffusers, transformers, safetensors, torch. Reconcile with `scripts/requirements/requirements-rpg-*.txt`.
    - `dev.in`: pytest, pytest-cov, pytest-xdist, playwright, pytest-playwright, mypy, ruff, pip-tools, pip-audit.
    - Compile each with `pip-compile --generate-hashes --output-file requirements/<name>.lock.txt requirements/<name>.in`. GPU sets use the PyTorch index (`--extra-index-url https://download.pytorch.org/whl/cu124`) and pin torch to a single version per set: resolve the 2.5.1 vs 2.6.0 conflict by choosing **one** version per runtime and documenting it.
  - Replace the root `requirements.txt` content with `-r requirements/gateway.lock.txt` plus a comment. Update the Dockerfile, `setup.sh`, `setup.bat` and CI to install from locks. `setup.*` must install psycopg (currently missing).
  - Remove the standard-library `enum` patch in `trading/__init__.py` (lines ~7-14). With Python 3.11, `StrEnum` exists, so import it directly where it is used.
- **Tests:** a CI step `pip install --require-hashes -r requirements/gateway.lock.txt` in a clean venv, then `python -c "import app.production"` with `PYTHONPATH=src`.
- **Acceptance:** all lock files compile; CI uses them; Python 3.11 is everywhere (grep workflows, Dockerfile and setup scripts for other versions: none remain); ruff runs repo-wide with the selected rules. F821 (undefined name) must be 0 — fix the real bugs, e.g. `rpg/ai/npc_initiative.py:416`. Record other rule counts in the metrics.

#### WP-1.4 — Test estate triage: collect everything, fix or quarantine, drive to zero

- **Addresses:** DEL2.
- **Depends on:** WP-1.3.
- **Goal:** the full Python suite is collected by default and runs green, with an explicit, shrinking quarantine.
- **Design:**
  - **Configuration** moves to `pyproject.toml` `[tool.pytest.ini_options]`:
    - `testpaths = ["src/tests"]`, `pythonpath = ["src"]`, `addopts = "-q --tb=short --strict-markers --import-mode=importlib"`;
    - markers: `postgres`, `multiprocess`, `gpu`, `live_provider`, `playwright`, `slow`, `smoke`, `live_codex`;
    - delete `src/tests/pytest.ini`, or reduce it to nothing and remove it.
  - **Quarantine file** `src/tests/quarantine.toml`:
    - entries are `nodeid` (or `collect_glob` for collection-level problems), `reason`, `category` (`retired_contract` | `env_dependency` | `real_bug` | `flaky` | `unknown`), `wp` (the owning WP), `added` (date);
    - a conftest plugin (`src/tests/conftest_quarantine.py`, loaded from the root conftest) marks listed tests `xfail(strict=True, reason=...)`, so a quarantined test that starts passing fails the run and forces removal. Collection-level entries use `collect_ignore_glob`.
  - **Root conftest cleanup** (`src/tests/conftest.py`):
    - Playwright import only under the `playwright` marker or `importorskip`;
    - remove the Flask port 5000 and the `flask_app` fixture;
    - remove the global `Path.write_text` monkeypatch reset — find what patches it and fix the source;
    - fixtures that need PostgreSQL skip with a clear reason when `OMNIX_TEST_DATABASE_URL` is unset.
- **Steps:**
  1. Run the full suite against a disposable database. Save the outcome inventory to `docs/roadmap/test-triage-<date>.csv` with columns nodeid, outcome, error summary, category, action, wp.
  2. For each failure or error, pick one action:
     - **fix the code** if it is a real bug; add a regression test;
     - **fix the test** if the test is wrong but the behaviour is current;
     - **rewrite** the test against the current contract (e.g. Flask `test_client` → FastAPI `TestClient`; `SQLiteJobStore` → in-memory or PostgreSQL fixture);
     - **delete** the test when the contract is retired *and* equivalent coverage exists — cite the covering test in the CSV;
     - **mark** environment-dependent tests with the right marker (`gpu`, `live_provider`, `playwright`);
     - **quarantine** only when none of the above can be done within this WP, and set `wp` to the WP that will resolve it.
  3. Move the 106 tests under `src/app/rpg/**` into `src/tests/rpg/**`, preserving names.
  4. Handle `.pyfrag` test generation:
     - find the generator (search `pyfrag`);
     - either generate the final test files at commit time with a check that they are current, or inline them;
     - document the choice in DECISIONS.md.
  5. Replace fixed-duration sleeps (55 sites in 33 files) with event- or condition-based waits (`threading.Event.wait(timeout)`, polling helpers with deadlines). This may be spread across later WPs; record the remaining count in the metrics.
  6. Delete the root `run_tests.py`, which is prose and not Python. Update `scripts/run_tests.bat` or delete it if it only runs retired groups. Update the docs that reference either.
- **Metrics:** `quarantined_tests` and `collection_errors` are added to the ratchet. Target at the end of this WP: 0 collection errors; quarantine ≤ 5% of tests. Target at certification: 0.
- **Acceptance:** `python -m pytest` with the disposable database passes (quarantine xfails allowed); the triage CSV is committed; the quarantine file has reasons and owners.

#### WP-1.5 — One required CI pipeline

- **Addresses:** DEL1.
- **Depends on:** WP-1.1, WP-1.2, WP-1.3, WP-1.4 (a partial start is allowed).
- **Goal:** a single `ci.yml` whose jobs are the required checks on `main`.
- **Design:** `.github/workflows/ci.yml`, triggered on `pull_request` (to main) and `push` (main). Permissions: `contents: read`. Concurrency cancels superseded runs.

  | Job | Contents |
  |---|---|
  | `lint` | `ruff check .`; `python scripts/architecture_lint.py --check`; `python scripts/architecture_metrics.py --check`; gitleaks; migration lint (AL014). |
  | `typecheck` | `mypy` (WP-1.6 configuration); `npm --prefix src/apps/web run typecheck`. |
  | `test-unit` | `pytest -m "not postgres and not multiprocess and not gpu and not live_provider and not playwright" -n auto`. |
  | `test-postgres` | PostgreSQL 17 service; `OMNIX_TEST_DATABASE_URL=postgresql://…/omnix_test`; `pytest -m "postgres or multiprocess" -n 2` plus `python scripts/run_architecture_gates.py --group postgresql` and `--group multiprocess`. |
  | `web` | `npm ci --prefix src/apps/web` (Node from `.node-version`); `npm --prefix src/apps/web run lint` (after WP-1.7); `run test`; `run build`; `run api:check`; Playwright app-shell spec (`tests/e2e/app-shell.spec.ts`, chromium, mocked routes). |
  | `docs` | `python docs/render_docs.py`, then `git diff --exit-code -- '*.html'`. |
  | `security` | `pip-audit -r requirements/gateway.lock.txt` (fail on high/critical); `npm audit --omit=dev --audit-level=high --prefix src/apps/web`. |

  Also:
  - `nightly.yml`, scheduled: the full suite including `slow`, the soak harness in `--mock-compute` mode, the benchmark regression check, and the restore rehearsal (WP-10.7).
  - Convert the trading research sweep workflows to `workflow_dispatch` or `schedule` only.
  - Fold unique checks from `architecture-runtime.yml`, `postgresql-persistence.yml`, `agent-runtime.yml`, `rpg-pr-deterministic.yml` and the others into `ci.yml` jobs, or keep them as optional path-filtered workflows. Required checks must not be path-filtered.
  - Delete `apply-pi-engineering-tools-once.yml` (a self-committing workflow with `contents: write`) after confirming it is obsolete. Log the confirmation in PROGRESS.md.
  - Remove `continue-on-error` and soft typecheck handling in `live-voice-latency.yml` and `new-chat-selection.yml`.
  - Replace `npm install` with `npm ci`.
  - Add `.github/CODEOWNERS` (placeholder owners; human fills in) and `.github/dependabot.yml` (pip, npm, github-actions; weekly).
- **Human gate:** enabling branch protection with the required checks is a repository-settings action. Request it in PROGRESS.md.
- **Acceptance:** `ci.yml` is green on a PR; total wall time < 30 min (record it); PROGRESS.md lists the required check names.

#### WP-1.6 — Python type checking rollout

- **Addresses:** DEL1.
- **Depends on:** WP-1.3.
- **Design:**
  - `[tool.mypy]` in `pyproject.toml`: `python_version = "3.11"`, `mypy_path = "src"`, `explicit_package_bases = true`, `namespace_packages = true`, `warn_unused_ignores = true`, `warn_redundant_casts = true`, `check_untyped_defs = true`.
  - **Strict group** (`disallow_untyped_defs = true`, `no_implicit_optional = true`) for the kernel packages as they are created or cleaned: `app.runtime`, `app.config`, `app.security`, `app.persistence` (kernel modules), `app.jobs` (kernel), `app.events`, `app.observability`, `app.capabilities`, `app.conversation`.
  - Every other package starts under `[[tool.mypy.overrides]]` with `ignore_errors = true`. Each module removed from that list must pass `check_untyped_defs`.
  - The metric `mypy_ignored_modules` (count of patterns under ignore) is ratcheted.
- **Acceptance:** `mypy` passes in CI. At certification, 0 ignored kernel modules and ≤ 10% of all modules ignored.

#### WP-1.7 — ESLint for the web app with boundary and patch rules

- **Addresses:** FE1, FE7 (enforcement).
- **Depends on:** WP-1.1.
- **Design:** `src/apps/web/eslint.config.js` (flat config) using `typescript-eslint` recommended and `eslint-plugin-react-hooks` (`rules-of-hooks: error`, `exhaustive-deps: warn`), plus these custom restrictions:

  | Rule | Configuration |
  |---|---|
  | `no-restricted-syntax` | Assignment to `window.fetch`, `globalThis.fetch`, or any `*.fetch` member. Assignment to members of `omnixApiClient`. Assignment to `window.__omnix*` properties. `new MutationObserver(` outside an allow-list file. `document.body.appendChild`/`insertBefore` outside an allow-list. `.innerHTML =` outside the markdown renderer. |
  | `no-restricted-imports` | A feature may import another feature only through `src/features/<name>/index.ts` (public API files created per feature as needed). `src/features/shared` and `src/design` are importable by all. `src/app` may import features only via `ModuleWorkspace`/manifests (see WP-9.7). |

  Baseline existing violations with file-level disable comments in the form `/* eslint-disable <rule> -- baseline WP-9.x */`, generated by a script. The metric `eslint_baseline_disables` is ratcheted to 0 by the end of Phase 9. Add `"lint": "eslint ."` to the web `package.json`.
- **Acceptance:** `npm --prefix src/apps/web run lint` passes; a new `window.fetch =` fails lint (unit test or fixture).

---

### Phase 2 — Kernel, composition and dependency direction

#### WP-2.1 — Neutral runtime package

- **Addresses:** X2 (trading → gateway, jobs → gateway), X3.
- **Depends on:** WP-1.2.
- **Goal:** process runtime concepts live in `app/runtime`, not in the web gateway.
- **Steps:**
  1. Create `src/app/runtime/` with these modules, moving code as noted:

     | New module | Moved from |
     |---|---|
     | `config.py` | `app/runtime_config.py` |
     | `capabilities.py` | `app/runtime_capabilities.py` |
     | `contracts.py` | `app/runtime_contracts.py` |
     | `paths.py` | `app/runtime_paths.py` |
     | `logging.py` | `app/runtime_logging.py` (becomes part of WP-10.1) |
     | `background.py` | `BackgroundWorker`, `GatewayBackgroundRuntime`, `BackgroundOwnershipUnavailable` and `register_background_worker` from `app/gateway/background_runtime.py` |
     | `net.py` | from WP-0.2 |

  2. Update **all** importers in the same PR (mechanical). Do not leave shims unless external scripts import the old paths; check `scripts/`.
  3. `register_background_worker` must not require a FastAPI app. Signature: `register_background_worker(registry: BackgroundRegistry, worker: BackgroundWorker)`, where `BackgroundRegistry` is held by the composition root. Keep a thin adapter on the gateway side (`gateway.state.background_registry`) until WP-2.2 replaces the registrars.
  4. Trading monitors: replace `from app.gateway.background_runtime import …` with `from app.runtime.background import …`.
- **Acceptance:**
  - `grep -rn "app.gateway" src/app/trading src/app/jobs` returns nothing;
  - architecture gates `unit` pass;
  - lint AL001 baseline shrinks accordingly.

#### WP-2.2 — FeatureModule contract and feature catalog

- **Addresses:** X2, X3, X5 (per-feature schema completeness), SCALE (feature enable/disable).
- **Depends on:** WP-2.1.
- **Goal:** each feature is one self-describing module mounted by the composition root; the static `FEATURES` tuple and the whole-app registrars disappear.
- **Design** (`src/app/runtime/features.py`):

  ```python
  @dataclass(frozen=True, slots=True)
  class FeatureModule:
      id: str                                           # stable id, e.g. "audiobook"
      title: str
      requires: frozenset[RuntimeCapability] = frozenset({RuntimeCapability.SERVE_API})
      depends_on: tuple[str, ...] = ()                  # other feature ids (contracts only)
      config_model: type[BaseModel] | None = None       # env prefix OMNIX_<ID>_ (WP-2.3)
      routers: tuple[Callable[["FeatureContext"], APIRouter], ...] = ()
      internal_routers: tuple[Callable[["FeatureContext"], APIRouter], ...] = ()  # service-token routes
      job_handlers: tuple["JobHandlerSpec", ...] = ()   # WP-2.5
      background_workers: tuple[Callable[["FeatureContext"], BackgroundWorker], ...] = ()
      scheduled_tasks: tuple["ScheduledTaskSpec", ...] = ()   # WP-6.3
      repositories: tuple["RepositorySpec", ...] = ()   # WP-2.6
      outbox_consumers: tuple["OutboxConsumerSpec", ...] = ()  # WP-5.3
      settings: tuple["SettingSpec", ...] = ()          # WP-2.3
      permissions: tuple["PermissionSpec", ...] = ()    # WP-4.3
      public_paths: frozenset[str] = frozenset()        # unauthenticated paths (rare)
      lifecycle: "FeatureLifecycle | None" = None       # process-local startup/shutdown

  @dataclass(frozen=True, slots=True)
  class FeatureContext:
      feature_id: str
      config: BaseModel | None
      runtime: RuntimeConfig
      capabilities: RuntimeCapabilities
      services: "KernelServices"   # jobs, assets, blobs, settings, providers, events, audit, db, tenant provider
      logger: logging.Logger
  ```

  - **Catalog:** `src/app/runtime/feature_catalog.py` holds `FEATURE_CATALOG: dict[str, str]`, mapping id to `"app.<pkg>.feature:FEATURE"`. It is the **only** place that lists features.
  - **Enablement:** `OMNIX_FEATURES` (comma list, default `all`) and `OMNIX_FEATURES_DISABLED`. If a disabled feature is a dependency of an enabled one, startup fails with a clear error.
  - **Composition root** (`src/app/gateway/app_factory.py`, replacing the body of `create_gateway_app` in `gateway/main.py`):
    1. builds `KernelServices`;
    2. loads the enabled features;
    3. validates capabilities and dependencies;
    4. mounts each router via `app.include_router(router, dependencies=[Depends(feature_guard(feature.id))])`. `feature_guard` is a no-op placeholder now, and becomes auth plus permission defaults in WP-4.2/4.3;
    5. registers background workers and lifecycles through the existing lifecycle machinery (`gateway/lifecycle.py`).

    Routers keep their current absolute paths. **Do not change URLs** in this WP.
  - **Feature packages** expose `feature.py`. Registrars no longer receive the FastAPI app. Middleware is added only by the kernel.
- **Per-feature migration checklist** (each feature is one PR):
  1. Create `app/<feature>/feature.py` with `FEATURE`.
  2. Convert every `register_*(gateway)` function for the feature into router factories. Routes defined with `@app.get` inside a function become `APIRouter` routes.
  3. **Schema completeness:** every browser-facing route gets `response_model` and a typed request model. Remove `include_in_schema=False` unless the route is internal (move it to `internal_routers`) or a documented transport exception (WebSocket or SSE — document it in `docs/architecture/api-transport-exceptions.md`). Replace `dict[str, Any]` bodies with Pydantic models.
  4. Convert `async def` handlers that do synchronous I/O to `def` (AL005). This overlaps WP-7.1; do it here for the feature's routes.
  5. Remove the entry from `gateway/feature_registry.py:FEATURES` and add it to `FEATURE_CATALOG`.
  6. Regenerate OpenAPI types. Update the web client usages of newly typed routes where the handwritten type conflicts (full migration happens in WP-9.3).
  7. Tests: a router test for each changed route and a feature-disable test (below).
- **Feature order:**
  1. `audiobook` — the reference pilot. Also write `docs/architecture/FEATURE_MODULE_GUIDE.md` from it.
  2. `image` (image_asset_routes, image_reference_routes, image_workspace_routes, image_model_routes).
  3. `voice` (new package `app/voice/`: voice_library_routes, voice_job_summary_routes, tts_runtime_routes, tts_pcm_websocket, tts_live_call_websocket until WP-3.2 moves live parts).
  4. `characters` (characters/api.py, avatar_api, avatar_viseme_api, avatar_generation_api, live2d_avatar, live_conversation_rendering).
  5. `assistant_memory` (routes, settings_routes, management_routes).
  6. `core` kernel features: chat core (`core_chat_routes.py`), jobs and events (`core_jobs_routes.py`), assets (`core_assets_routes.py`), providers/models, settings, diagnostics, reports, prompts, replay, model residency. These become kernel-owned routers in `app/gateway/kernel_routes/` or in their owning kernel packages.
  7. `research`, `hermes`, `assistant_tools`, `agent_runtime`.
  8. `trading` (the router list in `gateway/trading_routes.py`; monitors become `background_workers`, later `scheduled_tasks` in WP-6.3).
  9. `rpg` (24 `gateway/rpg_*` modules and the 21 compatibility routes in `gateway/main.py`, which move to `app/rpg/api/compat_router.py`).
  10. `live_voice` (after WP-3.2), `companion_activity`, `desktop_companion`, `story` (storyteller/podcast; `story_asset_save.py`, `story_audio_text.py`).
- **Exit steps (final PR):**
  - delete `FEATURES` and `register_gateway_features`;
  - `gateway/main.py` contains no inline routes;
  - delete the `core_services.py` re-export barrel (update tests to import from owners);
  - delete the `app.gateway.main.app` alias if unused, or keep it only as the ASGI entry pointing to `app.production:app`.
- **Feature-disable matrix test** (`src/tests/app/test_feature_matrix.py`): for each optional feature id, build the provider-free app with that feature disabled and assert:
  - startup succeeds;
  - none of its paths are in `app.openapi()`;
  - kernel smoke routes respond.

  Run it in `test-unit`.
- **Acceptance:** all features in the catalog; `FEATURES` deleted; matrix test green; OpenAPI diff contains only additions or intentional typed changes (review it); metrics `schema_excluded_routes` and `untyped_body_routes` reduced to only documented transport exceptions and internal routes.

#### WP-2.3 — Typed configuration and a settings service

- **Addresses:** OPS2, X4 (settings part), PERF3 (settings document).
- **Depends on:** WP-2.1.
- **Design:**
  - **Package `src/app/config/`:**
    - `env.py`: the **only** module that reads `os.environ`. It provides typed readers (`env_str`, `env_bool`, `env_int`, `env_url`, `env_list`) that record every variable name read. Values are never logged.
    - `models.py`: kernel configuration sections as frozen Pydantic models (database, bind/network, auth, observability, storage, providers defaults, runtime role — `RuntimeConfig` becomes a section or stays a dataclass wrapped by `OmnixConfig`).
    - `load.py`: `load_config(env=os.environ) -> OmnixConfig`, which validates everything at startup and aggregates errors by variable name without values. Feature configuration comes from `FeatureModule.config_model` with prefix `OMNIX_<FEATURE_ID_UPPER>_`.
    - `registry.py`: exports a machine-readable list of all known variables (name, type, default, feature, description) for docs. Generate `docs/CONFIGURATION.md` from it and check in CI that it is current.
  - **Server-owned user settings** (from the UI) move out of the single JSON document into a typed settings service:
    - New migration `NNNN_settings_entries.sql`: `omnix_settings_entries(workspace_id, key text, value jsonb, revision bigint, updated_by text, updated_at timestamptz, primary key (workspace_id, key))`.
    - Data migration: split the existing settings document (the document row used by `runtime_document_compat` for settings) into entries with `jsonb_each`, idempotently.
    - `app/platform/settings_service.py` (or `app/config/settings_service.py`) provides `get(key)`, `get_section(prefix)`, `set(key, value, expected_revision)` (optimistic concurrency: revision mismatch → 409) and `subscribe(key, callback)` (in-process invalidation plus a `NOTIFY omnix_settings` wake-up after WP-5.4).
    - Settings keys and types come from the existing settings registry (see [ARCHITECTURE.md](ARCHITECTURE.md) "Settings architecture") plus `FeatureModule.settings`.
  - Provider cache invalidation (currently in `shared.save_settings`) subscribes to provider-affecting keys.
- **Steps:**
  1. Implement the package and service.
  2. Replace direct environment reads package by package (AL007 ratchet), starting with the kernel, then trading (55 `OMNIX_*` flags; `OMNIX_PERSISTENCE_MODE` read in 26 monitors), agent runtime (74), RPG and the gateway.
  3. Replace `shared.load_settings`/`save_settings` callers with the settings service (feeds WP-2.8).
  4. `POST /api/settings` accepts a typed patch model (key → value) with validation. Reject unknown keys. Validate URL fields (see WP-4.10 SSRF rules).
- **Acceptance:** AL007 is 0 outside `app/config`; `docs/CONFIGURATION.md` is generated and checked; settings writes use optimistic concurrency; the legacy settings document is no longer written (a test asserts no writes).

#### WP-2.4 — Migrations become a release step; tenant bootstrap leaves request paths

- **Addresses:** PERF2, SCALE4, DATA4, PJ1, OPS3.
- **Depends on:** WP-1.2 (AL012, AL014).
- **Goal:** no request, repository constructor or domain function applies migrations or bootstraps identity. The runtime verifies schema compatibility only. Version N and N+1 can run against the same schema.
- **Design:**
  1. **Release step.**
     - `python -m app.persistence migrate` (exists) is the only path that applies migrations.
     - Add `python -m app.persistence status --json`.
     - Compose gets a one-shot `migrate` service; the gateway `depends_on` it with `condition: service_completed_successfully`.
     - The Windows launcher runs migrate before starting the gateway cohort.
  2. **Runtime.**
     - `ensure_postgresql_runtime_ready()` defaults to `apply_schema_changes=False` and `auto_initialize_fresh_install=False`.
     - The production composition fails startup when required migrations are pending, unless `OMNIX_MIGRATE_ON_START=true`. That setting is allowed only when the role is `worker`, the auth mode is `local`, and `OMNIX_ENV=development`; otherwise it is a startup error.
  3. **Identity.**
     - Split `bootstrap_local_tenant` into:
       - `ensure_local_identity(database) -> TenantContext`: idempotent identity upsert, **no** migrations, audit event only when the identity row is newly created. Called once by the composition root and by CLI tools.
       - `TenantProvider.current() -> TenantContext`: returns the process's local context now; request-scoped from WP-4.2.
     - Replace all 132 non-test call sites. Services receive a `TenantProvider` via constructor or `FeatureContext`, or use `current_tenant()` from `app/security/tenant_context.py` (a contextvar with the process default until WP-4.2).
     - Remove `ensure_postgresql_runtime_ready` calls from repository constructors (18 sites) and compat adapters.
  4. **Compatibility window.**
     - Every migration file starts with a header comment `-- omnix-migration: phase=<expand|contract|data> transactional=<true|false>`. Existing files without a header are treated as `phase=contract transactional=true`.
     - Add columns `phase` and `transactional` to the migrations metadata table (new migration).
     - The app declares `SCHEMA_MIN_CONTRACT` (the newest *contract* migration it requires) and `SCHEMA_KNOWN` (all versions it knows).
     - On startup:
       - unknown applied versions whose phase is `expand` or `data` are allowed (log info);
       - an unknown applied `contract` version is a startup error ("database is newer than this app");
       - a missing required version is a startup error.
     - This replaces the blanket `MigrationDriftError` for unknown versions (`persistence/migrations.py:218-224`).
     - Document the expand/contract procedure in `docs/architecture/MIGRATION_POLICY.md`: add nullable column → dual write → backfill (data) → switch reads → contract (drop) in a later release.
  5. **Ordering and non-transactional migrations.**
     - Canonical order is the existing sort. Verify the implementation and document it.
     - AL014 forbids new duplicate prefixes and new files that sort before the latest applied file.
     - `transactional=false` files run outside a transaction, one statement per file (for `CREATE INDEX CONCURRENTLY`).
     - Pending migrations are computed in canonical order. The runner refuses to apply a lower-sorting unapplied file after a higher one has been applied (this is the out-of-order hazard), unless `--allow-out-of-order` is passed by an operator.
  6. **Database roles.**
     - Support `OMNIX_MIGRATION_DATABASE_URL` (DDL owner role, e.g. `omnix_migrator`) separate from `OMNIX_DATABASE_URL` (runtime role `omnix_app`: DML only, not owner, no `BYPASSRLS`).
     - New migration `NNNN_runtime_role_grants.sql` grants DML on all tables and sets default privileges, but only if the roles exist. Otherwise it no-ops with a `NOTICE`; the local single-role mode keeps working.
     - Readiness in production mode warns (and fails if `OMNIX_REQUIRE_ROLE_SEPARATION=true`) when the runtime role owns tables.
- **Tests:**
  - A test asserting no call path from any route, repository constructor or domain service reaches `apply_migrations` (static: AL012 plus a runtime test that patches `apply_migrations` to raise and exercises representative routes: RPG turn, world library read, chat prompt, character list).
  - A compatibility-window test: apply an extra fake `expand` migration and assert the app still starts; apply a fake `contract` migration and assert it refuses.
  - An out-of-order refusal test.
  - A role-separation test, skipped when roles cannot be created in CI's PostgreSQL service (create them in the CI init script).
- **Measurements:** statement count and duration for one RPG turn and one character-mode chat prompt, before and after (`docs/measurements/migrations-off-request-path-<date>.json`).
- **Acceptance:** AL012 is 0 outside allowed modules; `workspace.local_bootstrap` audit rows no longer appear per request (test); the compatibility-window tests pass; architecture gates `postgresql` pass.

#### WP-2.5 — Jobs kernel inversion: typed handler registry

- **Addresses:** X2, PJ3 (dispatch), PJ4, R4.
- **Depends on:** WP-2.2 (features exist), WP-2.4.
- **Goal:** `app.jobs` is a kernel that knows no feature. Features register handlers.
- **Design:**
  - `src/app/jobs/handlers.py`:

    ```python
    @dataclass(frozen=True, slots=True)
    class JobHandlerSpec:
        type: str                           # e.g. "image.generate"
        handler: Callable[["JobExecutionContext", JobRecord], "JobOutcome"]
        input_model: type[BaseModel]        # validates job.input_payload at submission and execution
        resource_class: ResourceClass       # cpu | llm | tts | stt | image | research | ...
        timeout_seconds: float
        max_attempts: int = 3
        retry_backoff: "Backoff" = Backoff(base_seconds=2, factor=2, max_seconds=300, jitter=0.2)
        submission_policy: Callable[[CreateJobRequest], CreateJobRequest] | None = None  # defaults, guards
    ```

    `JobHandlerRegistry` is built from the enabled features and rejects duplicate types. `execute_durable_feature_job` (currently an if/else at `durable_feature_worker.py:336-360`) dispatches through the registry. An unknown type fails the job non-retryably with code `unsupported_job_type`.
  - `JobExecutionContext` provides:
    - a fenced job handle bound to `(worker_id, lease_token)`: progress, logs, stages, heartbeat, complete, fail;
    - a cancellation token;
    - blob store, provider service, settings service, tenant context (from the job's workspace and principal);
    - a logger with correlation ids (WP-10.2).
  - **Submission:** `JobService.create_job` validates `input_payload` against `input_model` and applies `submission_policy`. The RPG turn guard (`jobs/rpg_turn_job_guard.py`) becomes RPG's `submission_policy`. `jobs/models.py` must not import platform defaults (lines ~146-152); voice-cloning and effective defaults become policies of their features.
- **Moves** (update imports; no shims):

  | From | To |
  |---|---|
  | `jobs/image_inline.py` | `app/image/jobs.py` |
  | `jobs/voice_inline.py` | `app/voice/jobs.py` |
  | `jobs/research_inline.py` | `app/research/jobs.py` |
  | `jobs/inline_feature_jobs.py` + `jobs/inline_feature_jobs/` (shadow package loading via importlib) — story/podcast parts | `app/story/jobs.py` |
  | the same, RPG parts | `app/rpg/jobs.py` |
  | `jobs/rpg_last10_report.py`, `jobs/rpg_debug_job_hook.py`, `jobs/rpg_turn_job_guard.py` | `app/rpg/jobs/` |

  Also delete the shadow-package importlib trick.
- **Import-time installs:** delete the 7 installs in `jobs/__init__.py` (lines ~48-55). `InMemoryJobStore` moves to `src/tests/support/in_memory_jobs.py` (test-only) and executes through the same registry. If any production path still depends on in-memory inline execution, stop and escalate (§1.6).
- **Single owner of the jobs table:**
  - All SQL on `omnix_jobs*` lives in `persistence/job_repository.py` and `persistence/execution_repositories.py`.
  - Replace the 57 raw statements outside persistence (e.g. `rpg/worlds/generation_worker.py:177-223`, `rpg/worlds/lifecycle_service.py:249-252`) with `JobService` operations: cancel, delete-by-owner, list-by-type/status with cursor.
  - AL006 reaches 0.
- **Tests:**
  - registry duplicate rejection;
  - unknown type fails non-retryably;
  - input validation at submit;
  - one handler per feature with a fake provider;
  - backoff schedule respected;
  - a test that `app.jobs` imports no feature package (AL001 covers it).
- **Acceptance:** `jobs` fan-out consists only of kernel packages; AL006 is 0; durable worker, audiobook and architecture gate tests pass.

#### WP-2.6 — Persistence kernel inversion and a composable unit of work

- **Addresses:** X2, PJ4–PJ6.
- **Depends on:** WP-2.5.
- **Goal:** `app.persistence` contains only kernel infrastructure and repositories. Feature repositories live in features. The unit of work stops constructing 33 repositories and stops importing RPG.
- **Design:**
  - **Kernel persistence keeps:** database, config, authority, `unit_of_work` (generic), tenant, identity service, migrations runner, outbox repository, job repositories, asset repository, blob store, audit, lifecycle/retention, the document store (generic, with revision), contracts.
  - **`UnitOfWork`:**
    - exposes kernel repositories as attributes (`work.jobs`, `work.audit`, `work.identities`, `work.outbox`, `work.assets`);
    - exposes `work.repository(RepoType) -> RepoType` for feature repositories registered via `RepositorySpec(type, factory)` in `FeatureModule.repositories`;
    - constructs repositories lazily, at most once per transaction.
  - **Moves:**

    | From | To |
    |---|---|
    | `persistence/rpg_*.py` (21 files) | `app/rpg/persistence/` |
    | `persistence/chat_compat.py`, `chat_runtime_compat.py`, conversation repositories | `app/chat/persistence/` |
    | `character_compat.py`, `avatar_compat.py` | `app/characters/persistence/` |
    | `memory_compat.py`, `owner_memory_compat.py`, memory job execution | `app/assistant_memory/persistence/` |
    | `document_feature_compat.py` classes | their owners |
    | `execution_feature_compat.PostgresProviderModelRefreshStore` | providers |
    | model residency | stays kernel (`app/jobs/residency_repository.py`) |
    | `image_asset_compat.py` | `app/image/persistence/` |
    | `configuration_compat.py` | owner of assistant configuration (`app/assistant_tools/persistence/`) |

    Update `runtime_composition.py` factories accordingly. That module shrinks as FeatureModules provide factories.
  - **Migrations:** keep one ordered stream in `persistence/migrations/` (out of scope to split it).
- **Acceptance:** AL001 shows `app.persistence` imports no feature package; the unit of work constructs only kernel repositories eagerly; the persistence architecture gates pass; compat inventory updated.

#### WP-2.7 — Platform package cleanup

- **Addresses:** X1 (the platform patch), X2.
- **Depends on:** WP-2.2 (RPG feature exists).
- **Steps:**
  1. Remove the import-time replacement in `app/platform/__init__.py` (lines 1-11). Make `app.rpg.session.new_game.create_new_game_session` natively call the progress-aware implementation: fold `create_new_game_session_with_progress` into the owner, or make the RPG compat router call the progress variant explicitly.
  2. Move `platform/rpg_player_compat.py`, `rpg_session_compat.py`, `rpg_session_genesis_compat.py`, `rpg_inspection_compat.py` and `rpg_adventure_compat.py` into `app/rpg/api/compat/`.
  3. `app.platform` keeps settings registry, diagnostics, reports, legacy sessions (if still used) and effective defaults (only kernel-level ones).
- **Acceptance:** `app.platform` imports no RPG module (AL001); the RPG compat routes still pass their tests.

#### WP-2.8 — Retire `shared.py`

- **Addresses:** X4, SEC (plaintext secrets file), PERF4 (cache).
- **Depends on:** WP-2.3, WP-7.2 part A (provider service), WP-4.9 (secret store) — or an interim secret-store adapter.
- **Steps:**
  1. Paths and constants → `app/runtime/paths.py` and `app/config`.
  2. Settings and sessions → settings service (WP-2.3) and the chat store. Legacy `sessions.json` callers: find them, migrate or delete.
  3. Secrets → `SecretStore` (WP-4.9). Delete `SECRETS_FILE` read/write and the plaintext fallback. Provide a one-time importer CLI, `python -m app.security import-legacy-secrets`, which imports `resources/data/secrets.json` if present and renames it to `.imported`.
  4. Provider getters → `ProviderService` (WP-7.2): `get_provider`, `get_tts_provider`, `get_stt_provider`, `invalidate_provider_cache`.
  5. Text utilities → `app/text.py`.
  6. Delete `install_postgresql_document_callbacks`/`clear_postgresql_document_callbacks`, the callback registration in `persistence/runtime_install.py`, and the settings/sessions entries in `runtime_document_services.py` that exist only for `shared.py`. Update the compat inventory.
  7. Delete `src/app/shared.py`.
- **Acceptance:** the file no longer exists; there are no file fallbacks for settings, sessions or secrets anywhere (test: grep for `SETTINGS_FILE`, `SESSIONS_FILE`, `SECRETS_FILE` returns nothing); ADR-0010 compliance test added (with the database unavailable, settings reads fail closed).

#### WP-2.9 — Package cycles to zero

- **Addresses:** X2.
- **Depends on:** WP-2.1–WP-2.8 (most cycles disappear with them).
- **Steps:** resolve every remaining cycle as listed in Appendix B. Key new kernel packages:
  - `app/conversation/` (contracts): `ChatSession`, `ChatMessage`, `PromptMemoryItem` models; a `TranscriptReader` Protocol; `estimate_tokens`. chat, memory and characters depend on it. Prompt orchestration stays in chat and receives memory/character collaborators via ports wired at composition.
  - `app/capabilities/`: the canonical capability registry and tool-adapter registry. agent_runtime and assistant_tools both depend on it.
  - `app/testing` production package: move to `src/tests/support/`. Remove production imports of it (`chat↔testing`, `jobs↔testing`).
- **Acceptance:** AL002 is 0; the metric `package_cycles` is 0.

---

### Phase 3 — Removal of runtime patching

#### WP-3.0 — Characterization harness

- **Addresses:** a prerequisite for X1 work.
- **Depends on:** WP-1.4.
- **Design:** `src/tests/characterization/` provides:
  - `harness.py` with `capture(scenario_name, fn) -> dict`, which normalizes results (strips timestamps, UUIDs and durations; sorts unordered collections) and compares against `golden/<scenario>.json`;
  - an environment flag `OMNIX_UPDATE_GOLDEN=1` that regenerates goldens. Regenerating is allowed **only** in the PR that introduces the scenario, before the refactor, and must be stated in the PR description.

  Deterministic fakes: `FakeLLMProvider` (scripted responses per prompt hash), `FakeTTS`, `FakeMarketData` (fixed bar series). Follow Appendix F.
- **Scenarios to create before the corresponding WP:**

  | Scenario | Captures | Before WP |
  |---|---|---|
  | chat-live-sse-turn | SSE event sequence, persisted messages, store method calls | 3.1 / 3.2 |
  | live-voice-prompt | Assembled system prompt and messages for a fixed session, character, profile and memory | 3.2 |
  | live-voice-tts-lane | Phrase segmentation and frame schedule with FakeTTS | 3.2 |
  | rpg-turn | Seeded 20-turn run: state hash per turn, visible response, events | 3.3 (after 3.3a) |
  | trading-evaluate | Fixed bars → proposals, authorization decisions, paper orders, events for `TradingStrategyMonitor._evaluate_candidates` and `_run_config` | 3.4 |
  | job-store-guards | RPG turn submissions and debug hook behaviour | 3.5 |

- **Acceptance:** the harness plus the first scenario are merged, with a written guide in `src/tests/characterization/README.md`.

#### WP-3.1 — Chat store: native targeted mutations; remove the whole-workspace save

- **Addresses:** CM1, PJ2, X1 (gateway → persistence patch).
- **Depends on:** WP-2.6 (chat persistence moved), WP-3.0.
- **Steps:**
  1. Fold `gateway/live_chat_postgres_fast_path.py` (the patches of `PostgresChatSessionStore.get_session`, `PostgresCharacterChatSessionStore.begin_user_message` and `complete_streamed_reply`, lines ~535-586) into the store classes as their native implementations.
  2. Add native single-session operations for every mutation now done via `save_sessions`:
     - `set_session_interaction`
     - `append_user_message`
     - `append_assistant_message` (proactive)
     - `save_interrupted_reply`
     - rename, archive, soft delete
     - update profile fields

     Each operation locks only its session row (`FOR UPDATE`), writes only its rows, and bumps the session revision.
  3. Migrate every caller (about 30; start with `chat/store.py:275-330, 476-517` and `chat/character_store.py:80-137, 173, 284, 412, 416-449`).
  4. Delete `save_sessions` delete-by-difference logic (`chat_compat.py:67-82`) and the whole-workspace `load` that pulls 200 full transcripts (`:35-43`). List views use a summary projection with cursor pagination.
  5. Remove the process-local chat lock as a correctness mechanism (`chat/concurrency.py:8`). Row locks are the mechanism; a local lock may remain only as an optimization.
- **Tests:**
  - more than 200 sessions: operations on the oldest still work;
  - two concurrent processes (multiprocess test): creating a session on process A while process B mutates another session never soft-deletes A's session;
  - characterization chat-live-sse-turn still matches.
- **Acceptance:** `grep -rn "save_sessions(" src/app` returns nothing in production code; the multiprocess test passes.

#### WP-3.2 — Live voice becomes a module (`app/live_voice`) with explicit ports

- **Addresses:** PR1, X1, X3, R2 (partial).
- **Depends on:** WP-3.1, WP-3.0 (live-voice scenarios).
- **Goal:** remove every live-chat and live-voice hook from `gateway/runtime_hooks.py:initialize_gateway_runtime_hooks`, and move the domain logic out of `app/gateway`.
- **Design:**

  ```text
  app/live_voice/
    feature.py            # FeatureModule: routers (SSE/WebSocket), background workers (lane), settings, permissions
    contracts.py          # Protocols: TranscriptStore, PromptBuilder, LLMStream, TTSLane, SpeculationCache, Metrics
    prompt/               # builder.py (assembly), cache.py (character snapshot / profile envelope / identity caches),
                          # window.py, dependency_stages.py, companion_context.py, spoken_style.py, profile.py
    llm/                  # stream.py (low-latency streaming), routing.py (provider routing), retry.py,
                          # metrics.py, lmstudio_responses.py, lmstudio_model_resolution.py, lmstudio_diagnostics.py
    speech/               # tts_lane.py (execution lane), speculative_tts.py, runtime_offload.py,
                          # startup_frame_policy.py, pcm_diagnostics.py
    transport/            # sse.py (bridge, OmnixStreamingResponse), websocket.py (live call), routes.py
    speculation.py        # bounded caches (size + TTL), no deep copies of full transcripts
    diagnostics.py
  ```

  The pipeline is composed **explicitly** in `app/live_voice/pipeline.py` as a list of named stages. The stage order reproduces the current hook composition order; document it in a comment derived from the installation order in `runtime_hooks.py` (Appendix A.1).
- **Steps** (split into PRs by sub-area: prompt, llm, speech, transport):
  1. For each hook in Appendix A.1, move its logic into the corresponding module as a direct implementation, called by the pipeline instead of wrapping methods.
  2. Replace the global `StreamingResponse.__init__` patch (`live_sse_transport.py:~374`) with an `OmnixStreamingResponse` subclass used by the live routes.
  3. Replace the `tts_live_call_websocket.get_tts_provider` seam swap (runtime_hooks.py lines ~146-148) with constructor injection of a `TTSProviderResolver`.
  4. `memory_job_offload` → submit durable memory jobs through `JobService` (a handler registered by `assistant_memory`). Delete the process-local executor.
  5. Delete `gateway/live_chat_speculative_tts.py` (never referenced), following Appendix G.
  6. Delete `initialize_gateway_runtime_hooks` and the imports at the top of `runtime_hooks.py`. Delete `runtime_hooks.py` once `_install_required_rpg_turn_hooks` is also gone (WP-3.3c).
  7. `assistant_context/__init__.py:18-56` (the route grab-bag registering memory, character, avatar, desktop and TTS routes) is removed. Those routes belong to their FeatureModules.
- **Tests:** the live-voice characterization scenarios match; the existing live-voice test suites pass (`src/tests/live_speech`, `src/tests/app/test_live_voice_*`); the latency benchmark doesn't regress (use the existing live-voice latency harness if runnable, else record a skip reason).
- **Acceptance:** `app/gateway` contains no `live_chat_*`, `live_voice_*` or `tts_live_*` domain modules (thin route shims allowed only if they just import routers); AL003 is 0 for these files; the metric "gateway lines" drops by ~15K.

#### WP-3.3 — RPG: determinism, an explicit turn pipeline, and collapsing the runtime parts

Split into five sub-WPs, executed in order.

**WP-3.3a — Deterministic core (fixes RPG1)**

- **Depends on:** WP-1.2 (AL013).
- **Design:**
  - Each session has an immutable `rng_seed` (a 64-bit integer).
    - For new sessions, generate it at creation (`secrets.randbits(64)`) and store it in state.
    - For existing sessions without a seed, derive it as `int.from_bytes(sha256(session_id).digest()[:8], "big")` and persist it on the next save (an upcaster).
  - Per-decision RNG: `rng_for(session_seed, turn_index, purpose: str, sub_index: int = 0) -> random.Random`, seeded with `sha256(f"{seed}:{turn}:{purpose}:{sub}")`.
    - `resolve_player_action` requires a seed, which `runtime_part09.py:469` must pass as `rng_for(..., purpose="player_action")`. Make the `seed` parameter mandatory in `action_resolver.resolve_player_action`, `resolve_attack_roll` and `resolve_noncombat_check`.
  - Text-choice randomness (16 global `random` calls) uses `rng_for(..., purpose="text:<site>")`.
  - A `Clock` Protocol is injected in the turn context. The turn input carries `now` captured once at the boundary. Idle-tick gating (`runtime_part20.py:128`) uses the recorded turn time, not the wall clock.
  - Deterministic ids: `uuid5(namespace=session_uuid, name=f"{turn}:{purpose}:{counter}")` in the core (9 `uuid4` calls).
  - AL013 covers the RPG core package list (Appendix D).
- **Tests:** a replay test that plays 50 turns with `FakeLLMProvider`, then replays from the initial state with the recorded inputs, and asserts identical state hashes per turn. Wire the existing state-hash utilities (`core/determinism.py`) into it.
- **Acceptance:** AL013 is 0; the replay test is in CI.

**WP-3.3b — Characterization of the turn pipeline** — create the `rpg-turn` scenarios (WP-3.0) using seeded sessions: combat, dialogue, item use, travel, idle, first call, fast paths.

**WP-3.3c — Explicit ordered turn pipeline (replaces the hooks)**

- **Design:** `app/rpg/session/pipeline.py`:

  ```python
  class TurnStage(Protocol):
      name: str
      optional: bool                       # optional stages may degrade with a logged metric, never silently
      def run(self, ctx: TurnContext) -> TurnContext: ...
  TURN_PIPELINE: tuple[TurnStage, ...] = (...)   # explicit order
  ```

- **Steps:**
  1. Convert each of the 19 optional hooks in `rpg/session/__init__.py:79-101` and the required hooks in `gateway/runtime_hooks.py:83-122` into stages or direct code. List in Appendix A.3.
  2. Delete `_try_install_optional_hook` and `_install_optional_fast_runtime_hooks`.
  3. Replace `except Exception: return` with explicit failures, or with optional-stage degradation that logs and emits a metric.
  4. `rpg_turn_job_mirror` (a gateway hook plus middleware `_install_middleware`) becomes an explicit post-commit stage or outbox consumer.
  5. Remove the 4 `sys.meta_path` import hooks (e.g. `player_agency_runtime_hook.py:153-169`) by making the intercepted modules call the intended code directly.
  6. The in-memory session and submission locks (`interaction_timeline_hook.py:23-24`, `rpg_turn_job_mirror.py:34`) become database row locks (the campaign row `FOR UPDATE` already exists in `rpg_turn_service`) or advisory locks keyed by session.
- **Acceptance:** RPG characterization matches; AL003/AL004 are 0 in `app/rpg/session`; no `install_*` remains in `app/rpg`.

**WP-3.3d — Collapse the 40 runtime parts**

- **Steps:**
  1. Replace the globals merge in `rpg/session/runtime.py:54-65,140,145-151` with explicit modules named by responsibility. Suggested split: `turn_apply.py`, `state_normalization.py`, `npc_turns.py`, `narration.py`, `interactions.py`, `idle.py`, `combat_flow.py`, `inventory_flow.py`, `bootstrap_payload.py`, `persistence_bridge.py`. Adjust to the actual content.
  2. Keep exactly one `_apply_turn_authoritative`: the currently effective one after all parts load (defined 15 times; the last binding wins). Break it into functions of ≤ 150 lines.
  3. Remove all 246 star imports (AL010) and the 53 `globals()` calls in `app/rpg`.
  4. Replace the 1,000-line file cap in `scripts/check_rpg_file_lines.py` with the global policy: files ≤ 1,200 lines, functions ≤ 150 lines, tracked by metrics.
- **Acceptance:** `runtime_part*.py` files are gone; characterization matches; AL010 is 0 in RPG.

**WP-3.3e — Fix hidden errors masked by `sitecustomize`** — fix `rpg/ai/npc_initiative.py:416` (`opening_bonus` undefined) and any other `NameError` that F821 revealed in RPG.

#### WP-3.4 — Trading: fold the import-time overlays into their owners

- **Addresses:** TR1, X1.
- **Depends on:** WP-3.0 (trading-evaluate scenario), WP-1.3 (Python 3.11).
- **Goal:** `app/trading/__init__.py` installs nothing. The effective behaviour lives in the owning functions. The paper-authorization wrapper becomes explicit composition.
- **Procedure:**
  1. Fold installers **in their current installation order** (Appendix A.4), one installer per PR where large.
  2. For each installer, for each target it patches:
     - move the wrapper's logic into the owning function or method, preserving composition order: the new owner body equals `wrapper(original)` semantics;
     - delete the patch line;
     - run the trading characterization and the trading test suite (`src/tests/trading`).
  3. Because each fold happens in install order, later still-installed wrappers keep wrapping the (now modified) owner, so behaviour stays identical at every step.
  4. `_AuthorizedStrategyPaperRepository` (from `trading_data_hardening.py:596-614`): `TradingStrategyMonitor._run_config` constructs it natively (explicit decoration of the paper repository in the method body). WP-8.3 later moves the authorization into `OrderGateway`.
  5. After all folds, delete the modules that only contained overlays (`*_fixes`, `*_refinements`, `*_hardening`, `*_reliability`), or rename what remains to responsibility names.
  6. Remove the standard-library enum patch (WP-1.3 prerequisite).
  7. Delete the unused `install_trading_route_hook` (`gateway/trading_routes.py:116-128`).
- **Acceptance:** trading AL003/AL004 are 0; characterization matches; the trading suite passes; a test proves the authorization gate applies when `strategy_monitor` is imported directly without importing `app.trading` (import-order independence).

#### WP-3.5 — Composition-root and jobs-kernel class patches

- **Addresses:** X1.
- **Depends on:** WP-2.5.
- **Steps:**
  1. `install_rpg_turn_job_guard(PostgresJobStoreAdapter)` (`runtime_composition.py`) → RPG `submission_policy` (WP-2.5).
  2. `install_rpg_debug_job_hook(...)` → a kernel `JobObserver` protocol (`on_created`, `on_started`, `on_completed`, `on_failed`), registered by the RPG feature when its debug setting is enabled.
  3. `install_live_agent_store_hooks(...)` (`chat/live_agent_store.py:45`) → explicit collaborator injection into the chat store (a live-agent planner port), wired by the composition root.
  4. `services.jobs.chat_execution_owner = owner` and `services.jobs.chat_dispatcher = dispatcher` (`production.py`) → constructor parameters of the job service or chat execution service. Do not set attributes on a cached singleton.
- **Acceptance:** `runtime_composition.py` contains no `install_*` calls; AL003 is 0 for these files.

#### WP-3.6 — Agent runtime patch seams

- **Addresses:** AR1, X1.
- **Depends on:** WP-3.0 (add agent scenarios: run lifecycle, child run, approval, promotion).
- **Steps:**
  1. Remove `AgentRunService.__getattribute__` (`service.py:548-574`) and the module-global rebinding in `pi_runtime.py` (~75, 102, 116, 234) and `review_orchestration.py:213-221`.
  2. Replace them with constructor-injected collaborators. The full service split is WP-8.2; this WP makes the seams explicit so the split is mechanical.
- **Acceptance:** AL003 is 0 in `app/agent_runtime`; agent runtime tests (127 files) pass.

#### WP-3.7 — Delete `sitecustomize.py` and `usercustomize.py`

- **Addresses:** X1, DEL1.
- **Depends on:** WP-3.3e.
- **Steps:**
  1. Read `src/usercustomize.py` and document what it does.
  2. RPG narrator paths that call `LMStudioProvider.generate`/`generate_stream`/`call` (added by `sitecustomize.py:22-91`) must use an explicit adapter, `app/rpg/ai/llm_gateway_adapter.py`, wrapping any `BaseProvider`.
  3. Find call sites by deleting `sitecustomize` locally and running the RPG and provider suites.
  4. Delete both files.
- **Acceptance:** the files are gone; suites pass; a test asserts that `builtins` has no `opening_bonus` attribute after importing the app.

#### WP-3.8 — Delete legacy patchers and unused route hooks

- **Addresses:** X1, X6.
- **Depends on:** WP-2.2 exit, WP-3.1–3.7.
- **Steps:**
  1. Remove all `FastAPI.__init__` patchers (48 files) and unused `install_*_route_hook` functions, e.g.:
     - `install_blocking_route_offload_hook`
     - `_install_local_browser_cors_hook`
     - `install_audiobook_route_hook`
     - `install_rpg_*_route_hook`
     - `install_hermes_route_hook`
     - `install_realtime_route_hook`
     - `install_research_mode_route_hook`
  2. Remove `_remove_hook_installed_assistant_context_routes` (`gateway/main.py:649-659`).
  3. Delete `gateway/assistant_turn_routes.py` and `gateway/assistant_context_routes.py` if still unused (Appendix G).
  4. Delete `gateway/blocking_route_offload.py` (requires WP-7.1 complete).
- **Acceptance:** metrics `install_hook_functions` = 0, `fastapi_init_patchers` = 0, `foreign_attribute_assignments` = 0 in `src/app`; lint baseline for AL003/AL004 is empty.

---

### Phase 4 — Identity, authorization, tenancy and agent safety

Phase 4 may start after WP-1.5. Authentication is enforced by middleware first, so it doesn't wait for WP-2.2. Router-level dependencies are added as features migrate.

#### WP-4.1 — Authentication

- **Addresses:** SEC1.
- **Depends on:** WP-0.3, WP-1.5.
- **Design** (package `src/app/security/`):
  - **Modes** (`OMNIX_AUTH_MODE`):
    - `local` (default for local installs);
    - `oidc` (enterprise);
    - `disabled` — allowed only when `OMNIX_ENV=test`, or `development` with the bind host on loopback. Otherwise startup error.
  - **Sessions:** new migration adding `omnix_auth_sessions`:
    - columns: `id` (random, stored as its sha256), `user_id`, `workspace_id` (default workspace), `created_at`, `last_seen_at`, `expires_at`, `absolute_expires_at`, `revoked_at`, `csrf_secret`, `user_agent_hash`, `auth_method`;
    - cookie `omnix_session`: HttpOnly, `SameSite=Strict`, `Secure` when served over HTTPS (config), `Path=/`;
    - sliding expiry 12 h, absolute 7 days (configurable).
  - **Local mode:**
    - An **install credential** is created on first start: a random 32-byte secret, stored hashed with `hashlib.scrypt` in `omnix_install_credentials`. Its plaintext is written once to the protected secret store (WP-4.9; interim: DPAPI on Windows, a 0600 file on POSIX) so the launcher can use it.
    - The launcher obtains a one-time login code via an internal CLI endpoint (`python -m app.security login-code`, which writes a 60-second single-use code to the database) and opens `http://127.0.0.1:5173/auth/local/callback?code=<code>`. That route exchanges the code for a session cookie and redirects to `/`.
    - Manual login page `/login`: the user pastes the install credential (shown by `python -m app.security show-install-credential`, which requires local console access).
    - The user is the existing `user:local` in `workspace:local` with role `owner` (backward compatible).
  - **OIDC mode:**
    - Authorization Code + PKCE: `/auth/oidc/login` → IdP → `/auth/oidc/callback`.
    - ID token validated with PyJWT against JWKS (cached, refreshed on unknown `kid`), checking issuer, audience, expiry, nonce and `azp` when present.
    - Users map by `(issuer, sub)` into `omnix_users`, with an `external_identities` table added by migration. Just-in-time provisioning is controlled by `OMNIX_OIDC_ALLOWED_DOMAINS`/`OMNIX_OIDC_REQUIRED_GROUP`; workspace membership comes from configuration or group claims.
    - Bearer JWT access tokens are accepted for API clients (`Authorization: Bearer`), with a configurable audience.
  - **Middleware** `AuthenticationMiddleware`:
    - resolves the principal from the session cookie, bearer token or service token (internal routers only);
    - **denies by default**: 401 for unauthenticated requests, except public paths (`/health`, `/ready`, `/auth/*`, `/login`, static assets) and `FeatureModule.public_paths`;
    - WebSocket upgrades require a valid session cookie (browser) or bearer token (non-browser);
    - token query parameters are never accepted.
  - **CSRF:**
    - Double-submit: the server sets a non-HttpOnly `omnix_csrf` cookie derived as `HMAC(session.csrf_secret, session.id)`.
    - State-changing requests must send `X-Omnix-CSRF` equal to it.
    - This replaces the WP-0.3 `X-Omnix-Client` requirement for cookie-authenticated requests. Keep the Origin checks.
  - **Web:**
    - login route and page;
    - `OmnixApiClient` middleware adds `X-Omnix-CSRF` (read from the cookie);
    - on 401, redirect to `/login?next=…`;
    - update `viewApiScope.ts` so the firewall passes the header through.
  - **Launcher control app** (`launcher/control_app.py`): the same auth (it is an operator surface), or loopback-only plus the service token. Choose auth and log the choice.
- **Tests** (`src/tests/security/test_auth_*.py`):
  - unauthenticated request → 401 on every non-public route (auto-enumerated);
  - login flows for local and OIDC (OIDC with a fake IdP: local JWKS and signed tokens);
  - session expiry, revocation and rotation;
  - CSRF missing or wrong → 403;
  - WebSocket without a session → rejected;
  - the `disabled` mode startup guard.
- **Human gate:** switching existing installations from no-auth to `local` changes operator workflow. The launcher must auto-login; document the change in `docs/OPERATIONS.md` and request approval before merging the default flip.
- **Acceptance:** tests pass; the web app works end to end with local auth via the launcher (Playwright test with a login fixture).

#### WP-4.2 — Per-request principal and tenant context

- **Addresses:** SEC1, SCALE6.
- **Depends on:** WP-4.1, WP-2.4.
- **Design:**
  - `Principal(user_id, memberships: tuple[TenantContext, ...], auth_method, session_id)`. Reuse `TrustedPrincipal` in `persistence/tenant.py`, renamed or extended.
  - The FastAPI dependency `require_principal` and a contextvar `current_principal`.
  - `current_tenant()` resolves the workspace from the `X-Omnix-Workspace` header, if present and the user is a member, or else the user's default workspace. The composition root mounts every feature router with `Depends(require_principal)`.
  - Repositories take `TenantContext` explicitly. Remove the `local_tenant_context()` defaults (20 repositories).
  - Background jobs record `principal_user_id` and `workspace_id` at submission. Execution sets the tenant context from the job.
  - Scheduled tasks run per workspace (iterate active workspaces) with a system principal flagged `system=True`, which has only the permissions the task declares.
- **Acceptance:** AL012 is 0 outside allowed modules; a test runs two users in two workspaces and asserts isolation at the API level.

#### WP-4.3 — Authorization (RBAC with a permission catalog)

- **Addresses:** SEC1.
- **Depends on:** WP-4.2, WP-2.2 (router-level defaults).
- **Design:**
  - Permissions are strings (`<domain>:<action>`). The starter catalog is in Appendix C; features add theirs via `FeatureModule.permissions`.
  - Roles: `owner` (all), `admin` (all except ownership transfer and credential export), `member` (feature read/write, tool proposals, agent runs, no approvals of high-risk capabilities, no settings or admin), `approver` (additive role: approvals), `viewer` (read-only).
  - The role → permission mapping lives in code (`app/security/roles.py`) and is overridable by configuration.
  - Enforcement: `require_permission("x:y")` dependency per route. Router factories set a default read permission for GET and a write permission for mutating methods, with per-route overrides.
- **Tests:** `test_every_route_declares_permission_or_is_public` enumerates `app.routes`, including WebSocket routes; a role matrix test for representative routes; a viewer attempting a mutation gets 403.
- **Acceptance:** tests pass; the permission catalog is documented in `docs/security/PERMISSIONS.md`.

#### WP-4.4 — PostgreSQL row-level security

- **Addresses:** SCALE6, SEC1.
- **Depends on:** WP-4.2, WP-2.4 (role separation).
- **Design:**
  - A migration enables RLS on every table with a `workspace_id` column. Generate the list from `information_schema` in a data-phase migration, or enumerate explicitly (preferred for review):

    ```sql
    ALTER TABLE t ENABLE ROW LEVEL SECURITY; ALTER TABLE t FORCE ROW LEVEL SECURITY;
    CREATE POLICY tenant_isolation ON t
      USING (workspace_id = current_setting('omnix.workspace_id', true))
      WITH CHECK (workspace_id = current_setting('omnix.workspace_id', true));
    ```

  - The unit of work runs `SELECT set_config('omnix.workspace_id', %s, true)` at transaction start from the current `TenantContext`. Transactions without a tenant fail (except kernel system operations listed explicitly).
  - Cross-workspace system work (retention, recovery scans) iterates workspaces, setting the configuration per workspace. Listing workspaces uses a `SECURITY DEFINER` function `omnix_list_active_workspaces()` owned by the migrator role.
  - Global tables without `workspace_id` (migrations metadata, runtime nodes, users) get explicit policies or remain non-RLS with a documented justification.
- **Tests:** with a raw SQL query missing the `workspace_id` filter, a test run as workspace A cannot read B's rows (proves RLS, not app filtering); writes with a mismatched `workspace_id` fail.
- **Acceptance:** metric `rls_coverage` is 100% of tenant tables; tests pass under the runtime role.

#### WP-4.5 — Approvals bound to principals; a single CapabilityExecutor

- **Addresses:** SEC2, AR2.
- **Depends on:** WP-0.4, WP-4.3, WP-2.9 (`app/capabilities`).
- **Design:**
  - `omnix_capability_approvals` (WP-0.4): `requested_by` and `decided_by` are now principal user ids. Approve or deny requires `tools:approve` or `agent:approve`. The approver may not be the run token or service token. Self-approval is allowed only for low-risk capabilities when configured (`approval_self_allowed_max_risk`).
  - `app/capabilities/executor.py: CapabilityExecutor.execute(grant: Grant, capability_id, input, *, approval_id=None, idempotency_key) -> ExecutionResult`.
    - `Grant` comes from the broker's RunSpec (agent path) or from a user-initiated proposal (tool path).
    - It validates scope, resource limits and budget, and approval when required (the digest must match).
    - It writes an idempotent execution record and evidence, then calls the adapter from a fail-closed adapter registry: an unknown tool is an error, not `adapter_status: pending` (`hermes_bridge.py:84-92`).
  - Route all 9 call sites of `hermes_assistant_tool_execute_payload` through the executor:
    - `broker_api.py:980`
    - `chat_bridge.py:924,1852`
    - `task_graph_runtime.py:53-55`
    - `workflow_runtime.py:47`
    - `assistant_tools/routes.py:108`
    - `assist_core/live_agent_planner.py:84`
    - `chat/live_agent_store.py:66,156`

    Delete `approved = node.approval_policy == "allow_automatic"` (`task_graph_runtime.py:932-941`). Tool budget and wall-time accounting happen in the executor (server-side), not only in the TypeScript guard.
  - Workflow registration over HTTP requires `agent:workflows:admin`.
- **Tests:** each call site uses the executor (static test: `hermes_assistant_tool_execute_payload` is referenced only by the executor); an unknown adapter errors; budget is charged server-side; approval by a run token is rejected.
- **Acceptance:** tests pass; the agent runtime authority tests pass unchanged, or are updated with justification.

#### WP-4.6 — Run-scoped signed tokens for the broker and model gateway

- **Addresses:** SEC2, AR (model gateway L1).
- **Depends on:** WP-4.5.
- **Design:**
  - `app/security/run_tokens.py`: token = base64url(`payload`) + "." + base64url(`HMAC-SHA256(key, payload)`), where `payload = {"run_id", "attempt", "caps_digest", "exp", "nonce"}`.
    - Key: `OMNIX_RUN_TOKEN_KEY`, generated at install and stored in the secret store.
    - TTL 15 minutes, renewed by the owner process.
  - The Pi broker extension and the model gateway require `Authorization: OmnixRun <token>`. `X-Omnix-Agent-Run-Id` alone is rejected.
  - Token delivery to the Pi process: an environment variable consumed at startup by the broker/guard extensions and **removed from `process.env`** before any shell tool runs. Also add it to the environment deny-list in `process_environment.py`/`pi_runtime_core.py` for child processes. Verify with a test that a shell tool cannot read it.
  - Agent-facing endpoints (broker, model gateway, guard budget) move to an internal router, optionally on a separate listener (`OMNIX_AGENT_LISTENER_PORT`, loopback).
- **Tests:** missing, invalid or expired token → 401; a shell child process cannot see the token; the model gateway rejects a run id without a token.
- **Acceptance:** tests pass.

#### WP-4.7 — Agent sandbox by default, egress control, global run limits

- **Addresses:** SEC6, AR (H1).
- **Depends on:** WP-4.6.
- **Design:**
  - Profiles that can mutate the workspace default to isolation `docker_strong`, using the existing `isolation.py` support with memory, CPU and pid limits.
  - If Docker is unavailable, a mutating run fails with a clear error unless `OMNIX_AGENT_ALLOW_UNSANDBOXED=true`. The UI then shows a persistent warning, and the audit records the override.
  - Read-only profiles may run supervised without a sandbox.
  - Network: the sandbox runs with `--network none`, plus access to the broker through a mounted unix socket (POSIX) or a dedicated internal Docker network whose only reachable endpoint is the broker (Windows/Docker Desktop). Enforce `network_policy="broker-only"` this way (currently only logged: `pi_runtime_core.py:141,492`).
  - "Safe" auto-approved command prefixes (`pi_guard_extension.ts:251-257,674-680`) are auto-approved **only inside the sandbox**. Outside it they require approval.
  - Workspace root allow-list (WP-0.4) enforced in `local_workspace.py`. In-place mutation of a `workspace_root` without a repository (`service_core.py:2673-2674`) is allowed only for allow-listed roots.
  - `browser.open` `workspace_preview` (`browser_adapter.py:969-1010`) runs `npm run dev` inside the sandbox container, with the port mapped to loopback. The hard-coded `src/apps/web` path (`:96`) becomes configuration.
  - Global concurrency: `OMNIX_AGENT_MAX_CONCURRENT_RUNS` (default 2) enforced via a database counter row with `FOR UPDATE` (safe across processes).
  - `HOME` is not passed through (`pi_runtime_core.py:29-46`); use a sandbox home.
- **Tests:** a mutating run without Docker fails unless the override is set; network egress from the sandbox to a non-broker address fails (integration test, skipped where Docker is unavailable, run in CI with Docker); the concurrency limit holds across two processes.
- **Acceptance:** tests pass; documented in `docs/security/AGENT_SANDBOX.md`.

#### WP-4.8 — Audit logging for sensitive actions

- **Addresses:** SEC8.
- **Depends on:** WP-4.2.
- **Design:**
  - `app/security/audit.py: AuditService.record(action, target_type, target_id, outcome, details=None)`. It takes principal, workspace and request id from context.
  - Actions:
    - `auth.login` / `auth.logout` / `auth.failed`
    - `settings.update`
    - `secret.set` / `secret.delete`
    - `approval.decide`
    - `capability.execute`
    - `agent.run.start` / `stop` / `promote`
    - `trading.control.*`
    - `trading.paper.order`
    - `feature.toggle`
    - `admin.*`
  - Revoke UPDATE and DELETE on `omnix_audit_events` from the runtime role. Retention through the maintenance path only (WP-5.2).
  - Details must pass the content-free sanitizer (`gateway/content_free_diagnostics.py`): no prompts, no secrets.
- **Acceptance:** a test per action asserts an audit row; the runtime role cannot delete audit rows.

#### WP-4.9 — Secret store

- **Addresses:** X4, SEC4 (prevention).
- **Depends on:** WP-2.3.
- **Design:**
  - `app/security/secrets.py: SecretStore` Protocol with `get`, `set`, `delete`, `names`. Backends:
    - `EnvSecretStore` (read-only);
    - `WindowsDpapiSecretStore` (reuse `provider_secret_store.py`);
    - `KeyringSecretStore` (optional extra `keyring`) for macOS and Linux;
    - `ExternalVaultSecretStore`: an interface only, with documentation on implementing HashiCorp Vault or Azure Key Vault — out of scope to implement.
  - Selection: `OMNIX_SECRET_STORE=auto|env|dpapi|keyring`.
  - No plaintext file backend.
  - Assistant tool credentials (currently `unavailable_assistant_tool_secret` in production: `runtime_document_services.py`) use the secret store, so tools work under PostgreSQL authority without plaintext storage.
- **Acceptance:** no code path writes secrets to plaintext files (test with a fake filesystem watcher or grep); `settings.py` masking is preserved.

#### WP-4.10 — Hardening: headers, rate limits, docs exposure, SSRF, disclosure

- **Addresses:** SEC7.
- **Depends on:** WP-4.1.
- **Steps:**
  1. **Security headers middleware:** `Content-Security-Policy` (for the gateway-served pages; Nginx serves the SPA with its own CSP in WP-11.3), `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, `Permissions-Policy` (microphone allowed for self), `X-Frame-Options: DENY` / `frame-ancestors 'none'`, and HSTS when HTTPS.
  2. **Rate limits:** login endpoints (5/min per IP + user); approval and execute endpoints (configurable). In-process token bucket plus ingress limits (WP-11.3).
  3. **Docs exposure:** `/docs`, `/redoc` and `/openapi.json` require `admin:*` in non-development environments. The schema export script uses the app factory offline and is unaffected.
  4. **SSRF:** provider `base_url`/endpoint settings go through `app/security/url_policy.py`.
     - Allowed: http and https only; loopback; private CIDRs in `OMNIX_ALLOWED_PRIVATE_NETWORKS` (default: none except loopback); public hosts.
     - Always blocked: link-local `169.254.0.0/16`, `fe80::/10`, metadata hostnames.
     - Validate at settings write time and resolve at connect time (DNS-rebinding safe: check the resolved IP).
  5. **llama.cpp provider:** remove port-owner killing (`llamacpp_provider.py:93-95,142-145`); if the port is busy, error out. Restrict model paths to the models directory.
  6. **Disclosure:** asset APIs return ids and download URLs, never `storage_path` (`assets/models.py:36`); raw exception text is never returned (WP-10.5 envelope).
- **Acceptance:** tests per item (headers present, rate limit triggers, `/docs` protected, SSRF cases blocked, no `storage_path` in responses).

#### WP-4.11 — Threat model, ASVS checklist, security test suite

- **Addresses:** the Security 9/10 exit criteria.
- **Depends on:** WP-4.1–4.10.
- **Steps:**
  1. `docs/security/THREAT_MODEL.md`: STRIDE per component (browser, ingress, gateway API, worker, scheduler, job workers, model services, PostgreSQL, blob store, agent sandbox, Hermes, trading providers, assistant tool integrations), with mitigations mapped to WPs.
  2. `docs/security/ASVS_L2_CHECKLIST.md`: every OWASP ASVS 4.0.3 Level 2 requirement with status (pass / fail / N/A) and evidence (test or file). Target ≥ 90% pass; failures justified.
  3. `src/tests/security/` suite in CI: auth matrix, CSRF, Origin/Host, WebSocket auth, RLS, approvals, run tokens, sandbox (Docker job), SSRF, headers, secrets not in logs (log capture test with canary secrets).
- **Acceptance:** documents complete; suite green; checklist ≥ 90% pass.

---

### Phase 5 — Data and persistence

#### WP-5.1 — Complete job fencing and job-engine hygiene

- **Addresses:** PJ3, DATA (job logs).
- **Depends on:** WP-0.5, WP-2.5.
- **Steps:**
  1. Every job mutator takes `(worker_id, lease_token)` and checks them **in the same UPDATE** (`WHERE id=$1 AND lease_owner=$2 AND lease_token=$3 AND status='running'`): progress, input, stages, logs, heartbeat, complete, fail, cancel finalization. Remove the check-then-act in the durable worker guard (`durable_feature_worker.py:66-101`).
  2. Job logs move to an append-only table `omnix_job_logs(job_id, workspace_id, seq, level, message, data, created_at)`, replacing the metadata rewrite that has no row lock (`job_compat.py:516-531`).
  3. Add a CHECK constraint on job status values.
  4. Retries use the handler's `retry_backoff` (WP-2.5). Retry delay 0 is gone (`execution_repositories.py:551`). Expired leases retry after backoff and count attempts; exceeding `max_attempts` → dead letter.
  5. Priority aging: effective priority = priority + floor(age_seconds / `OMNIX_JOB_PRIORITY_AGING_SECONDS`), capped.
  6. The lease release sweep moves from every claim (every 250 ms, `job_repository.py:240-243`) to a scheduled task every 5 s (WP-6.3).
- **Tests:** a stale worker cannot update progress or logs after takeover; concurrent cancel and log update both persist; the backoff schedule holds; dead letter after max attempts.
- **Acceptance:** ADR-0013 updated; tests pass.

#### WP-5.2 — Retention and lifecycle worker

- **Addresses:** DATA1.
- **Depends on:** WP-6.3 (scheduler) or an interim `BackgroundWorker`; WP-4.4 (per-workspace iteration).
- **Design:**
  - `app/persistence/retention.py: RetentionWorker` executes the policies in `omnix_retention_policies` (migration 0016).
  - Deletes run in batches (`DELETE … WHERE ctid IN (SELECT ctid … LIMIT 5000)`) with a statement timeout, per workspace, and record `omnix_lifecycle_cleanup_runs`.
  - Default policies (add missing ones by migration):

    | Data | Retention |
    |---|---|
    | Terminal jobs | 30 days |
    | Job attempts / job logs / job events | 30 days after job terminal |
    | Resolved dead letters | 90 days |
    | Outbox published | 7 days |
    | Inbox processed | 7 days |
    | Agent run events | 30 days after run terminal, keeping evidence-referenced events |
    | Trading strategy events | 180 days (configurable) |
    | RPG snapshots | keep last 20 per campaign plus every 100th turn |
    | Runtime nodes | stopped/expired older than 7 days |
    | Audit | 365 days (configurable, maintenance path only) |
    | Auth sessions | expired + 7 days |

  - Enforce the capacity policies in `omnix_capacity_policy` at admission (reject with a retryable 429 and a metric), or document why each one is advisory.
  - **Partitioning (conditional):** if any table exceeds 20M rows or a retention batch exceeds 2 s p95 in the soak benchmark, convert it to monthly range partitions on `created_at`: create a partitioned table, dual-write, backfill, swap in a maintenance window (expand/contract migrations). Document the decision per table in DECISIONS.md.
- **Tests:** policies delete eligible rows and keep ineligible ones (fixture); evidence-referenced agent events are kept; a boundedness test inserts N days of data, runs retention and asserts row counts.
- **Acceptance:** metric `retention_policies_executed` = all; the soak benchmark shows bounded table growth.

#### WP-5.3 — Outbox relay and consumers

- **Addresses:** DATA2.
- **Depends on:** WP-2.2, WP-6.3.
- **Design:**
  - `app/events/outbox_relay.py: OutboxRelayWorker`:
    - claims batches via the existing `claim_batch` (`persistence/outbox_repository.py:90`);
    - dispatches to `OutboxConsumerSpec(event_type_pattern, consumer_name, handler)` registered by features;
    - records per-consumer inbox dedup (existing schema, migration 0011);
    - marks rows published;
    - issues `NOTIFY omnix_outbox, '<workspace_id>:<event_type>'` after commit.
  - Consumers:
    - an SSE bridge that publishes domain events to the browser event stream (WP-5.4);
    - cache invalidation (settings, providers);
    - the RPG turn job mirror (from WP-3.3c);
    - agent run event projections (WP-7.4).
  - Event types with no consumer after this WP: stop writing them, and log the list in DECISIONS.md.
- **Acceptance:** metric `outbox_consumer_coverage` = 100% of written types; outbox lag metric (oldest unpublished age) exposed; tests for dedup and retry.

#### WP-5.4 — Event delivery: one reader, NOTIFY wake-up, commit-safe cursor

- **Addresses:** PERF5, R9.
- **Depends on:** WP-5.3 (optional), WP-2.2.
- **Design:**
  - Add `tx_id xid8 NOT NULL DEFAULT pg_current_xact_id()` to `omnix_job_events` (expand migration; backfill old rows with `'0'::xid8`) plus an index `(workspace_id, tx_id, id)`.
  - **Reader query:** `WHERE workspace_id=$1 AND (tx_id, id) > ($2, $3) AND tx_id < pg_snapshot_xmin(pg_current_snapshot()) ORDER BY tx_id, id LIMIT $4`. This delivers only rows whose transactions are older than every in-progress transaction, so a late-committing lower id cannot be skipped.
  - **Cursor** (SSE `id:` field) = `"<tx_id>:<id>"`. Old integer cursors are accepted and translated conservatively (restart from that id with `tx_id` 0).
  - One `EventReader` per process and workspace:
    - `LISTEN omnix_events` on a dedicated connection;
    - wakes on NOTIFY (published by the event writer after commit, and by the outbox relay), with a fallback poll every 5 s;
    - fans out to subscribers through bounded `asyncio.Queue(maxsize=1000)`.
  - A slow subscriber whose queue fills is disconnected with a final `event: resync`; the client reconnects with its cursor.
  - Replay limit per connection: 5,000 events, then `event: resync` (the client refetches state via queries).
  - One `/events` implementation: delete the divergent one in `gateway/runtime_app.py` or in `gateway/main.py`, whichever is less resilient.
- **Tests:**
  - A concurrency test: two transactions, the lower id commits after the higher; the reader delivers both, in order, exactly once.
  - Subscriber count does not change database query rate (count queries with 1 vs 100 subscribers in a test harness).
  - Slow subscriber disconnect.
  - Reconnect with cursor resumes without duplicates.
- **Measurements:** idle database queries per second with 1, 10 and 100 subscribers, before and after.
- **Acceptance:** tests pass; measurement recorded; R9 closed.

#### WP-5.5 — Collections: cursor pagination and projections everywhere

- **Addresses:** DATA5, R6.
- **Depends on:** WP-2.2.
- **Design:**
  - A standard `CursorPage[T]` response: `items`, `next_cursor`, `has_more`. The cursor is an opaque base64 of the ordering key `(created_at, id)` or equivalent, in stable order. Request parameters: `limit` (default 50, max 200), `cursor`, and filters (`type`, `module`, `status`, `q`).
  - Apply to: assets (remove the 500 cap in `asset_compat.py:34`; push the image gallery filter into SQL: `gateway/image_workspace_routes.py:61-75`), jobs (by type, status, module), chat sessions (summary projection), RPG sessions and worlds (summary columns; no full state), agent runs, trading lists (orders, events, alerts), audiobook projects, voice library.
  - List endpoints return **projections**. Full documents are fetched by id.
  - Replace the 29 unbounded `fetchall()` calls in repositories with paged queries or explicit limits. Add a lint heuristic (AL015) counting `fetchall()` in repository modules whose SQL lacks `LIMIT`, ratcheted to 0.
- **Tests:** pagination over 1,000+ mixed assets returns every image asset once; stable under concurrent inserts.
- **Acceptance:** R6 closed; metric `capped_500_queries` = 0; `unbounded_fetchall` = 0.

#### WP-5.6 — RPG state model: typed state, deltas, periodic snapshots

- **Addresses:** RPG4, PERF3.
- **Depends on:** WP-3.3d, WP-2.6.
- **Design:**
  - A typed Pydantic `CampaignState` (versioned, `schema_version`) with **upcasters** from older `state_jsonb` shapes. Existing saved sessions must load — a hard requirement.
  - Per turn, a single transaction does:
    1. read the campaign row `FOR UPDATE` (once);
    2. apply the turn in memory;
    3. write the new state **once**, and the turn row with a compact delta (JSON Patch RFC 6902 of the state change);
    4. write a full snapshot only every `OMNIX_RPG_SNAPSHOT_EVERY` (default 20) turns;
    5. write the outbox event.
  - Remove the second `save_session` rewrite after the turn, and the redundant re-hash passes (canonical JSON + SHA computed once).
  - Revision semantics: a save at the same revision with a different hash raises a conflict (409). Do not silently bump (`rpg_compat.py:103-110`).
  - Summary columns on the campaign table (title, updated_at, turn count, player level, location name) for list views.
  - Narration jobs move out of session JSON into the jobs system (an `rpg.narration` job type, WP-2.5).
- **Measurements:** per-turn statement count, bytes written (WAL via `pg_stat_wal` before/after in the benchmark), and turn persistence p95 for 100 KB and 1 MB states.
- **Acceptance:** RPG turn overhead excluding LLM p95 < 150 ms at 1 MB state; legacy session fixtures load via upcasters (test with real historical state samples from the test fixtures).

#### WP-5.7 — Chat and memory query performance

- **Addresses:** DATA3, CM2.
- **Depends on:** WP-3.1.
- **Steps:**
  1. History search: `pg_trgm` GIN index on message content, or a generated `tsvector` column with a GIN index. Remove `COUNT(*)` per turn (`chat_runtime_compat.py:73-127`); use `LIMIT n+1` for has-more.
  2. Conversation-summary lookup: an indexed key `(workspace_id, session_id, kind)` instead of scanning up to 5,000 documents (`chat_runtime_compat.py:45-64`).
  3. Transcript windowing: the prompt assembly loads only the window it needs (last N messages plus summaries), never the full transcript.
  4. Context budget per model: use the provider's advertised context window (ProviderSpec, WP-8.4) instead of the fixed 65,536 (`context_budget.py:10-11`).
- **Acceptance:** chat prompt assembly DB time p95 < 30 ms with a 10k-message session (benchmark recorded).

#### WP-5.8 — Blob storage protocol and S3-compatible adapter

- **Addresses:** SCALE5, PERF7 (storage part), R14.
- **Depends on:** WP-2.6.
- **Design:**
  - Use the existing `BlobStore` Protocol (`persistence/contracts.py:116-120`). Extend it if needed: `put_stream(key, stream, content_type) -> BlobRef(key, size, sha256)`, `open(key) -> stream`, `delete(key)`, `presign_get(key, ttl) -> url | None`.
  - `LocalBlobStore` stays the default; it is constructed only in the kernel storage module (AL011).
  - `S3BlobStore` (optional extra `boto3`) targets S3-compatible endpoints. Compose adds MinIO in a `storage` profile for integration tests.
  - Assets store `blob_key`, not an absolute `storage_path`:
    - expand migration adds `blob_key`;
    - backfill computes keys from existing paths relative to the storage root;
    - switch reads;
    - contract later drops `storage_path` exposure.
  - The 21 files that read `storage_path` switch to `BlobStore.open`.
  - Voice-clone discovery by directory scan (`assets/canonical_voice_clones.py:37`) becomes asset records.
  - The image service writes outputs through the gateway blob API (a service-token internal upload endpoint), or directly to the shared S3 bucket. The gateway never depends on the image service's local disk.
  - Remove triple storage of generated audio: one blob, the asset record references it, and the job row references the asset id — no base64 in job rows (`jobs/voice_inline.py:337,568-575`).
  - Uploads stream to the blob store with size limits (audiobook `routes.py:349`, STT uploads, image references `reference_transport.py:31`).
- **Tests:** the asset suite runs against both `LocalBlobStore` and `S3BlobStore` (MinIO in CI); job rows contain no base64 payloads over 1 KB (test); remaining whole-file buffering paths removed (`asset_service.py:68-82`, `coordinated_recovery.py:213-223`).
- **Acceptance:** metric `absolute_storage_path_reads` = 0; the multi-host test in WP-6.8 passes with MinIO.

#### WP-5.9 — JSONB governance and optimistic concurrency

- **Addresses:** DATA3.
- **Depends on:** WP-5.5.
- **Steps:**
  1. Generate `docs/architecture/JSONB_INVENTORY.md`: each JSONB column, whether it is queried, filtered, updated partially or opaque, and a decision.
  2. Promote queried or filtered fields to typed columns (expand/contract) with indexes.
  3. The document store gets a `revision` column and compare-and-set updates (`persistence/document_store.py:56-92` currently last-writer-wins). Callers handle 409.
  4. Validate document shapes with Pydantic at the repository boundary for every document table.
- **Acceptance:** inventory complete; every "queried" field is promoted or has a justified GIN index; document-store writes are conditional.

#### WP-5.10 — Connection and transaction management

- **Addresses:** SCALE7, PJ1.
- **Depends on:** WP-2.4.
- **Steps:**
  1. Per-role pool sizes are configurable (`OMNIX_DB_POOL_MAX` per role, defaults: API 10, worker 10, job worker 5, scheduler 3). A startup check computes the expected total from `OMNIX_DEPLOYMENT_PROCESS_COUNTS` (or the compose profile) against `SHOW max_connections` and warns above 80%.
  2. The advisory-lock connection is dedicated and created outside the pool (`background_runtime.py:74-81`).
  3. Authority checks: one per transaction (cache the result in the unit of work); `database.transaction()` performs the same checks as the unit of work, or is made private to the kernel.
  4. Use `run_transaction` (currently 0 callers) for serialization-failure and deadlock retries around admission-critical transactions: chat admission, job claim, RPG turn.
  5. Statement timeouts per class: request 5 s, job 30 s, maintenance 120 s, via `SET LOCAL statement_timeout`.
- **Acceptance:** pool metrics exposed (WP-10.3); the round trips per unit of work reduced (measured).

#### WP-5.11 — Migration lint in CI

- **Addresses:** DATA4.
- **Depends on:** WP-2.4, WP-1.2.
- **Steps:**
  1. AL014 plus a SQL check:
     - `CREATE INDEX` on existing large tables (from a list) must be `CONCURRENTLY` in a `transactional=false` migration;
     - no `DROP COLUMN` or `DROP TABLE` in an `expand` migration;
     - every migration has the header.
  2. Document the checks in `MIGRATION_POLICY.md`.
- **Acceptance:** lint runs in CI; a synthetic bad migration fails.

---

### Phase 6 — Execution plane and horizontal scalability

#### WP-6.1 — Job worker pools by resource class, as a standalone process

- **Addresses:** SCALE1, PJ3 (shared pool).
- **Depends on:** WP-2.5, WP-5.1.
- **Design:**
  - `python -m app.worker --pools llm=2,image=1,tts=1,research=2,cpu=4` (new `src/app/worker/__main__.py`). Each pool claims only job types whose `resource_class` matches, with its own concurrency.
  - Workers are stateless and can run on any host: they claim with `SKIP LOCKED` and fence by lease.
  - The gateway worker role keeps singleton schedulers only; job execution moves to job workers. In local mode the launcher starts one job worker process with default pools.
  - Graceful shutdown: stop claiming, finish in-flight jobs within a deadline, release leases on exit.
  - Readiness and metrics per pool.
- **Acceptance:** multiprocess test with two job workers and 100 jobs: every job runs exactly once, pools respect concurrency, and killing a worker mid-job leads to reclaim after lease expiry.

#### WP-6.2 — Device permits for GPU capacity across processes

- **Addresses:** SCALE3, R5, PR (H6).
- **Depends on:** WP-6.1.
- **Design:**
  - Table `omnix_device_permits`:
    - columns: `device_id` (e.g. `host:gpu0`), `model_class` (`tts`, `stt`, `image`, `llm-local`), `capacity` (units), `holder_id`, `units`, `priority` (`realtime` > `interactive` > `batch`), `lease_expires_at`, `acquired_at`;
    - configured capacity per device and class in `omnix_device_capacity`.
  - `DevicePermitService.acquire(device, class, units, priority, lease)` is fenced and renewable; the lease expires on process death.
  - **Realtime reservation:** a configured number of units is reserved for `realtime`. Batch jobs yield: the audiobook "yield to realtime" pattern (`render_service.py:155-172`) generalizes here.
  - Integrations:
    - job claim for GPU classes (acquire before claim, or claim then acquire with a short wait and requeue);
    - the image service;
    - the TTS service (via the gateway facade or service-side admission);
    - the live voice lane;
    - RPG world forge.
  - Delete the per-process semaphores (`generation_jobs.py:40`, `image_inline.py:22-23`, `structured_provider.py:24`, `rpg_world_forge_provider.py:41`), or reduce them to local concurrency caps, and delete the lock-file priority markers (`tts_priority.py:96-136`) once permits cover TTS.
  - One owner per model: local TTS inside the worker gateway and `tts_server.py` must not both load the model. Configuration chooses; readiness fails on a double load.
- **Tests:** two processes contending for one permit never exceed capacity; permits are released on expiry; realtime preempts batch within the configured bound.
- **Acceptance:** R5 closed; diagnostics show permit holders.

#### WP-6.3 — Scheduler with per-task ownership

- **Addresses:** SCALE1, TR2/TR3 (monitor loops).
- **Depends on:** WP-2.2.
- **Design:**
  - `ScheduledTaskSpec(name, interval_seconds | cron, jitter, timeout_seconds, run: Callable[[TaskContext], Awaitable[None]], executor: "async" | "thread" | "process", max_overlap=1, requires=...)`, declared in `FeatureModule.scheduled_tasks`.
  - `app/runtime/scheduler.py`:
    - each task runs under its **own** advisory lock (`pg_try_advisory_lock(hash(task_name, workspace))`), so tasks spread across several scheduler processes and no single worker is a bottleneck;
    - bounded executors per class (thread pool size configurable; process pool for CPU-bound tasks);
    - overlap prevention, per-task timeout, metrics (duration, failures, lag).
  - Migrate: trading monitors (22), retention (WP-5.2), outbox relay (WP-5.3), chat recovery, lease sweep (WP-5.1), memory maintenance, agent supervisors (WP-6.5).
  - The single background advisory lock (ADR-0011) remains for tasks that must be globally singleton together, or is replaced by per-task locks. Update ADR-0011.
- **Acceptance:** two scheduler processes split tasks with no duplicate execution (test); trading monitors run under the scheduler; `gateway/trading_routes.py` no longer registers monitors.

#### WP-6.4 — Live voice scaling

- **Addresses:** PR2, SCALE1.
- **Depends on:** WP-3.2, WP-6.2, WP-7.3.
- **Design:**
  - Live-call routes run on API replicas when remote TTS is configured (ADR-0012).
  - Ingress routes a call's HTTP SSE and WebSocket traffic to the same replica using a call-affinity key (cookie `omnix_call_affinity` or header `X-Omnix-Call-Id` with consistent hashing: `hash $http_x_omnix_call_id consistent;` in Nginx). Remove the default worker pinning (`X-Omnix-Gateway-Affinity: worker` in `live-speculation-direct-gateway-transport.ts:74`) when remote TTS is configured.
  - Call state is per-call and in-process; affinity guarantees locality. Nothing authoritative lives there: the transcript persists through the chat store.
  - The TTS service exposes a streaming synthesis endpoint (binary PCM chunks) with admission control via device permits. It returns 429 with `Retry-After` when saturated, and the live lane degrades gracefully.
  - Concurrency per replica: `OMNIX_LIVE_MAX_CALLS` (default derived from permits); readiness reports capacity.
- **Tests:** a load test with N concurrent simulated calls using FakeTTS behind the permit service: capacity scales linearly with added TTS capacity units; overload returns 429, not timeouts.
- **Acceptance:** the load test result is recorded in `docs/measurements`.

#### WP-6.5 — Agent runtime concurrency and durability

- **Addresses:** AR3, SCALE2, PERF6 (locking).
- **Depends on:** WP-6.1, WP-6.3, WP-3.6.
- **Steps:**
  1. Replace the global RLock (`service_core.py:238`) with per-run locks (a per-run `asyncio.Lock`/`threading.Lock` registry, with a bounded LRU). Cross-process mutual exclusion comes from the run lease in PostgreSQL.
  2. Move git diff capture, acceptance, promotion, `npm ci` and Pi spawn out of locks and request threads into jobs: `agent.workspace.prepare`, `agent.run.start`, `agent.promote`. `POST /api/agent-runs` returns 202 with the run id.
  3. Supervisors start through a `ScheduledTaskSpec`/`BackgroundWorker` at startup, not lazily on first `get()` (`service_core.py:489-490,1969-1995`).
  4. `update_state` fenced by lease token (`repository.py:398-442`).
  5. Command delivery: the process hosting the Pi session polls its commands (existing command table). A command for a session hosted elsewhere is picked up by the owner, never silently dropped. Add a test with two processes.
  6. `start_child` does not hold the parent row lock during worktree creation or install (`service.py:644-687`): take the lock only for the short state transition.
  7. Replace the 27 silent `except Exception` blocks with logged handling (AL009 ratchet).
- **Acceptance:** a two-process test covers start, steer, approve and complete across processes; no request thread spawns processes.

#### WP-6.6 — Inventory and elimination of process-local state

- **Addresses:** SCALE2.
- **Depends on:** WP-6.5, WP-3.3c.
- **Steps:**
  1. Generate `docs/architecture/PROCESS_LOCAL_STATE.md` from a scan of module-level mutable containers, locks and caches in `src/app` (extend the metrics script).
  2. Classify each entry:
     - **cache** — must be bounded (size + TTL) and invalidatable;
     - **coordination** — must move to the database;
     - **per-connection** — allowed when covered by affinity.
  3. Fix all coordination entries:
     - RPG locks (done in 3.3c);
     - the trading range-backtest results map (`strategy_api.py:206-207`) → jobs plus stored results;
     - the execution-plane instrument map (`execution_observation_plane.py:71-74`) → bounded;
     - the image service progress map (`image_service_runtime.py:29-30`) → bounded;
     - speculation caches → bounded plus TTL.
- **Acceptance:** the inventory contains only approved categories; metric `unbounded_module_caches` = 0.

#### WP-6.7 — Rolling deployment support

- **Addresses:** SCALE4.
- **Depends on:** WP-2.4, WP-6.1, WP-6.3.
- **Steps:**
  1. On SIGTERM: drain — readiness goes false immediately, stop admitting new work, finish in-flight requests and streams within `OMNIX_DRAIN_SECONDS` (default 30), release leases and locks, exit.
  2. Report version in `/ready` and diagnostics (`build_revision`).
  3. Test: run version N (current branch) and a simulated N+1 (the same code plus an extra expand migration and a new feature flag) side by side, and perform a rolling restart of replicas under load. Assert zero failed requests other than retried idempotent ones, and no duplicate job execution.
- **Acceptance:** the rolling-upgrade test passes in the nightly workflow.

#### WP-6.8 — Multi-host topology test and capacity benchmarks

- **Addresses:** the Scalability 9/10 exit criterion.
- **Depends on:** WP-5.8, WP-6.1–6.4.
- **Steps:**
  1. `docker-compose.multihost-test.yml` with: PostgreSQL, MinIO, migrate, 2 API replicas, 1 scheduler, 2 job workers, fake model services (CPU fixtures) and Nginx. Each service has its own container filesystem (no shared local volumes except for PostgreSQL and MinIO data).
  2. A test script drives chat, jobs, events, assets and live-call simulation through Nginx.
  3. Extend `scripts/benchmark_gateway_scaling.py`/`measure_gateway_soak.py` with the new topology.
  4. Record p50/p95/p99 and throughput. Store the SLO baselines (WP-10.6).
- **Acceptance:** nightly green; results under `docs/measurements`.

---

### Phase 7 — Performance

#### WP-7.1 — Event-loop correctness

- **Addresses:** PERF1, R2, RPG3, TR3 (handlers).
- **Depends on:** WP-1.2 (AL005).
- **Steps:**
  1. For every AL005 violation (229): if the handler does synchronous I/O, change it to `def` (FastAPI's thread pool). If it genuinely needs async (streaming), keep `async def` and offload synchronous calls with `await asyncio.to_thread(...)` or a bounded executor.
  2. Do it per package, one PR each: characters, assistant_memory, gateway core, RPG, trading, image, desktop_companion, assistant_tools, assistant_context, research, live_speech.
  3. RPG turn pipeline (`gateway/rpg_turn_pipeline.py`):
     - `load_session`, narrative generation and save run off the loop;
     - canonical narrative generation becomes a job or a bounded executor;
     - **shadow narrative generation off by default** (`shadow.py:34,232`, sampling 0%). Enable it via a setting.
  4. Model services (`src/tts_server.py:492-550`): synthesis runs in a dedicated executor with concurrency = device capacity; the event loop only streams.
  5. The cold TTS provider lookup is offloaded (`tts_live_call_websocket.py:373` → `live_voice_runtime_offload.py:239-247`).
  6. Streaming bridges: `model_gateway.py:97` parks a default-executor thread per chunk. Use a dedicated bounded executor, or an async client (httpx `AsyncClient`, WP-7.2).
  7. Delete `gateway/blocking_route_offload.py` once no allow-listed route remains async-with-sync-I/O.
- **Tests:** an event-loop lag test runs a slow fake DB/provider (200 ms) concurrently with a health probe loop and a WebSocket frame loop. Assert lag p99 < 20 ms (use the existing `event_loop_lag_monitor.py` and the baseline benchmark `scripts/benchmark_gateway_baseline.py`).
- **Acceptance:** AL005 is 0; the lag test is in CI; benchmark recorded.

#### WP-7.2 — Provider transport, registry and caching

Split into Part A (service and cache) and Part B (transport).

- **Addresses:** PERF4, PR4, X4.
- **Depends on:** WP-2.3.
- **Part A — `ProviderService`** (`app/providers/service.py`):
  - `ProviderSpec(id, factory, capabilities: frozenset[Capability], config_model, context_window_resolver)`, registered **explicitly** (a list in `app/providers/catalog.py`, not glob auto-discovery at `registry.py:46-71` and `audio_registry.py:46-104`). Duplicate ids are rejected: fix the double `faster-qwen3-tts` registration (`audio_plugins.py:281-292` vs `faster_qwen3_tts_provider.py:350-357`).
  - `ProviderService.get(provider_id | None, *, capability) -> ProviderHandle`:
    - keyed cache by `(provider_id, config_hash)`;
    - reference counting: a handle returned to a caller is released via a context manager (`with provider_service.lease(...) as provider:`);
    - eviction closes an instance only when its refcount reaches 0.
  - Settings are read from the settings service cache with invalidation, not re-read on every call.
  - Replace `shared.get_provider` (49 call sites) and the 43 provider-name conditionals with capability-based selection and spec metadata.
  - RPG's `ProfileBoundProvider` (`production_pipeline.py:82-95`) must not mutate the shared instance. It passes per-call options (`model`, `temperature`, `timeout`) as call arguments, supported by the provider interface.
- **Part B — transport:**
  - Each HTTP provider holds one `httpx.Client` (sync) and/or `httpx.AsyncClient` with connection pooling, `timeout=httpx.Timeout(connect=5, read=<per-call>, write=10, pool=5)`, and HTTP/1.1 keep-alive.
  - Retry middleware for idempotent calls (GET, model listing, health) and for 429/503 honouring `Retry-After`; exponential backoff with jitter; `max_retries` from configuration (currently unused, `base.py:130`).
  - Circuit breaker per provider (half-open probing).
  - Cancellation: a `CancellationToken` passed to every provider call. Streaming loops check it, and HTTP streams are closed on cancel. Replace LM Studio's private `_cancel_event` kwarg (`lmstudio_provider.py:185-210`).
  - Codex provider (`chatgpt_codex_provider.py`):
    - one conversation turn per request, using a pool of Codex processes or per-session instances (size configurable);
    - cancellation terminates only the turn belonging to the cancelled job (`generation_jobs.py:240-252`, `chatgpt_codex_provider.py:1172-1186`);
    - the provider no longer holds a lock across an entire streamed turn shared by all requests.
  - Replace the 35 direct `requests.*` calls in `src/app` with provider or service clients. Remove `requests` from the gateway lock when unused.
- **Tests:**
  - concurrency test: two sessions on different providers stream simultaneously, and neither provider is closed mid-stream;
  - retry on 503 then success;
  - circuit opens after N failures;
  - cancel stops the stream within 200 ms (FakeHTTP server);
  - Codex cancel affects only its job (fake Codex process).
- **Acceptance:** metric `direct_requests_calls` = 0; `pooled_http_clients` covers every HTTP provider.

#### WP-7.3 — Media streaming end to end

- **Addresses:** PERF7, R14.
- **Depends on:** WP-5.8, WP-7.2.
- **Steps:**
  1. TTS service: a streaming endpoint (HTTP chunked `audio/L16` or WebSocket binary frames) emitting PCM chunks as they are synthesized, not a buffered WAV. The gateway facade (`qwen_http_gateway.py:54-74`) forwards chunks without buffering.
  2. STT live WebSocket: binary audio frames instead of base64 JSON (`nemotron_eou_live_websocket.py:425`). Keep JSON for control messages.
  3. `tts_http_client.py`: no base64 re-encoding (`:203-221`).
  4. Fix the voice-clone client/server contract mismatch: multipart vs JSON (`tts_http_client.py:296-301` vs `tts_server.py:591-592`). Choose multipart for uploads and update the server.
  5. `/v1/realtime` stub (`live_speech/realtime.py`): remove it from production registration (the feature is disabled by default) until it is implemented. Remove the fake TTS fallback (`tts_adapters.py:34-46`).
- **Measurements:** first-audio latency before and after (the existing live qualification harness, if runnable; otherwise a fake-TTS latency harness); peak memory for a 10-minute synthesis.
- **Acceptance:** no base64 audio in gateway ↔ model-service transport except documented control payloads; measurements recorded.

#### WP-7.4 — Agent runtime event volume and queries

- **Addresses:** PERF6, AR3.
- **Depends on:** WP-6.5, WP-5.3.
- **Steps:**
  1. Stop persisting `message_update` token deltas (`pi_runtime_core.py:388-403,939-957`). Persist the final message, plus sampled progress events at most every 1 s. Live token streaming to the UI goes over SSE from memory, not the database.
  2. Per-run sequencing without locking the run row: a `sequence` column from a per-run counter row updated with `UPDATE … RETURNING`, or an identity plus ordering by `(created_at, id)`. Remove `MAX(sequence)+1` under `FOR UPDATE` (`repository.py:500-545`).
  3. Replace the 11 calls of `list_events(after_sequence=0, limit=5000)` with typed, indexed queries or projections: acceptance evidence, tool-result records, validation records, the promotion marker, reviewer text.
  4. Cache the capability registry and MCP policy (invalidated on file or configuration change) instead of rebuilding them about 10 times per broker call (`capabilities.py:245-246`).
- **Tests:** a long run with 20,000 events still validates acceptance correctly (the regression the 5,000-event window would fail).
- **Acceptance:** tests pass; events-per-run volume reduced (measured).

#### WP-7.5 — Trading compute and data paths

- **Addresses:** TR3, TR9, PERF6.
- **Depends on:** WP-6.3, WP-3.4.
- **Steps:**
  1. Strategy evaluation (CPU-bound Decimal math) runs in a process pool (the scheduler's `executor="process"`), with candidates processed in parallel up to a limit.
  2. The execution-observation fan-out uses a bounded executor, not the default one (`execution_observation_monitor.py:156-161`).
  3. Indicators: incremental computation per new bar (keep state), or vectorize with numpy (already a dependency). Stop recomputing whole sessions every bar.
  4. Event-store reads (20k–50k per cycle) are replaced with projection tables maintained by outbox consumers (qualification state, latest risk decision per attempt, open attempts).
  5. Bound the in-memory maps (TR9).
- **Measurements:** strategy cycle duration and CPU with 50 and 200 symbols, before and after.
- **Acceptance:** cycle p95 within the monitor interval at 200 symbols (record the target in the PR).

#### WP-7.6 — Query optimization pass with populated data

- **Addresses:** DATA3, DATA5.
- **Depends on:** WP-5.5–5.7.
- **Steps:**
  1. Seed a disposable database with 100k assets, 100k jobs (with events), 10k chat sessions with 1M messages, 1k RPG campaigns, 50k agent events and 1M trading events (a generator script under `scripts/seed_benchmark_data.py`).
  2. Enable `pg_stat_statements`, run the soak, and review the top 30 queries by total time with `EXPLAIN (ANALYZE, BUFFERS)`. Add or adjust indexes (via migrations).
  3. Record before/after in `docs/measurements/query-pass-<date>.md`.
- **Acceptance:** all list endpoints p95 < 100 ms at these volumes.

#### WP-7.7 — Import time and cold start

- **Addresses:** X2 (boot cost).
- **Depends on:** WP-2.2, WP-3.3d.
- **Steps:**
  1. Measure `python -X importtime -c "import app.production"` and time to ready.
  2. Only enabled features are imported. Feature packages avoid heavy imports at module level (torch, pandas and friends are imported inside functions or services).
  3. Target: cold start to ready < 8 s with all features on the reference machine; < 4 s with RPG and trading disabled. Record both.
- **Acceptance:** measurement recorded; the metric `boot_imported_modules` is ratcheted.

#### WP-7.8 — Frontend performance

Covered in WP-9.9. It is listed here for completeness.

---

### Phase 8 — Domain restructuring

#### WP-8.1 — Persistence and jobs subsystem wrap-up

- **Addresses:** PJ5, PJ6.
- **Depends on:** WP-2.6, WP-5.x.
- **Steps:**
  1. Remaining compat adapters: for each entry in `compatibility-inventory.json`, rename by responsibility (drop the `_compat` suffix where the adapter is a stable implementation), or delete it if it is a migration shim whose consumers are gone.
  2. `asset_compat` must preserve provenance (`source_job_id`, owner) and make updates atomic (one transaction).
- **Acceptance:** the compat inventory has only category A (stable adapters, renamed) or is empty; the architecture gate for compatibility growth is updated.

#### WP-8.2 — Agent runtime decomposition and declarative extensibility

- **Addresses:** AR1, AR4, AR5, AR6.
- **Depends on:** WP-3.6, WP-4.5, WP-6.5.
- **Design** — split `AgentRunService` (4,556 lines, 73 methods) into injected services behind ports:

  | Service | Responsibility |
  |---|---|
  | `RunLifecycleService` | create, start, stop, complete, state transitions, leases |
  | `RunSteeringService` | commands, steering, semantic task updates |
  | `WorkspaceService` | worktrees, dependency install, diff capture, candidate state |
  | `PromotionService` | wraps the existing `workspace_promotion.py` |
  | `GitHubBindingService` | repository binding, PR operations |
  | `SupervisionService` | supervisors, recovery, heartbeats |
  | `QualityStateMachine` | coding quality, review orchestration, quality recovery |
  | `ChildRunService` | subagents; one `start_child` implementation |

  Plus:
  - All SQL moves into repositories: `service_core` 10, `planning_api` 4, `budget` 3, and `workflow_runtime`'s 51 statements into a new `WorkflowRepository`.
  - `chat_bridge.py` becomes a lane router plus one handler module per lane. `route_typed_chat_turn` (735 lines) is split. Intent detection is consolidated into the semantic classifier; remove the duplicated regex logic in `profiles` and `router`.
- **Declarative extensibility:**
  - Capabilities are declared as data (`resources/config/capabilities/*.yaml`, or Python dataclass lists per integration package) with a schema: id, namespace, zone, effect, risk, scope type, approval policy, network and credential requirements, visibility, input/output schema, adapter id.
  - Adapters register in the fail-closed adapter registry (WP-4.5) by adapter id.
  - Profiles are declared as data (ceiling capability sets, selector rules). Remove the 50 hard-coded `"coding"` checks in favour of profile attributes (e.g. `profile.requires_workspace`, `profile.quality_gates`).
  - Adding a capability means one declaration plus one adapter registration. Write the recipe in `docs/architecture/AGENT_EXTENSION_GUIDE.md`, with a test that adds a fake capability via the recipe.
- **Package cleanup:**
  - `assist_core`: move the 37 `hermes_rpg_*` modules into `app/rpg/hermes/`; move the other `hermes_*` into `app/hermes/`; delete the 7 never-imported modules (Appendix G); merge micro-modules by responsibility; delete `assist_core` when empty.
  - `assistant_context`: its routes belong to FeatureModules (done in 3.2/2.2). What remains is the context service, merged into `app/conversation` or `app/assistant_tools` as appropriate.
  - Catalog drift: implement `gmail.send_email` or remove it from the personal-assistant profile (`gmail_adapter.py:185-193`). Missing credentials report `connection_status="missing_credentials"` instead of silently using a fake adapter (`gmail_adapter.py:134-141`).
  - Default budgets include token and cost caps (`contracts.py:587-594`), configurable. Cost caps work with paid providers by recording price metadata from `ProviderSpec`.
- **Acceptance:** no class over 800 lines in `app/agent_runtime`; no function over 150 lines; extension recipe test passes; all 127 agent-runtime test files pass.

#### WP-8.3 — Trading: strategy plugin contract, OrderGateway, data authority, providers

- **Addresses:** TR2, TR4, TR5, TR6, TR7, TR8, TR9.
- **Depends on:** WP-3.4, WP-6.3, WP-7.5.
- **Design and steps:**
  1. **Strategy contract** (`app/trading/strategies/contract.py`):

     ```python
     class Strategy(Protocol):
         kind: str                         # e.g. "gap_pullback_v1"
         version: str
         config_model: type[BaseModel]
         data_requirements: DataRequirements   # instruments, intervals, lookback, providers
         def evaluate(self, ctx: StrategyContext) -> list[Proposal]: ...   # pure, deterministic
     ```

     - A `StrategyRegistry` is populated by explicit registration.
     - The persisted `strategy_kind` becomes a string validated against the registry, replacing the `Literal` and union types and the if/else mapper (`strategy_repository.py:30,34,113-117`). A migration drops any CHECK constraint on the kind only if one exists (expand/contract).
     - Monitors become one generic `StrategyRunner` scheduled task per enabled strategy configuration.
     - Bespoke monitors (AI shadow v1/v2/v3, deep recovery, prospective gap/economic, Solana, interday discovery) become either strategies or research tasks on the shared scheduler with a common base (start/stop/loop removed).
     - Recipe doc plus test: add a fake strategy by one module and one registration line.
  2. **OrderGateway** (`app/trading/execution/order_gateway.py`) — the only path to `paper_repository.place_order`. It enforces, in one transaction:
     - account enabled;
     - global and per-account kill switches (new table `omnix_trading_kill_switches`, DB-backed, changeable at runtime with the `trading:control` permission and audited);
     - per-strategy kill switch;
     - entry window;
     - qualification;
     - profile match;
     - risk policy (position and notional limits, daily loss);
     - authorization bound to the order's **own** trade attempt, not the latest decision for the instrument;
     - long-only: a sell with no or insufficient position is rejected unless shorting is explicitly enabled per account (`paper_repository.py:246,586-593`);
     - idempotency.

     Atomic replace means cancel plus place in one transaction (`paper_api.py:444-459`). `_AuthorizedStrategyPaperRepository` logic moves here. Repository methods become private to the gateway module (lint rule). Manual routes (`paper_api.py:220-302,372-393`) also go through the gateway.
  3. **Data authority:** move decision inputs from local JSON into PostgreSQL tables (expand migrations):
     - Yahoo 1-minute evidence (`yahoo_evidence.py`);
     - IBKR promotion evidence (`ibkr_evidence.py`);
     - disk caches (`service.py:69-72`, `cache.py`) → a PostgreSQL cache table or bounded in-memory cache — decision data must be in PostgreSQL;
     - the climatology file → configured absolute path or database seed data.

     Dedupe evidence revisions by content hash, excluding `received_at` from revision identity (`yahoo_evidence.py:358-370,403-409`; `providers/equity.py:241,269-270`). Remove the `gh api` runtime fetch of the premarket handoff (`prospective_gap_runtime.py:544-598`); replace it with an explicit import job with provenance, disabled by default. Remove the committed `resources/trading/activity_log/*` runtime logs from git (human gate for history), and add them to `.gitignore`.
  4. **Providers:**
     - a real adapter interface (bars, quotes, stream subscribe, calendar, rate limits);
     - a proactive per-provider request budget (token bucket; Binance request weights);
     - **priority lanes**: protective exits have a reserved budget and a separate circuit breaker from research polling;
     - a shared upstream stream per instrument with fan-out to browser clients and reconnect with gap recovery (use `streaming/gap_recovery.py`, currently test-only);
     - the IBKR tick path records to an in-memory ring plus batched database writes, never file read-modify-write on the network thread (`ibkr_market_data_monitor.py:163-248`);
     - `wait_for_quote` uses an event, not a 20 ms busy poll;
     - client id configurable.
  5. **Lock protection:** background mutations carry the lease epoch (fencing token). Remove the per-acquisition `SELECT 1` serialization (`background_runtime.py:99-102`), replacing it with fencing checks in writes.
  6. **AI influence:**
     - the intraday LLM call moves out of the proposal path (asynchronous research annotation; proposals never wait on an LLM);
     - research features may not change entry scores unless the strategy configuration explicitly opts in, and that opt-in is audited and visible;
     - correct `OMNIX_TRADING_OPERATIONS.md:172` to match reality.
  7. **Hygiene:**
     - one Eastern-time zone definition (`app/trading/time.py`), replacing 77 definitions;
     - session close from the calendar (38 hard-coded `time(16,0)`);
     - AI shadow version retirement: propose default-off for superseded versions in PROGRESS.md (human gate).
  8. **Frontend:** a single trading API client using generated types, replacing 10 copies of `requestJson` and 88 hard-coded paths. Done with WP-9.3.
- **Acceptance:** strategy recipe test passes; OrderGateway tests (kill switches, long-only, attempt-bound authorization, atomic replace, idempotency) pass; no trading decision input is read from local files (test with a read-only filesystem fixture); trading characterization still matches (or differences are approved and documented).

#### WP-8.4 — Providers, prompts and model services

- **Addresses:** PR3–PR6.
- **Depends on:** WP-7.2, WP-7.3.
- **Steps:**
  1. **Prompt registry:** expand `app/prompts` into a registry of versioned templates (`id`, `version`, `template`, `variables_schema`, `output_contract` optional). Move the 117 inline prompt strings (71 files) into feature-local template modules registered with the registry. Prompt changes are reviewed via golden tests.
  2. **Structured outputs:** every LLM call that expects structure uses the structured contracts gateway (`providers/structured/`). Replace ad hoc parsing (e.g. `audiobook/annotation.py:183-210`).
  3. **Model services:**
     - auth (WP-0.5);
     - loopback (WP-0.2);
     - offload (WP-7.1);
     - streaming (WP-7.3);
     - size limits;
     - no tracebacks;
     - health endpoints that report model residency without blocking.
  4. `src/openai_api.py`: either implement it on top of `ProviderService` with auth, or remove it and its docs, since chat and transcription are placeholders. **Choose removal** unless a caller exists (search the scripts and docs); log it in DECISIONS.md.
  5. llama.cpp provider process management: explicit start/stop only when `auto_start` is true; drain stdout; bind loopback; no killing (WP-4.10).
  6. Delete unused `providers/tts_abstraction.py` (Appendix G).
- **Acceptance:** metric `inline_prompt_strings` ≤ 10 (documented); model service tests pass.

#### WP-8.5 — Chat, memory and characters

- **Addresses:** CM2, CM3.
- **Depends on:** WP-2.9, WP-3.1, WP-6.1.
- **Steps:**
  1. Chat SSE route (`core_chat_routes.py:185-242`): goes through admission, idempotency, ownership and interruption, the same as the job path. Generation runs on a bounded executor, not a thread per generation with 100 ms polling (`generation_jobs.py:564-603`). Cancellation propagates to the provider via `CancellationToken`.
  2. Memory v2 cutover:
     - follow `docs/MEMORY_V2_*.md`;
     - add a shadow-comparison report (existing shadow tables);
     - the authority flip is a human gate;
     - after the flip and a soak period recorded in PROGRESS.md, delete v1 (6.7K lines) and its compat adapters;
     - until then, v1 and v2 share contracts via `app/conversation`.
  3. Characters: move the 19 deployment-rehearsal harness files (5.1K lines) out of `app/characters` into `scripts/rehearsal/` or `src/tests/rehearsal/`. Characters depends on memory only through contracts.
- **Acceptance:** the SSE and job paths share the admission code (test: duplicate submission via SSE returns the existing job); v1 deletion completed or explicitly blocked with a human decision recorded.

#### WP-8.6 — RPG: contracts, dead code, LLM fan-out, packaging as a plugin

- **Addresses:** RPG5–RPG8, X5, X6.
- **Depends on:** WP-3.3, WP-5.6, WP-2.5.
- **Steps:**
  1. **Dead code** (Appendix G):
     - build `scripts/reachability_report.py` (see the review's method; roots: `app.production`, the worker entrypoints, the feature catalog; include lazy, relative and star imports and `import_module` strings) that outputs unreachable modules per package;
     - delete unreachable RPG modules (≈526 modules, ≈108K lines), including `rpg/api` (duplicate), `story`, `cognitive`, `progression`, `quest`, `quests` if confirmed unreachable;
     - move test-only harnesses (58 modules) to `src/tests/rpg/support/`;
     - resolve the 7 same-name shadowed files;
     - replace file-path loading.
     - The Hermes approved flow (`hermes_rpg_canonical_submitter.py`) must submit through the real turn pipeline, not the old `rpg/pipeline.py` with its in-memory `_game_store`.
  2. **Typed contracts:**
     - Pydantic models for the turn request and response, state views (player, party, location, combat, inventory, journal, objectives), world library and authoring payloads;
     - all 112 gateway RPG routes in the schema (done per WP-2.2);
     - replace `Dict[str, Any]` plumbing at module boundaries (metric `rpg_dict_any` ratcheted; target: boundaries typed; internal dicts allowed within a module);
     - replace the 513 `_safe_dict` copies with one utility.
  3. **Platform tables:** no raw SQL on `omnix_jobs` (WP-2.5). RPG repositories live in `app/rpg/persistence` (WP-2.6).
  4. **LLM fan-out:**
     - advisories off by default or batched into a single call (`state_normalization.py:215-218`, `runtime_part15.py:124-167` successors);
     - shadow writer off by default (WP-7.1);
     - cache narrative outputs by (state hash, action, prompt version) for replay and retries;
     - per-call timeout aligned with the turn SLO.
  5. **Packaging:** RPG is an optional FeatureModule and can be disabled (the matrix test proves it). Optional follow-up (not required for 9/10): move the package to `src/packages/omnix_rpg/` as a separate distribution. Record the decision in DECISIONS.md.
  6. **Test suite:** a separate RPG test job with path filters for speed, plus inclusion in the full nightly.
- **Acceptance:**
  - unreachable RPG modules = 0 (report);
  - RPG file and function size limits met;
  - turn LLM calls ≤ 2 sequential by default (measured with a fake provider counter);
  - deterministic replay test passes;
  - RPG disabled → app boots.

#### WP-8.7 — Audiobook: polish the reference feature

- **Addresses:** makes the reference template exemplary.
- **Depends on:** WP-2.2, WP-6.2.
- **Steps:**
  1. Move ~154 lines of raw SQL from `audiobook/service.py` into a repository.
  2. Shorten leases from 1 hour, with renewal.
  3. Routes as module-level router functions (no closures).
  4. Remove the legacy hook (`routes.py:862-874`).
  5. Depend on the TTS port, not the concrete provider (`model_identity.py:23`).
  6. Streamed uploads (`routes.py:349`).
  7. Update `FEATURE_MODULE_GUIDE.md` with the final template.
- **Acceptance:** the guide's checklist is fully satisfied by audiobook.

#### WP-8.8 — Image feature

- **Addresses:** PR (M5), R4.
- **Depends on:** WP-5.8, WP-6.2.
- **Steps:**
  1. Remove the thread-per-job plus progress-poller-thread path (`image_inline.py:54-61,447-452`); durable worker only.
  2. Residency via device permits.
  3. Bound the image service progress map.
  4. Assets via the blob protocol.
- **Acceptance:** image job tests pass under the durable worker only.

---

### Phase 9 — Frontend architecture

All paths in this phase are relative to `src/apps/web/src/`.

#### WP-9.1 — Module runtime lifecycle (activate/dispose)

- **Addresses:** FE1, R8.
- **Depends on:** WP-1.7.
- **Design:**

  ```ts
  export interface ModuleRuntime {
    activate(ctx: ModuleRuntimeContext): Disposable | Promise<Disposable>;
  }
  export interface Disposable { dispose(): void }
  ```

  - `app/viewRuntime.ts` keeps a map of active disposables per module.
  - The router effect (`app/router.tsx:82-85`) activates the entering module and disposes the leaving one, so the effect returns a cleanup.
  - Each of the 47 initializers returns a `Disposable`, and the 9 side-effect imports become explicit `activate` functions.
  - `ModuleRuntimeContext` provides the query client, API client, event client and a typed service registry (replacing `window.__omnix*` flags).
  - **Unsafe cleanup pattern to fix:** current cleanups restore a `fetch` reference captured at install time (`features/chatbot/live-chat-workspace.tsx:108`). Transport concerns move to middleware (WP-9.2) *before* enabling disposal for fetch-wrapping runtimes.
- **Tests:** a navigation test (Vitest + jsdom): mount the app, navigate Chat → Trading → Chat three times, and assert that the counts of active listeners (instrument `addEventListener`/`removeEventListener`), intervals, observers and fetch wrappers are equal after each cycle.
- **Acceptance:** test passes; R8 closed.

#### WP-9.2 — Transport middleware in one API client

- **Addresses:** FE1.
- **Depends on:** WP-9.1 (partial), WP-4.1 (CSRF header).
- **Design:**
  - `api/client.ts` (and the new typed client from 9.3) exposes `use(middleware)`, where a middleware is `(req, next) => Promise<Response>`.
  - Built-in middlewares: CSRF and client header, firewall scope (from `app/viewApiScope.ts`; becomes middleware instead of a fetch wrapper), request-id propagation, diagnostics timing, retry for idempotent GETs, 401 → login redirect.
  - Convert the 15 live feature fetch wrappers into:
    - middleware scoped to a module (registered on activate, removed on dispose), or
    - explicit calls in feature code.

    Specifically, `features/assistant-workspace/assistant-context-controller.ts:114-119,229-244`, which rewrites chat POSTs to `/api/assistant/context/chat/…`, becomes an explicit client method used by the chat feature. `live-chat-submission-gateway.ts:163-186`, which swaps fetch temporarily, becomes an explicit call.
  - Delete the client method replacements: `features/voice/voiceJobListGuard.ts` (use a dedicated `listVoiceJobSummaries` method) and `features/podcast/podcastSessionGuard.ts` (explicit podcast session creation).
  - Remove all 55 `window.__omnix*` flags in favour of the service registry or module state.
  - Keep `installViewApiFirewall` only as a thin global safety net for any remaining raw `fetch`, then delete it when raw fetch = 0.
- **Acceptance:** ESLint `window.fetch` assignment violations = 0; client method replacement = 0; `__omnix` flags = 0.

#### WP-9.3 — Typed API client from OpenAPI

- **Addresses:** FE3, X5, R12.
- **Depends on:** WP-2.2 (backend routes in the schema), WP-9.2.
- **Design:**
  - Use `openapi-fetch` with the generated `paths` type (`api/generated/types.ts`): `const api = createClient<paths>({ baseUrl: '' })` with the middleware from 9.2. Paths, parameters, bodies and responses are type-checked.
  - Replace the handwritten types in `api/client.ts:36-191`, `features/audiobook/AudiobookWorkspace.tsx:6-240` and every other payload type (272) with generated types. Keep view-model types separate and derived from generated types.
  - The 24 local `request`/`requestJson` helpers are deleted; the 76 raw `fetch(` calls outside `api/` move to the typed client.
  - Runtime validation at stream boundaries: SSE event payloads, WebSocket messages, and job `output_refs` are validated with Zod schemas (in `api/schemas/`). Generate them from OpenAPI where feasible, or handwrite them next to the event type definitions, with a test that they match the OpenAPI component schemas.
  - Remove the fabricated `JobRecord` (`api/client.ts:889-966`).
  - Transport exceptions (WebSocket/SSE) are documented in `docs/architecture/api-transport-exceptions.md` with their message schemas.
- **Acceptance:** metrics `web_handwritten_api_types` = 0 for schema routes, `web_raw_fetch_outside_api` = 0, and UI-called paths present in OpenAPI = 100% (excluding documented transport exceptions); `api:check` in CI.

#### WP-9.4 — React owns the DOM

- **Addresses:** FE2.
- **Depends on:** WP-9.1.
- **Steps:**
  1. Rebuild injected UI as React components subscribed to stores:
     - `features/chatbot/researchProgressController.ts:553-598` (injected `<article>` nodes) → a `ResearchProgressCard` rendered in the transcript list from store state;
     - `features/chatbot/chat-sidebar-manager.ts` → a React sidebar;
     - `features/storyteller/story-audio-enhancer.ts` and `story-extra-mount.ts` → components in `StorytellerWorkspace`, removing the extra `createRoot` islands (4 total);
     - storyteller panels that scrape `innerText` and poll every 1–1.5 s (`StoryAudioPanel.tsx:330-342`, `StoryCastPanel.tsx:11-29`) → consume the shared story store.
  2. Remove the DOM reads in `ChatbotWorkspace.tsx:673` (`select[aria-label=…]`), `:1288` (deleting injected rows) and `:175-179` (window flags).
  3. Remove the document-wide `MutationObserver`s (at least 12 with `subtree:true`).
- **Acceptance:** metrics: web MutationObserver files ≤ 2 (justified, e.g. a Live2D canvas); DOM injection calls outside React ≤ 5 justified; `createRoot` calls = 1.

#### WP-9.5 — Component decomposition

- **Addresses:** FE5.
- **Depends on:** WP-9.3, WP-9.4.
- **Steps:**
  1. For `ChatbotWorkspace` (2,039-line function), `TradingChartPanel` (1,740), `AudiobookWorkspace` (1,353), `StorytellerWorkspace` and `live-voice-controller.ts`, extract:
     - query hooks (`useChatSessions`, `useChatMessages` …);
     - command hooks (`useSendMessage` …);
     - a feature store (`useSyncExternalStore` or Zustand);
     - presentational components.
  2. Targets: component files ≤ 400 lines, functions ≤ 150 lines; ESLint `max-lines-per-function` warns at 150, errors at 250, with baseline disables tracked.
  3. `watch('content')` at the top of Chat (`ChatbotWorkspace.tsx:420`) moves into the composer component. Message markdown rendering is memoized per message (`React.memo` + `useMemo` keyed by content).
- **Acceptance:** size targets met; Chat keystrokes do not re-render the transcript (React Profiler-based test or render-count test).

#### WP-9.6 — State and events

- **Addresses:** FE8, PERF5 (web side).
- **Depends on:** WP-9.1, WP-5.4.
- **Steps:**
  1. A typed event bus (`events/bus.ts`) with a central event map type replaces window `CustomEvent`s (61 files, 67 names, duplicates such as `'omnix:assistant-voice-perf'` in 29 files).
  2. All features use the shared SSE client (`events/eventClient.ts`) with query invalidation hooks, following `features/platform/PlatformModuleWorkspace.tsx:500-517`. Replace `setInterval` polling (28 files) and `refetchInterval` (48) wherever a server event exists. Keep polling only for resources without events, with documented intervals.
  3. Workspace state that should be deep-linkable (selected session, campaign, instrument, project) moves from localStorage (109 calls) to route search parameters (TanStack Router). localStorage keeps only preferences.
- **Acceptance:** CustomEvent dispatch sites = 0; setInterval files ≤ 5 (justified).

#### WP-9.7 — Feature boundaries and single-source module registration

- **Addresses:** FE7.
- **Depends on:** WP-1.7.
- **Steps:**
  1. Each feature exposes `features/<name>/index.ts` (its public API) and `features/<name>/module.ts` (a manifest: id, route, lazy component, runtime, API prefixes, nav icon, CSS entry).
  2. `app/modules.ts`, `app/router.tsx`, `features/ModuleWorkspace.tsx`, `app/viewApiScope.ts` (`ROUTE_MODULES`, `MODULE_API_PREFIXES`) and `design/primitives.tsx` (icons) all derive from the manifest list. Adding a module = one manifest plus one line in the manifest registry.
  3. Remove the silent fallback to `chatbot` in `viewApiScope.ts:65`: an unknown route → a 404 view.
  4. Break chatbot ↔ assistant-workspace (21/13 edges): merge them into one feature, or define explicit interfaces. **Decision:** merge them into `features/assistant` with sub-folders, since they are one product surface. `settings` must not import `storyteller`. `shared` becomes a real kernel (UI primitives, hooks, formatting); move widely used utilities there.
  5. ESLint `no-restricted-imports` enforces the boundaries (WP-1.7 rules, now without baseline).
- **Acceptance:** add-a-module recipe test (a scaffolded fake module appears in nav and routes with one registration line); feature cycle count = 0.

#### WP-9.8 — CSS architecture

- **Addresses:** FE6.
- **Depends on:** WP-9.7.
- **Design:**
  - Cascade layers declared once in `styles.css`: `@layer reset, tokens, base, mantine, components, features, themes, overrides;`.
  - Design tokens (CSS custom properties) in `design/tokens.css`: color, spacing, radius, typography, elevation, motion. Map them to the Mantine theme (`design/theme.ts`, whose palette is currently unused), or remove Mantine where it is barely used (30 files). **Decision:** keep Mantine for form primitives and map tokens into its theme.
  - Themes (`liquid-glass-theme.css`, `theme-presets.css`, `appearance-overrides.css`, `TradingLightTheme.css`) set **tokens only**, via `[data-theme=…]` selectors. They stop targeting feature class names (221 targeted today).
  - Feature CSS migrates to CSS Modules (`*.module.css`) per component, loaded with the feature (lazy), not from `main.tsx` (24 eager imports at `main.tsx:12-35`).
  - Fold `*Fix.css` files into their owners, and fold `legacy-layout.css` into components or delete it.
- **Metrics:** `web_important` ≤ 50; `web_hardcoded_colors` ≤ 300 (from 6,675); `web_global_css_files` ≤ 10.
- **Acceptance:** metrics met; a visual regression check (Playwright screenshots of each workspace in dark and light themes) passes against approved baselines, captured before migration; differences must be reviewed and approved by a human (gate).

#### WP-9.9 — Resilience, accessibility and rendering performance

- **Addresses:** FE4, PERF8.
- **Depends on:** WP-9.5.
- **Steps:**
  1. Error boundaries per route plus a TanStack Router `errorComponent` with retry. Chunk-load failures retry once and then offer a reload.
  2. Global `error`/`unhandledrejection` handlers send client error reports to `/api/client-errors` (new endpoint; rate-limited; no PII; with request id).
  3. List virtualization (`@tanstack/react-virtual`) for chat transcripts, job lists, asset galleries, RPG journal and trading tables. Remove the conflicting `content-visibility` rules (`legacy-layout.css:523` vs `ChatbotWorkspaceScroll.css:13-16`).
  4. Remove the 1 s clock re-render in `TradingChartPanel.tsx:433,772`: an isolated clock component.
  5. Lazy-load `pixi.js` and Live2D only when an avatar is visible. Today `characterClient.ts:3` imports them statically.
  6. Audio worklets become real module files loaded via Vite worker URLs and type-checked (`live-voice-pcm-session.ts:1002` builds them from strings). CSP no longer needs `blob:` for scripts.
  7. Accessibility:
     - remove the hidden "Episode request" `<h3>` and fixed `aria-labelledby="module-title"` in `design/primitives.tsx:70`;
     - run `@axe-core/playwright` on each workspace in e2e (add the dependency: approved as a dev dependency here) with 0 critical violations.
  8. Platform lists fetched unbounded (`PlatformModuleWorkspace.tsx:170-173,232-235`) use cursor pagination (WP-5.5).
- **Acceptance:** error-boundary test (a throwing component shows fallback, not a blank app); the axe e2e passes; a transcript with 5,000 messages scrolls smoothly (render count bounded in test).

#### WP-9.10 — Frontend dead code and test estate

- **Addresses:** FE9, X6.
- **Depends on:** WP-9.7.
- **Steps:**
  1. Delete the 92 unreachable modules and their 72 tests (Appendix G), including the dead duplicate `ImageGenerationWorkspaceImpl.tsx`.
  2. Shared test utilities: `test/renderWithProviders.tsx` (theme, query client, router, API client mock) replaces the 13 copies of `renderWithTheme` and the 65 ad hoc `QueryClient`s.
  3. Tests for thin features:
     - storyteller: ≥ 10 meaningful tests;
     - audiobook: ≥ 10;
     - podcast: ≥ 5;
     - live-speech: ≥ 5;
     - conversation-production: ≥ 3.
  4. Playwright app-shell spec runs in CI (WP-1.5). Add one e2e per workspace: open, primary action with mocked backend, error state.
- **Acceptance:** metrics `web_unreachable_modules` = 0; every feature has tests; e2e per workspace green.

---

### Phase 10 — Observability and operations

WP-10.1 and WP-10.2 may start right after WP-1.5.

#### WP-10.1 — Structured logging

- **Addresses:** OPS1.
- **Depends on:** WP-1.5.
- **Design:**
  - `app/observability/logging.py` provides `configure_logging(config)`:
    - stdlib `logging` with a JSON formatter (`OMNIX_LOG_FORMAT=json|text`, default text locally, json in containers);
    - level per logger from configuration;
    - rotation through the existing `resilient_rotating_file_handler.py` for file sinks;
    - one sink configuration.
  - Context injection via a `logging.Filter` reading contextvars: `request_id`, `job_id`, `attempt`, `run_id`, `workspace_id`, `user_id` (hashed), `feature`.
  - Replace all 198 `print()` calls in `src/app` (AL008 → 0) and the 8 ad hoc file sinks (`voice_debug.py:66`, `trade_logging.py:96-101` — which must not be a `RotatingFileHandler` shared across processes: use one file per process or stdout — and `app/logging.py:9-13`).
  - Content-free policy: remove the unsalted SHA-256 text fingerprints in `voice_debug.py:83-85`. Agent debug logs stay opt-in; remove the force-enable in `start_all.bat:67-68`.
- **Acceptance:** AL008 = 0; a log-capture test shows context ids on log lines emitted inside a request and inside a job.

#### WP-10.2 — Request and job correlation

- **Addresses:** OPS1, R15.
- **Depends on:** WP-10.1.
- **Steps:**
  1. Middleware accepts an inbound `X-Request-ID` (validated format) or generates one. It sets the contextvar and returns the header.
  2. Jobs store `correlation_id` (new column, expand migration) from the submitting request; workers set the contextvar from it.
  3. Provider and model-service calls forward `X-Request-ID`. SSE events include `correlation_id` where relevant.
  4. The web client (middleware) generates request ids and includes them in client error reports.
- **Acceptance:** a test traces one chat submission through admission → job → provider call (fake) → completion event, with the same id in every log line.

#### WP-10.3 — Metrics

- **Addresses:** OPS1.
- **Depends on:** WP-10.1.
- **Design:**
  - `prometheus-client` registry in `app/observability/metrics.py`.
  - `/metrics` served on a private listener (`OMNIX_METRICS_PORT`, loopback by default), or on the main app requiring `admin:metrics`.
  - Catalog documented in `docs/operations/METRICS.md`:

    | Area | Metrics |
    |---|---|
    | HTTP | requests, errors, latency histogram by route template |
    | Runtime | event-loop lag histogram |
    | Database | pool size, in use, wait-time histogram, statement duration by repository method (sampled) |
    | Jobs | queue depth and oldest age by type/status; claims; lease expirations; retries; dead letters; execution duration by type |
    | Providers | call latency, errors, circuit state, retries by provider |
    | Speech | TTS first-audio latency; live calls active; STT latency |
    | Events and outbox | SSE subscribers, events delivered, resyncs; outbox lag and publish rate |
    | Maintenance | retention rows deleted, run duration; scheduler task duration, failures, lag |
    | Capacity | device permits held and waiting by class |
    | Security | auth failures, rate-limit rejections |

  - Replace the three in-process counters in `platform/runtime_diagnostics.py` with this registry. Diagnostics reads from it.
- **Acceptance:** a metrics endpoint test asserts the catalog names exist; label cardinality bounded (route templates, not raw paths).

#### WP-10.4 — Tracing (optional, off by default)

- **Addresses:** OPS1.
- **Depends on:** WP-10.2.
- **Design:**
  - OpenTelemetry as an optional extra; enabled by `OMNIX_OTEL_ENABLED=true` plus the standard `OTEL_EXPORTER_OTLP_*` variables.
  - Instrument FastAPI, psycopg and httpx.
  - Manual spans: job execution, RPG turn stages (reuse the existing trace spans in `gateway/rpg_turn_pipeline.py:48-392`), live-voice pipeline stages, agent run steps.
  - The trace id is added to log context.
  - Compose `observability` profile: OTel collector plus Jaeger or Tempo (documentation only; not required in CI).
- **Acceptance:** with tracing enabled in a test using an in-memory exporter, one request produces the expected span tree.

#### WP-10.5 — Error envelope and exception discipline

- **Addresses:** SEC7, OPS1.
- **Depends on:** WP-10.2.
- **Steps:**
  1. Global exception handlers return `application/problem+json`: `type`, `title`, `status`, `detail` (safe), `instance` (request path), `request_id`, plus a `code` for machine handling.
  2. `HTTPException` details become codes plus safe messages. Unhandled exceptions → 500 with a generic detail and the request id; the log has the stack trace.
  3. Replace silent broad excepts (AL009, 183 sites) with logged handling and metrics, or narrow the exception types. Target ≤ 10 documented exceptions.
- **Acceptance:** a test raises in a route and asserts no internals leak; AL009 ≤ 10 (with a documented allow-list).

#### WP-10.6 — SLOs, dashboards, alerts

- **Addresses:** the Observability 9/10 exit criterion.
- **Depends on:** WP-10.3, WP-6.8.
- **Steps:**
  1. `docs/operations/SLOS.md`. Initial SLOs are derived from WP-6.8 measurements; adjust after measuring:
     - API availability 99.5% (local) / 99.9% (hosted);
     - chat admission p95 < 50 ms;
     - first token p95 per provider class;
     - TTS first audio p95 < 1.5 s;
     - job queue age p95 < 30 s for interactive classes;
     - event delivery lag p95 < 1 s.
  2. Grafana dashboard JSON under `deploy/observability/dashboards/`.
  3. Prometheus alert rules under `deploy/observability/alerts.yml`.
- **Acceptance:** files exist and are validated (`promtool check rules` in CI, if available in the CI image; otherwise a YAML schema check).

#### WP-10.7 — Backup, restore and disaster recovery

- **Addresses:** Data and Ops 9/10.
- **Depends on:** WP-5.8.
- **Steps:**
  1. `scripts/backup_omnix.py` performs `pg_dump -Fc` plus blob-store snapshot (local: tar of the storage root; S3: bucket versioning documentation) with a manifest (checksums, schema version, timestamp).
  2. `scripts/restore_rehearsal.py` restores into a disposable database and storage, runs migrations status and readiness, and samples reads. It runs in the nightly workflow against a generated dataset.
  3. `docs/operations/BACKUP_RESTORE.md` documents RPO and RTO targets (e.g. RPO 24 h local, RTO 1 h).
  4. The backup from the 2026-09-26 rollout was never restore-tested. Request a human-run restore rehearsal on real data (human gate).
- **Acceptance:** the nightly restore rehearsal passes.

#### WP-10.8 — Runbooks

- **Depends on:** WP-10.3.
- **Steps:** `docs/operations/runbooks/`, one runbook each for:
  - worker ownership lost;
  - stuck jobs or queue growth;
  - PostgreSQL outage;
  - GPU saturation / permit starvation;
  - provider outage and circuit open;
  - auth outage (OIDC);
  - disk full / retention failing;
  - secret rotation (install credential, service token, run-token key, provider keys);
  - rolling upgrade and rollback;
  - restore.

  Each has symptoms, dashboards and metrics, diagnosis steps, remediation and verification.
- **Acceptance:** runbooks exist and are linked from `docs/OPERATIONS.md`.

#### WP-10.9 — Diagnostics consolidation

- **Depends on:** WP-10.3.
- **Steps:**
  1. One `/api/diagnostics` schema (typed) aggregating runtime, ownership, queues, permits, providers, event reader, outbox, retention, version and feature enablement.
  2. Content-free, and requiring the `admin:diagnostics` permission.
  3. Remove duplicate status endpoints, or make them views of it.
- **Acceptance:** schema documented; permission enforced.

---

### Phase 11 — Deployment and delivery

#### WP-11.1 — Container images

- **Addresses:** DEL3.
- **Depends on:** WP-1.3.
- **Steps:**
  1. `deploy/docker/gateway.Dockerfile`: multi-stage.
     - Builder: `python:3.11-slim` with build dependencies, `pip install --require-hashes -r requirements/gateway.lock.txt` into a venv.
     - Runtime: `python:3.11-slim`, copy the venv and `src/`, non-root user `omnix` (uid 10001), read-only root filesystem compatible, `HEALTHCHECK` on `/health`, `CMD` uvicorn `app.production:app`.
     - No CUDA, no models.
  2. `deploy/docker/web.Dockerfile`: Node build stage (`npm ci`, `npm run build`), then Nginx serving static files with the ingress config (WP-11.3).
  3. `deploy/docker/tts.Dockerfile`, `stt.Dockerfile`, `image.Dockerfile`:
     - `nvidia/cuda:12.4.x-runtime-ubuntu22.04` base (runtime, not devel) plus Python 3.11;
     - install from their lock files, with one torch version each;
     - models are downloaded at runtime into a mounted volume by an init command (`python -m app.models download <id>` with checksum verification);
     - non-root.
  4. Delete the root `Dockerfile`, or replace it with a pointer.
  5. CI `images.yml` (on tag and nightly): build images, run `trivy image` (fail on critical), generate an SBOM (`trivy image --format cyclonedx`), and smoke-test the gateway image against PostgreSQL.
- **Acceptance:** images build reproducibly; the gateway image is < 500 MB; trivy passes; containers run as non-root.

#### WP-11.2 — Compose profiles

- **Addresses:** DEL4.
- **Depends on:** WP-11.1, WP-2.4, WP-6.1, WP-6.3.
- **Steps:**
  1. Rewrite `docker-compose.yml` with profiles:
     - default: postgres, migrate (one-shot), gateway-worker (scheduler + singleton), api (replicas via `deploy.replicas` or named services), job-worker, web (Nginx);
     - `gpu`: tts, stt, image;
     - `storage`: minio;
     - `observability`: otel-collector, prometheus, grafana.
  2. No default passwords: `POSTGRES_PASSWORD` is required via an `.env` file (template `.env.example` without secrets). Compose fails if it is missing.
  3. Keep `docker-compose.postgres.yml` for developers who run only PostgreSQL. Fold `docker-compose.agent-tests.yml` into test profiles.
- **Acceptance:** `docker compose config` validates for each profile; the multihost test (WP-6.8) uses these images.

#### WP-11.3 — Ingress hardening

- **Addresses:** SEC3, DEL4, SCALE (affinity).
- **Depends on:** WP-4.1, WP-6.4.
- **Steps:**
  1. Update `deploy/nginx/omnix.conf`, generated by `scripts/render_gateway_ingress.py` from `deploy/gateway-route-policy.json`:
     - TLS server block (certificate paths configurable) with HTTP → HTTPS redirect;
     - security headers and CSP for the SPA;
     - `limit_req` zones for `/auth/*` and the API;
     - `client_max_body_size` aligned with upload limits;
     - WebSocket and SSE settings;
     - call-affinity consistent hashing for live-call routes (WP-6.4);
     - the `X-Omnix-Gateway-Affinity` header is honoured only for authenticated internal or ops use — strip it from external requests unless the policy allows it.
  2. OIDC deployments may put `oauth2-proxy` in front; this is documented as an alternative to in-app OIDC.
  3. Update [OMNIX_PRODUCTION_INGRESS.md](architecture/OMNIX_PRODUCTION_INGRESS.md).
- **Acceptance:** `nginx -t` in CI (containerized); the route policy test passes; the security headers test runs against the Nginx container.

#### WP-11.4 — Launcher and scripts

- **Addresses:** DEL4, DEL5.
- **Depends on:** WP-1.3, WP-2.4, WP-4.1.
- **Steps:**
  1. Remove hard-coded `C:\Users\unx47\…` (`start_all.bat:8-10`, `launcher/service_manager.py:452-454`, `setup.bat:10`).
  2. The launcher reads `resources/config/launcher.toml` (template committed, local file ignored) with environment paths, conda env names, ports and enabled services.
  3. The launcher runs `migrate` before the gateway (WP-2.4), starts job workers (WP-6.1), and performs the local auth login (WP-4.1).
  4. Repair `start_all.sh` for POSIX parity with the Windows launcher, or replace both with the Python launcher (`python -m app.launcher start`), keeping thin `.bat`/`.sh` wrappers. **Decision:** the Python launcher is the source of truth; the wrappers only call it.
  5. `setup.sh`/`setup.bat` install from locks, including psycopg, and set up PostgreSQL via compose.
  6. Delete dead scripts:
     - `src/app/llamacpp_installer.py` (installs unverified wheels from personal repos);
     - `src/temp_debug_presentation.py`;
     - the nonexistent imports in `src/__init__.py`.
  7. `generate_certs.py` takes hostnames and IPs as arguments (no hard-coded LAN IP).
- **Acceptance:** a clean Windows VM and a clean Linux VM can follow `docs/SETUP.md` to a ready system (human verification requested for Windows if no CI runner is available).

#### WP-11.5 — Release process

- **Addresses:** Delivery 9/10.
- **Depends on:** WP-11.1, WP-6.7.
- **Steps:**
  1. Semantic versioning in `pyproject.toml` and the web `package.json`, stamped into images (`OMNIX_SOFTWARE_REVISION`).
  2. `CHANGELOG.md` (Keep a Changelog format).
  3. `docs/operations/RELEASE.md` documents: release checklist (migrations reviewed for expand/contract, OpenAPI diff reviewed, security scan, restore rehearsal green), deployment order (migrate → workers → scheduler → APIs → web), rollback (redeploy previous images; contract migrations are never in the same release as the code that stops using the column).
- **Acceptance:** documents exist; the release workflow builds and tags images.

#### WP-11.6 — Repository hygiene

- **Addresses:** DEL5.
- **Depends on:** WP-0.1.
- **Steps:**
  1. Remove runtime data from the tree: `resources/trading/activity_log/*`, `resources/logs/*`, generated data under `resources/data/*` (keep templates). Update `.gitignore`.
  2. Voice-clone WAVs (16.7 MB, some named after real people): write a consent and licensing assessment in PROGRESS.md and request a human decision. Pending the decision, move sample voices that must remain into `resources/voice_samples/` with a `LICENSE`/consent manifest.
  3. HTML docs are kept (the portal is intentional), with the CI freshness check (WP-1.5).
  4. Resolve port collisions (8001 `openai_api` vs API replica — handled in WP-0.2/8.4; 8080 llama-server vs Nginx → move llama-server to 8180) and document the port map in one place (`docs/SETUP.md`).
- **Human gate:** history purge of large blobs (`src/tests.zip`, `src/app/rpg.zip`, test result zips, `node_modules` binaries) and of the key (WP-0.1) — one coordinated rewrite.
- **Acceptance:** `git ls-files resources/` contains only templates, config, examples and approved assets.

---

### Phase 12 — Certification

#### WP-12.1 — Re-measure, re-audit, re-rate

- **Depends on:** all previous WPs, or explicitly deferred items with human sign-off.
- **Steps:**
  1. Run `python scripts/architecture_metrics.py` and compare with the Appendix E targets. Every target must be met or have a signed-off exception in DECISIONS.md.
  2. Run the full validation suite (Appendix I), the nightly workflow (soak, multihost, rolling upgrade, restore rehearsal) and the security suite.
  3. Conduct a fresh review using the method in review §14: package import graph, route analysis, patch scan, subsystem audits. Write `docs/ENTERPRISE_ARCHITECTURE_RECERTIFICATION_<date>.md` with a scorecard in the same format as review §2 and evidence for each 9/10 criterion.
  4. Update [ARCHITECTURE.md](ARCHITECTURE.md), [OMNIX_RUNTIME_INVARIANTS.md](architecture/OMNIX_RUNTIME_INVARIANTS.md), [ARCHITECTURE_GATES.md](testing/ARCHITECTURE_GATES.md), README and SPEC to match the new architecture. Regenerate the HTML docs.
- **Acceptance:** every area and subsystem scores ≥ 9 with evidence; residual risks listed.

---

## 5. Appendices

### Appendix A — Runtime patch inventory and target owners

Verify each item at the time of work; there may be more. The lint (AL003/AL004) is the authoritative list.

#### A.1 Gateway hooks installed by `create_gateway_app`

These are installed via `gateway/__init__.py:_install_required_rpg_turn_hooks` → `runtime_hooks.initialize_gateway_runtime_hooks()`, in this order:

| # | Installer (module) | Patches (per audit) | Target owner after WP-3.x |
|---|---|---|---|
| 1 | `install_companion_activity_user_turn_hook` (`companion_activity_user_turn.py`) | Chat user-turn flow | `app/companion_activity` collaborator injected into the chat turn pipeline |
| 2 | `install_live_sse_transport_hook(constructor_hook=False)` (`live_sse_transport.py`) | Starlette `StreamingResponse.__init__`; assistant turn start | `app/live_voice/transport/sse.py` (`OmnixStreamingResponse`) |
| 3 | `install_live_chat_postgres_fast_path` (`live_chat_postgres_fast_path.py`) | `PostgresChatSessionStore.get_session`, `PostgresCharacterChatSessionStore.begin_user_message`, `complete_streamed_reply` | Chat store native (WP-3.1) |
| 4 | `install_live_chat_low_latency_stream_hook` | `PromptChatSessionStore.stream_provider_reply_chunks` | `app/live_voice/llm/stream.py` |
| 5 | `install_live_chat_provider_metrics_hook` | `stream_provider_reply_chunks` | `app/live_voice/llm/metrics.py` + WP-10.3 |
| 6 | `install_live_chat_stream_retry_hook` | `stream_provider_reply_chunks` | `app/live_voice/llm/retry.py` (or WP-7.2 retry middleware) |
| 7 | `install_live_chat_provider_routing_hook` | `stream_provider_reply_chunks` | `app/live_voice/llm/routing.py` |
| 8 | `install_live_chat_prompt_window_hook` | Prompt assembly | `app/live_voice/prompt/window.py` |
| 9 | `install_live_chat_live_voice_profile_hook` | `stream_provider_reply_chunks`, `LMStudioProvider.chat_completion`, prompt builder | `app/live_voice/prompt/profile.py` |
| 10 | `install_lmstudio_loaded_model_resolution_hook` | `LMStudioProvider.chat_completion` | `app/live_voice/llm/lmstudio_model_resolution.py`, or LM Studio provider native (WP-7.2) |
| 11 | `install_live_chat_lmstudio_responses_hook` | LM Studio response handling | `app/live_voice/llm/lmstudio_responses.py` |
| 12 | `install_live_voice_spoken_style_hook` | Prompt/style | `app/live_voice/prompt/spoken_style.py` |
| 13 | `install_live_chat_companion_context_hook` | Prompt context | `app/live_voice/prompt/companion_context.py` |
| 14 | `install_live_chat_prompt_cache_hook` | `live_voice_profile._build_live_voice_prompt`, `prompt_assembly.resolve_system_session_identity` | `app/live_voice/prompt/cache.py` |
| 15 | `install_live_chat_prompt_dependency_stage_hook` | Prompt stages | `app/live_voice/prompt/dependency_stages.py` |
| 16 | `install_live_chat_lmstudio_diagnostics_hook` | Diagnostics | `app/live_voice/llm/lmstudio_diagnostics.py` |
| 17 | `install_memory_job_offload_hook` | Memory job execution (process-local executor) | Durable memory jobs (WP-3.2 step 4) |
| 18 | `install_live_voice_runtime_offload_hook(constructor_hook=False)` | TTS provider resolution | `app/live_voice/speech/runtime_offload.py` |
| 19 | Seam swap: `tts_live_call_websocket.get_tts_provider = get_cached_live_tts_provider` | Module function | Constructor-injected `TTSProviderResolver` |
| 20 | `install_tts_live_call_pcm_diagnostics_hook` | WebSocket diagnostics | `app/live_voice/speech/pcm_diagnostics.py` |
| 21 | `install_tts_live_call_startup_frame_policy` | Startup frames | `app/live_voice/speech/startup_frame_policy.py` |

Then `_install_required_rpg_turn_hooks` (RPG section, A.3) and `install_rpg_turn_job_mirror_hook(constructor_hook=False)`.

#### A.2 Composition root, kernel and platform

| Location | Patch | Target |
|---|---|---|
| `runtime_composition.py` `production_job_store` | `install_rpg_turn_job_guard(PostgresJobStoreAdapter)`, `install_rpg_debug_job_hook(PostgresJobStoreAdapter)` | RPG `submission_policy`; `JobObserver` (WP-3.5) |
| `runtime_composition.py` `production_chat_store` | `install_live_agent_store_hooks(PostgresCharacterChatSessionStore, …)` | Injected live-agent planner port (WP-3.5) |
| `production.py` | `services.jobs.chat_execution_owner = owner`, `services.jobs.chat_dispatcher = dispatcher` | Constructor parameters (WP-3.5) |
| `jobs/__init__.py:48-55` | `install_inline_feature_job_execution`, `install_rpg_last10_report_inline_job`, `install_rpg_turn_job_guard`, `install_voice_studio_job_execution`, `install_image_job_execution`, `install_research_job_execution`, `install_rpg_debug_job_hook` on `InMemoryJobStore` | Job handler registry (WP-2.5) |
| `platform/__init__.py:1-11` | `_rpg_new_game_module.create_new_game_session = …with_progress` | Native in RPG (WP-2.7) |
| `src/sitecustomize.py` | `builtins.opening_bonus`; `LMStudioProvider.generate/generate_stream/call` | Fix NameError; RPG LLM gateway adapter (WP-3.3e, 3.7) |
| `trading/__init__.py:7-14` | Standard-library `enum` patch (StrEnum) | Python 3.11 (WP-1.3) |

#### A.3 RPG hooks

- **Required** (from `gateway/runtime_hooks.py:_install_required_rpg_turn_hooks`):
  - `install_fast_visible_dialogue_hook`
  - `install_dialogue_quality_hook`
  - `install_interaction_timeline_hook`
  - `install_interaction_lifecycle_hook` (itself installs a runtime hook, a worker hook and a load-recovery hook)
  - `install_rpg_turn_job_mirror_hook`
- **Optional, best-effort** (`rpg/session/__init__.py:79-101`, silent on failure):
  1. fast_combat_narration_skip
  2. fast_combat_presentation_hook
  3. interactive_fast_combat_result_hook
  4. player_agency_runtime_hook (also a `sys.meta_path` hook)
  5. npc_dialogue_repair_hook
  6. interpretive_adjudication
  7. first_call_dialogue_guard
  8. hypothetical_world_resolution
  9. contract_attachment
  10. diegetic_fallback_hook
  11. fast_visible_dialogue_hook
  12. visible_response_runtime_hook
  13. session_performance_hook
  14. interaction_event_store_hook
  15. dialogue_quality_hook
  16. interaction_timeline_hook
  17. interaction_lifecycle_hook
  18. narrative_engine_direct_dialogue_hook
  19. `rpg.debug_runtime_hook`
- **Also:**
  - the 40-part globals merge in `rpg/session/runtime.py`;
  - `apply_turn` rebound by 9 modules; `service.load_session` by 3;
  - 4 `sys.meta_path` import hooks;
  - `world_scene_survival_grounding_bridge.install_world_scene_survival_grounding_hook`.
- **Target:** explicit `TURN_PIPELINE` stages (WP-3.3c) and responsibility modules (WP-3.3d).

#### A.4 Trading installers

Folded in this exact order (`trading/__init__.py:51-75`):

1. `install_ai_shadow_reliability`
2. `install_persistent_ai_shadow_circuit`
3. `install_trading_data_hardening` (includes the AUTO_PAPER authorization wrapper on `_run_config` and wraps `_evaluate_candidates`)
4. `install_trading_data_runtime_refinements`
5. `install_trading_session_reliability`
6. `install_ai_shadow_v2_hardening`
7. `install_ai_shadow_v2_catalyst_provenance`
8. `install_ai_shadow_v2_roadmap_policy`
9. `install_ai_shadow_v2_catalyst_consistency`
10. `install_ai_shadow_v2_schedule_policy`
11. `install_ai_shadow_v2_metrics_policy`
12. `install_ai_shadow_v2_risk_policy`
13. `install_strategy_runtime_reliability_fixes`
14. `install_shadow_data_gap_guard`
15. `install_intraday_llm_reliability`
16. `install_ai_shadow_v2_circuit_guard`
17. `install_strategy_runtime_compatibility_fixes`
18. `install_dynamic_discovery_completeness`
19. `install_dynamic_discovery_completeness_refinements`

Plus `strategies/__init__.py:31` rebinding `evaluate_gap_pullback`, and the unused `install_trading_route_hook`.

#### A.5 Agent runtime

- `AgentRunService.__getattribute__` global rewriting (`service.py:548-574`)
- `pi_runtime.py` rebinding at import (~75, 102, 116, 234)
- `review_orchestration.py:213-221` global swap

#### A.6 Frontend

Enumerated by ESLint (WP-1.7):
- 17 files assigning `window.fetch`;
- `voiceJobListGuard.ts` and `podcastSessionGuard.ts` client method replacements;
- 55 `window.__omnix*` flags;
- import-time installs via `characterClient.ts` → `liveCharacterAvatarBridge.ts:617`, `liveCharacterVisemeBridge.ts:388`, `live2dCharacterRenderer.ts:728`.

### Appendix B — Package cycles and their resolutions

| Cycle | Resolution | WP |
|---|---|---|
| agent_runtime ↔ assistant_tools | Capability registry and adapter registry move to `app/capabilities`; both depend on it | 2.9, 8.2 |
| assist_core ↔ assistant_tools | Dissolve `assist_core` (hermes_rpg → rpg, hermes → app/hermes) | 8.2 |
| assistant_context ↔ research | `research/quick_search.py:10` must not import assistant_context; move the shared type to `app/conversation` or research contracts | 2.9 |
| assistant_memory ↔ chat | `app/conversation` contracts + `TranscriptReader` port | 2.9 |
| assistant_memory ↔ characters | Characters depends on memory contracts only | 2.9 |
| characters ↔ chat | `ChatSession` model in `app/conversation`; greeting/proactive turns via the chat service port | 2.9 |
| chat ↔ testing, jobs ↔ testing | Move `app/testing` to `src/tests/support`; no production imports | 2.9 |
| gateway ↔ jobs | `BackgroundWorker` to `app/runtime` | 2.1 |
| gateway ↔ platform, gateway ↔ persistence | Persistence subclassing a gateway store (`document_feature_compat.py`) and building gateway turn records (`rpg_turn_service.py:41`) move to owners | 2.6 |
| jobs ↔ persistence | Jobs kernel owns job repositories; persistence kernel does not import jobs models except contracts | 2.5, 2.6 |
| jobs ↔ rpg, jobs ↔ research | Feature handlers move to features | 2.5 |
| persistence ↔ rpg | RPG repositories move to `app/rpg/persistence` | 2.6 |
| persistence ↔ research, persistence ↔ providers | Feature stores move to owners | 2.6 |

### Appendix C — Permission catalog (starter)

| Permission | Meaning | Default roles |
|---|---|---|
| `chat:read` / `chat:write` | Sessions and messages | viewer (read), member+ |
| `characters:read` / `characters:write` | Character profiles | viewer / member+ |
| `memory:read` / `memory:write` / `memory:admin` | Memory items, settings, management | viewer / member / admin |
| `assets:read` / `assets:write` / `assets:delete` | Assets | viewer / member / member |
| `jobs:read` / `jobs:cancel` | Job views and cancel | viewer / member |
| `tools:propose` / `tools:approve` / `tools:execute` | Assistant tools | member / approver+admin / member |
| `tools:connections:admin` | OAuth connections, credentials | admin |
| `agent:run` / `agent:steer` / `agent:approve` / `agent:promote` / `agent:workflows:admin` | Agent runtime | member / member / approver+admin / admin / admin |
| `rpg:play` / `rpg:author` / `rpg:admin` | RPG | member / member / admin |
| `trading:read` / `trading:paper:order` / `trading:control` / `trading:strategies:admin` | Trading | viewer / member / admin / admin |
| `audiobook:read` / `audiobook:write` | Audiobook | viewer / member |
| `voice:read` / `voice:write` / `voice:clone` | Voice studio / cloning (consent governance) | viewer / member / member |
| `image:generate` / `image:models:admin` | Image | member / admin |
| `settings:read` / `settings:write` | Settings | member / admin |
| `admin:diagnostics` / `admin:metrics` / `admin:docs` / `admin:features` / `admin:users` | Operations | admin |

`owner` has all permissions. The `approver` role adds only `*:approve` permissions.

### Appendix D — Layer map for the architecture lint

Proposed `resources/architecture/layers.toml`. Adjust package names as they are created; do not loosen the rules.

```toml
[layers.kernel]
packages = [
  "app.runtime", "app.config", "app.security", "app.observability", "app.events",
  "app.persistence", "app.jobs", "app.assets", "app.capabilities", "app.conversation", "app.text",
]
may_import = ["kernel"]

[layers.shared_services]
packages = ["app.providers", "app.prompts", "app.platform"]
may_import = ["kernel", "shared_services"]

[layers.features]
packages = [
  "app.chat", "app.live_voice", "app.characters", "app.assistant_memory", "app.assistant_memory_v2",
  "app.rpg", "app.trading", "app.agent_runtime", "app.assistant_tools", "app.audiobook", "app.image",
  "app.voice", "app.research", "app.story", "app.hermes", "app.companion_activity", "app.desktop_companion",
  "app.live_speech", "app.replay",
]
may_import = ["kernel", "shared_services"]
# Feature-to-feature imports are allowed only into "<feature>.contracts" modules
# and only when declared in FeatureModule.depends_on.
feature_contract_module = "contracts"

[layers.composition]
packages = ["app.gateway", "app.production", "app.worker", "app.launcher"]
may_import = ["*"]

[owners]
# AL006: SQL on platform tables allowed only here
platform_table_sql = [
  "app/persistence/job_repository.py", "app/persistence/execution_repositories.py",
  "app/persistence/outbox_repository.py", "app/persistence/identity_service.py",
  "app/persistence/audit.py", "app/persistence/migrations.py", "app/persistence/retention.py",
]
blob_store_construction = ["app/persistence/blob_store.py", "app/persistence/storage.py"]

[rpg_core]
# AL013 applies here (determinism)
packages = [
  "app.rpg.core", "app.rpg.session", "app.rpg.combat", "app.rpg.economy", "app.rpg.items",
  "app.rpg.world", "app.rpg.social", "app.rpg.action_resolver",
]
```

### Appendix E — Ratchet metrics

Measure baselines in WP-1.1. Values marked "measure" must be computed then.

| Metric key | Definition | Baseline | Direction | Target |
|---|---|---:|---|---:|
| `package_cycles` | Top-level package 2-cycles (module-level imports) in `src/app` | 17 | lower | 0 |
| `layer_violations` | AL001 count | measure | lower | 0 |
| `foreign_attribute_assignments` | AL003 in `src/app` | measure (≥ 90 known) | lower | 0 |
| `install_hook_functions` | AL004 / `install_*` with patches | 87 | lower | 0 |
| `fastapi_init_patchers` | Files assigning `FastAPI.__init__` | 48 | lower | 0 |
| `async_handlers_without_await` | AL005 | 229 | lower | 0 |
| `schema_excluded_routes` | `include_in_schema=False` on non-internal routers | 274 | lower | 0 (except documented transport exceptions) |
| `untyped_body_routes` | Route params typed `dict`/`Any` | 24 | lower | 0 |
| `routes_without_permission` | Routes lacking a permission dependency and not public | 767 | lower | 0 |
| `bootstrap_calls_outside_startup` | AL012 | 132 | lower | 0 |
| `env_reads_outside_config` | AL007 | 388 | lower | 0 |
| `print_calls` | AL008 | 198 | lower | 0 |
| `silent_broad_excepts` | AL009 | 183 | lower | ≤ 10 |
| `star_imports` | AL010 | 246 | lower | 0 |
| `platform_table_sql_outside_owner` | AL006 | 57+ | lower | 0 |
| `direct_requests_calls` | `requests.<verb>(` in `src/app` | 35 | lower | 0 |
| `local_blob_store_constructions` | AL011 | 7 | lower | 1 |
| `absolute_storage_path_reads` | `storage_path` attribute reads outside the storage kernel | 21 files | lower | 0 |
| `unbounded_fetchall` | Repository `fetchall()` with no LIMIT | 29 | lower | 0 |
| `capped_500_queries` | `LIMIT 500` / `limit=500` caps in list paths | 28 | lower | 0 |
| `rpg_nondeterminism` | AL013 | measure | lower | 0 |
| `files_over_1200_lines` | Non-generated Python/TS files | measure | lower | ≤ 5 (documented) |
| `functions_over_150_lines` | Python + TS | measure | lower | ≤ 20 (documented) |
| `largest_class_lines` | Max class size, Python | 4,556 | lower | ≤ 800 |
| `quarantined_tests` | Entries in `quarantine.toml` | measure (WP-1.4) | lower | 0 |
| `collection_errors` | pytest collection errors | 112 | lower | 0 |
| `fixed_sleeps_in_tests` | `time.sleep(<const>)` in tests | 55 | lower | ≤ 5 |
| `mypy_ignored_modules` | Override patterns with `ignore_errors` | measure | lower | 0 kernel, ≤ 10% total |
| `compat_modules` | `*_compat.py` files | 17+ | lower | 0 (renamed stable adapters) |
| `process_local_state_unapproved` | Inventory entries not approved (WP-6.6) | measure | lower | 0 |
| `unreachable_rpg_modules` | Reachability report | 526 | lower | 0 |
| `rls_coverage_pct` | Tenant tables with RLS | 0 | higher | 100 |
| `retention_policies_executed_pct` | Policies with a successful run in the last 48 h (test env) | 0 | higher | 100 |
| `outbox_consumer_coverage_pct` | Written event types with consumers | 0 | higher | 100 |
| `web_fetch_assignment_files` | ESLint rule | 17 | lower | 0 |
| `web_omnix_window_flags` | `window.__omnix*` | 55 | lower | 0 |
| `web_raw_fetch_outside_api` | `fetch(` outside `src/api` | 76 | lower | 0 |
| `web_handwritten_api_types` | Payload types for schema routes | 272 | lower | 0 |
| `web_openapi_path_coverage_pct` | UI-called paths in OpenAPI | 36 | higher | 100 (except documented transport exceptions) |
| `web_important` | `!important` in CSS | 1,671 | lower | ≤ 50 |
| `web_hardcoded_colors` | Color literals in CSS/TSX styles | 6,675 | lower | ≤ 300 |
| `web_mutation_observer_files` | | 19 | lower | ≤ 2 |
| `web_set_interval_files` | | 28 | lower | ≤ 5 |
| `web_custom_event_dispatch_files` | | 61 | lower | 0 |
| `web_unreachable_modules` | | 92 | lower | 0 |
| `web_error_boundaries` | Route-level boundaries | 0 | higher | = number of routes |
| `eslint_baseline_disables` | Baseline disable comments | measure (WP-1.7) | lower | 0 |
| `boot_imported_modules` | Modules imported by `import app.production` + app build | measure | lower | ratchet |
| `inline_prompt_strings` | Prompt literals outside the prompt registry | 117 | lower | ≤ 10 |

### Appendix F — Characterization-test recipe

1. **Choose a boundary** whose behaviour must be preserved: a public function, route or pipeline entry.
2. **Make it deterministic.** Seed RNGs (RPG after WP-3.3a). Freeze the clock (inject, or `freezegun`-style fakes built in-house; no new dependency needed). Use `FakeLLMProvider` with scripted responses keyed by the prompt's sha256 (store the scripts next to the goldens). Use `FakeMarketData` with fixed bar fixtures from `src/tests/fixtures`.
3. **Capture outputs:** return values, persisted rows (query them after the call), emitted events, provider calls (prompts, sent via the fake), and log records at WARNING and above.
4. **Normalize:** replace UUIDs with ordinal placeholders in order of first appearance; strip timestamps and durations; sort sets; round floats to 6 decimals.
5. **Store** the golden JSON under `src/tests/characterization/golden/<scenario>.json`. Commit the harness and goldens in a PR **before** the refactor, generated on the pre-refactor code.
6. **During refactoring**, goldens must not change. If a change is intended (a bug fix), put it in a separate PR with a written justification and human approval.
7. **Retire** a characterization test only when it is superseded by specific behavioural tests that cover the same outputs.

### Appendix G — Dead-code deletion protocol

1. **Prove it is unreachable:** run `scripts/reachability_report.py` (created in WP-8.6; use it earlier if it exists, else build a minimal version following review §11.4's method) **and** a text search for the module path, its dotted name, and dynamic references (`import_module`, file paths, string registries, the feature catalog).
2. **Check tests:** if tests import the module, decide whether they test live behaviour through it (then it is not dead) or only the module itself (delete them together).
3. **Check non-Python consumers:** scripts, docs, CI workflows, launcher configuration, the web app.
4. **Delete** in a PR titled `remove unreachable <package> modules`, listing each module with its evidence (the reachability output) in the PR description.
5. **Validate:** the full suite plus the feature matrix test.
6. **Record** the deletion in PROGRESS.md with line counts.

### Appendix H — ADRs to write

| ADR | Title | WP |
|---|---|---|
| ADR-0015 | No runtime patching; explicit extension points | 1.2 |
| ADR-0016 | FeatureModule contract and feature catalog | 2.2 |
| ADR-0017 | Typed configuration and settings service | 2.3 |
| ADR-0018 | Migrations as a release step; expand/contract compatibility window; role separation | 2.4 |
| ADR-0019 | Job handler registry and execution context | 2.5 |
| ADR-0020 | Identity, sessions, CSRF and authentication modes | 4.1 |
| ADR-0021 | Authorization (permissions, roles) and row-level security | 4.3, 4.4 |
| ADR-0022 | Approvals, CapabilityExecutor and run tokens | 4.5, 4.6 |
| ADR-0023 | Agent sandbox and egress policy | 4.7 |
| ADR-0024 | Event delivery (commit-safe cursor, NOTIFY, outbox relay) | 5.3, 5.4 |
| ADR-0025 | Blob storage protocol and asset keys | 5.8 |
| ADR-0026 | Job worker pools, scheduler with per-task ownership, device permits | 6.1–6.3 (updates ADR-0011) |
| ADR-0027 | Provider service, transport policy and prompt registry | 7.2, 8.4 |
| ADR-0028 | Trading strategy contract and OrderGateway | 8.3 (updates ADR-0004) |
| ADR-0029 | Frontend module runtime, typed client and CSS architecture | 9.1–9.8 |
| ADR-0030 | Observability stack (logs, metrics, traces, error envelope) | 10.1–10.5 |

Use the existing short ADR format (see [ADR-0013](architecture/ADR-0013-durable-job-fencing.md)): status, decision, consequences.

### Appendix I — Validation command reference

Run from the repository root, one command at a time (no shell composition).

**Python:**

```text
python -m pytest <focused-test-path> -q --tb=short
python -m pytest -q
python -m pytest -m "postgres or multiprocess" -q
ruff check .
mypy
python scripts/architecture_lint.py --check
python scripts/architecture_metrics.py --check
python scripts/run_architecture_gates.py --group unit
python scripts/run_architecture_gates.py --group postgresql
python scripts/run_architecture_gates.py --group multiprocess
python scripts/run_architecture_gates.py --group persistence-all
python -m app.persistence status --json
```

(PostgreSQL gates need `OMNIX_TEST_DATABASE_URL` set to a disposable `omnix_test` database, or the `--local-disposable` profile described in [ARCHITECTURE_GATES.md](testing/ARCHITECTURE_GATES.md).)

**Web:**

```text
npm --prefix src/apps/web run lint
npm --prefix src/apps/web run typecheck
npm --prefix src/apps/web run test -- <focused-test>
npm --prefix src/apps/web run test
npm --prefix src/apps/web run build
npm --prefix src/apps/web run api:check
npm --prefix src/apps/web run test:e2e
```

**Benchmarks** (record JSON under `docs/measurements/`):

```text
python scripts/benchmark_gateway_baseline.py --samples 30 --output <file>
python scripts/check_architecture_benchmark.py --baseline resources/benchmarks/gateway/refactor-baseline.json --measured <file>
python scripts/benchmark_gateway_postgresql.py --samples 20 --output <file>
python scripts/benchmark_chat_recovery.py --samples 10 --output <file>
python scripts/benchmark_gateway_scaling.py --workers 3 --submissions 30 --output <file>
python scripts/measure_gateway_soak.py --mock-compute --duration-seconds 600 --output <file>
python scripts/certify_postgresql_restart.py --container omnix-architecture-test --local-disposable --output <file>
```

**Docs:**

```text
python docs/render_docs.py
```
