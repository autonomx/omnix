# Enterprise roadmap progress

Source: [roadmap](../ENTERPRISE_ARCHITECTURE_ROADMAP_2026-09-27.md) and [review](../ENTERPRISE_ARCHITECTURE_REVIEW_2026-09-27.md). Deviations: [DECISIONS.md](DECISIONS.md).

Completion requires every acceptance criterion and the Phase 12 certification. A code change alone is not certification. Existing untracked operator artifacts are preserved.

| WP | Status | PRs | Date | Metric deltas | Notes |
|---|---|---|---|---|---|
| WP-0.0 | done | — | 2026-09-27 | — | Progress and decision logs |
| WP-0.1 | done | — | 2026-09-27 | Current source scan: 0 leaks | Repository containment complete; credential rotation and history purge remain human actions |
| WP-0.2 | done | — | 2026-09-27 | Public bind literals outside policy: 0 | Shared listener policy, launcher propagation, exact CORS origins, standalone API port 8101 |
| WP-0.3 | done | — | 2026-09-27 | Additional web fetch wrappers: 0 | Host/Origin/CSRF guard applied to owning apps; clients and Windows startup watchdog send header |
| WP-0.4 | done | — | 2026-09-27 | 31 request-policy tests; 33 PostgreSQL approval/proposal tests | Acceptance checks pass: durable proposal/decision/execute flow, strict envelopes, generated contracts, explicit UI confirmation, random broker identities and no web client approval grant. Broader retired-contract test cleanup remains WP-1.4 |
| WP-0.5 | done | — | 2026-09-27 | 42 PostgreSQL worker/foreground protocol regressions; 40 credential/launcher tests; model/transport regressions | Internal workers and non-health model routes require service credentials; original claims fence finalization. Protected provisioning, streamed limits, private errors and gateway STT proxy implemented. Exact foreground ownership audit and required unit/PostgreSQL gates pass |
| WP-1.1 | in progress | — | 2026-09-27 | 49 metrics; 92 collection errors; 2,515 boot imports | Shared lexical provenance implemented; provisional inventory correction audited against the preserved original inputs. Fresh evidence and canonical locked CI verification remain pending |
| WP-1.2 | in progress | — | 2026-09-27 | 104 focused lint regressions; no migration violations | All 14 rules, shrinking inventory, migration protection, CI wiring and ADR-0015 implemented; alias/shadowing defects fixed. Canonical locked CI acceptance remains pending |
| WP-1.3 | in progress | — | 2026-09-27 | Python 3.11 baseline and runtime input manifests committed | Root pyproject/Ruff policy and per-runtime requirement inputs are committed; setup uses Python 3.11 and Trading no longer patches enum.StrEnum. Hashed lock compilation, Docker/workflow alignment and clean-install validation remain pending |
| WP-1.4 | not started | — | 2026-09-27 | — | Test estate triage: collect everything, fix or quarantine, drive to zero |
| WP-1.5 | not started | — | 2026-09-27 | — | One required CI pipeline |
| WP-1.6 | not started | — | 2026-09-27 | — | Python type checking rollout |
| WP-1.7 | not started | — | 2026-09-27 | — | ESLint for the web app with boundary and patch rules |
| WP-2.1 | not started | — | 2026-09-27 | — | Neutral runtime package |
| WP-2.2 | not started | — | 2026-09-27 | — | FeatureModule contract and feature catalog |
| WP-2.3 | not started | — | 2026-09-27 | — | Typed configuration and a settings service |
| WP-2.4 | not started | — | 2026-09-27 | — | Migrations become a release step; tenant bootstrap leaves request paths |
| WP-2.5 | not started | — | 2026-09-27 | — | Jobs kernel inversion: typed handler registry |
| WP-2.6 | not started | — | 2026-09-27 | — | Persistence kernel inversion and a composable unit of work |
| WP-2.7 | not started | — | 2026-09-27 | — | Platform package cleanup |
| WP-2.8 | not started | — | 2026-09-27 | — | Retire `shared.py` |
| WP-2.9 | not started | — | 2026-09-27 | — | Package cycles to zero |
| WP-3.0 | not started | — | 2026-09-27 | — | Characterization harness |
| WP-3.1 | not started | — | 2026-09-27 | — | Chat store: native targeted mutations; remove the whole-workspace save |
| WP-3.2 | not started | — | 2026-09-27 | — | Live voice becomes a module (`app/live_voice`) with explicit ports |
| WP-3.3 | not started | — | 2026-09-27 | — | RPG: determinism, an explicit turn pipeline, and collapsing the runtime parts |
| WP-3.3a | not started | — | 2026-09-27 | — | Deterministic core (fixes RPG1) |
| WP-3.3b | not started | — | 2026-09-27 | — | Characterization of the turn pipeline — create the `rpg-turn` scenarios (WP-3.0) using seeded sessions: combat, dialogue, item use, travel, idle, first call, fast paths. |
| WP-3.3c | not started | — | 2026-09-27 | — | Explicit ordered turn pipeline (replaces the hooks) |
| WP-3.3d | not started | — | 2026-09-27 | — | Collapse the 40 runtime parts |
| WP-3.3e | not started | — | 2026-09-27 | — | Fix hidden errors masked by `sitecustomize` — fix `rpg/ai/npc_initiative.py:416` (`opening_bonus` undefined) and any other `NameError` that F821 revealed in RPG. |
| WP-3.4 | not started | — | 2026-09-27 | — | Trading: fold the import-time overlays into their owners |
| WP-3.5 | not started | — | 2026-09-27 | — | Composition-root and jobs-kernel class patches |
| WP-3.6 | not started | — | 2026-09-27 | — | Agent runtime patch seams |
| WP-3.7 | not started | — | 2026-09-27 | — | Delete `sitecustomize.py` and `usercustomize.py` |
| WP-3.8 | not started | — | 2026-09-27 | — | Delete legacy patchers and unused route hooks |
| WP-4.1 | not started | — | 2026-09-27 | — | Authentication |
| WP-4.2 | not started | — | 2026-09-27 | — | Per-request principal and tenant context |
| WP-4.3 | not started | — | 2026-09-27 | — | Authorization (RBAC with a permission catalog) |
| WP-4.4 | not started | — | 2026-09-27 | — | PostgreSQL row-level security |
| WP-4.5 | not started | — | 2026-09-27 | — | Approvals bound to principals; a single CapabilityExecutor |
| WP-4.6 | not started | — | 2026-09-27 | — | Run-scoped signed tokens for the broker and model gateway |
| WP-4.7 | not started | — | 2026-09-27 | — | Agent sandbox by default, egress control, global run limits |
| WP-4.8 | not started | — | 2026-09-27 | — | Audit logging for sensitive actions |
| WP-4.9 | not started | — | 2026-09-27 | — | Secret store |
| WP-4.10 | not started | — | 2026-09-27 | — | Hardening: headers, rate limits, docs exposure, SSRF, disclosure |
| WP-4.11 | not started | — | 2026-09-27 | — | Threat model, ASVS checklist, security test suite |
| WP-5.1 | not started | — | 2026-09-27 | — | Complete job fencing and job-engine hygiene |
| WP-5.2 | not started | — | 2026-09-27 | — | Retention and lifecycle worker |
| WP-5.3 | not started | — | 2026-09-27 | — | Outbox relay and consumers |
| WP-5.4 | not started | — | 2026-09-27 | — | Event delivery: one reader, NOTIFY wake-up, commit-safe cursor |
| WP-5.5 | not started | — | 2026-09-27 | — | Collections: cursor pagination and projections everywhere |
| WP-5.6 | not started | — | 2026-09-27 | — | RPG state model: typed state, deltas, periodic snapshots |
| WP-5.7 | not started | — | 2026-09-27 | — | Chat and memory query performance |
| WP-5.8 | not started | — | 2026-09-27 | — | Blob storage protocol and S3-compatible adapter |
| WP-5.9 | not started | — | 2026-09-27 | — | JSONB governance and optimistic concurrency |
| WP-5.10 | not started | — | 2026-09-27 | — | Connection and transaction management |
| WP-5.11 | not started | — | 2026-09-27 | — | Migration lint in CI |
| WP-6.1 | not started | — | 2026-09-27 | — | Job worker pools by resource class, as a standalone process |
| WP-6.2 | not started | — | 2026-09-27 | — | Device permits for GPU capacity across processes |
| WP-6.3 | not started | — | 2026-09-27 | — | Scheduler with per-task ownership |
| WP-6.4 | not started | — | 2026-09-27 | — | Live voice scaling |
| WP-6.5 | not started | — | 2026-09-27 | — | Agent runtime concurrency and durability |
| WP-6.6 | not started | — | 2026-09-27 | — | Inventory and elimination of process-local state |
| WP-6.7 | not started | — | 2026-09-27 | — | Rolling deployment support |
| WP-6.8 | not started | — | 2026-09-27 | — | Multi-host topology test and capacity benchmarks |
| WP-7.1 | not started | — | 2026-09-27 | — | Event-loop correctness |
| WP-7.2 | not started | — | 2026-09-27 | — | Provider transport, registry and caching |
| WP-7.3 | not started | — | 2026-09-27 | — | Media streaming end to end |
| WP-7.4 | not started | — | 2026-09-27 | — | Agent runtime event volume and queries |
| WP-7.5 | not started | — | 2026-09-27 | — | Trading compute and data paths |
| WP-7.6 | not started | — | 2026-09-27 | — | Query optimization pass with populated data |
| WP-7.7 | not started | — | 2026-09-27 | — | Import time and cold start |
| WP-7.8 | not started | — | 2026-09-27 | — | Frontend performance |
| WP-8.1 | not started | — | 2026-09-27 | — | Persistence and jobs subsystem wrap-up |
| WP-8.2 | not started | — | 2026-09-27 | — | Agent runtime decomposition and declarative extensibility |
| WP-8.3 | not started | — | 2026-09-27 | — | Trading: strategy plugin contract, OrderGateway, data authority, providers |
| WP-8.4 | not started | — | 2026-09-27 | — | Providers, prompts and model services |
| WP-8.5 | not started | — | 2026-09-27 | — | Chat, memory and characters |
| WP-8.6 | not started | — | 2026-09-27 | — | RPG: contracts, dead code, LLM fan-out, packaging as a plugin |
| WP-8.7 | not started | — | 2026-09-27 | — | Audiobook: polish the reference feature |
| WP-8.8 | not started | — | 2026-09-27 | — | Image feature |
| WP-9.1 | not started | — | 2026-09-27 | — | Module runtime lifecycle (activate/dispose) |
| WP-9.2 | not started | — | 2026-09-27 | — | Transport middleware in one API client |
| WP-9.3 | not started | — | 2026-09-27 | — | Typed API client from OpenAPI |
| WP-9.4 | not started | — | 2026-09-27 | — | React owns the DOM |
| WP-9.5 | not started | — | 2026-09-27 | — | Component decomposition |
| WP-9.6 | not started | — | 2026-09-27 | — | State and events |
| WP-9.7 | not started | — | 2026-09-27 | — | Feature boundaries and single-source module registration |
| WP-9.8 | not started | — | 2026-09-27 | — | CSS architecture |
| WP-9.9 | not started | — | 2026-09-27 | — | Resilience, accessibility and rendering performance |
| WP-9.10 | not started | — | 2026-09-27 | — | Frontend dead code and test estate |
| WP-10.1 | not started | — | 2026-09-27 | — | Structured logging |
| WP-10.2 | not started | — | 2026-09-27 | — | Request and job correlation |
| WP-10.3 | not started | — | 2026-09-27 | — | Metrics |
| WP-10.4 | not started | — | 2026-09-27 | — | Tracing (optional, off by default) |
| WP-10.5 | not started | — | 2026-09-27 | — | Error envelope and exception discipline |
| WP-10.6 | not started | — | 2026-09-27 | — | SLOs, dashboards, alerts |
| WP-10.7 | not started | — | 2026-09-27 | — | Backup, restore and disaster recovery |
| WP-10.8 | not started | — | 2026-09-27 | — | Runbooks |
| WP-10.9 | not started | — | 2026-09-27 | — | Diagnostics consolidation |
| WP-11.1 | not started | — | 2026-09-27 | — | Container images |
| WP-11.2 | not started | — | 2026-09-27 | — | Compose profiles |
| WP-11.3 | not started | — | 2026-09-27 | — | Ingress hardening |
| WP-11.4 | not started | — | 2026-09-27 | — | Launcher and scripts |
| WP-11.5 | not started | — | 2026-09-27 | — | Release process |
| WP-11.6 | not started | — | 2026-09-27 | — | Repository hygiene |
| WP-12.1 | not started | — | 2026-09-27 | — | Re-measure, re-audit, re-rate |

## Blocked

- WP-0.1: credential rotation and git-history purge require the human gate in roadmap section 1.5. Repository containment can proceed independently.

## Human actions requested

- Rotate/revoke the Cerebras credential formerly in src/app/data/settings.json (cerebras.api_key). Earliest known commit: 637220e19; review baseline: 7bd17af08. Do not paste the credential into logs or messages.
- After rotation, prepare and approve a coordinated history purge of that file using git filter-repo, including clone replacement and protected-branch handling. Rewriting history and force-pushing require explicit authorization under roadmap section 1.5.

## Validation evidence

Validation is recorded per work package as execution proceeds.

- WP-0.1: Gitleaks 8.30.0 source scan passes. Negative checks detect all six custom token families, including a new synthetic credential inside an allow-listed test file. Scanner binary checksum verified before use. Exceptions are restricted to named rules, paths and exact non-secret examples.
- WP-0.2–0.3: focused Python containment suite passed (152 tests); after the Windows watchdog correction, security and launcher suites passed again (104 tests). Ruff passes for the new policy/guard modules and focused clients. The production-source public-bind AST gate passes.
- WP-0.3: 424 web unit-test files / 1,550 tests pass; typecheck and production build pass; isolated shell e2e passes all 13 cases. Gateway OpenAPI/schema, route-policy and cluster tests pass; middleware does not change the generated schema.
- WP-0.4: 94 request-policy, broker, Pi runtime and generated-schema tests pass. Migration 0098 applied only to the disposable `omnix_test` database in a task-owned PostgreSQL container. All 33 approval repository, public/internal proposal API and workspace approval integration tests pass. Coverage includes concurrent consumption, replay, denial, expiry, input digest binding, tenant scope, ledger rollback, opaque IDs, concurrent exact-request deduplication, policy tightening and adapter failure. Eight workflow PostgreSQL integration tests also pass with trusted execution parameters. Expiry uses database wall time after acquiring the row lock.
- WP-0.4: 425 web files / 1,555 tests pass; typecheck and production build pass. The Pi extension behavioral harness passes: approval IDs are absent from model parameters/results, reordered identical input retries use the private ID, and changed input cannot reuse it. Public tool request models reject client approval fields; no `approved: true` literal or legacy internal execute URL remains in web source.
- WP-0.4: current isolated web shell e2e passes all 13 cases. The pure validator now shares the runtime gate's destructive-action rule; three regressions prevent destructive automatic execution through either gate.
- WP-0.5: 77 focused PostgreSQL tests pass, including 16 internal protocol tests, durable/local finalization, lease takeover, transaction-time expiry, chat ownership and memory transactions. The complete existing PostgreSQL architecture gate passes all 54 tests with its default runtime database explicitly set to the same disposable database. Unit architecture gate passes all 125 tests after adapting HTTP fixtures to the WP-0.3 Host/client-header contract; no guard was relaxed. Generated OpenAPI/types and web typecheck are current.
- WP-0.5: all 40 credential/launcher tests pass, including concurrent first-start publication, reuse, explicit environment precedence, invalid configuration, native Windows DPAPI round-trip, POSIX permission rejection, propagation without logging, and exclusion from the web process. Tests use task-owned temporary credential files or explicit ephemeral tokens. A broader gate was interrupted after its reload-launch test invoked provisioning without isolation; that fixture now provides an explicit token. No existing operator credential was read or changed; metadata verification confirms no service-token file was created in the default operator store.
- WP-0.5: model boundaries and gateway STT transport are implemented. Final focused run: 197 passed, with only the two previously confirmed baseline failures below remaining. All 152 security tests pass. Coverage includes every composed non-health model route, chunked/underreported/multipart upload limits, swallowed limit exceptions, private provider failures, stream correlation, gateway HTTP/WS transport and cleanup, and real HTTP credential/redirect containment. Worker model-control input and mutable STT settings cannot choose an unconfigured credential audience.
- WP-0.5: final unit architecture gate passes all 125 tests; the final PostgreSQL gate passes all 54 tests using only the task-owned disposable database. Web: 425 files / 1,559 tests pass, typecheck and production build pass, and isolated shell e2e passes all 13 cases. Generated OpenAPI/types and rendered operator docs are current. Ruff and `git diff --check` pass; the current source scan covers 7,289 files / 80.03 MB with no leaks.
- WP-0.5 foreground audit complete: generic compatibility flags cannot authorize an unleased transition. Inline chat requires its matching live gateway owner; ownerless legacy rows remain recoverable. RPG audit records require their exact attached, started submission and original scoped claim. All worker lease columns must be absent; both worker-claim implementations exclude foreground audit records. Public generic job creation rejects foreground types and execution-authority keys. Atomic RPG persistence no longer borrows either submission or worker credentials from a row.
- WP-0.4–0.5 final acceptance review: 107 focused persistence/foreground tests pass, including all 42 protocol regressions and atomic turn rollback/replay; 189 security/request-policy/worker ownership tests pass. All 33 approval/proposal/workspace integration tests and the Pi approval identity/retry harness pass again. Generated-schema validation passes all three tests; no `approved: true` or legacy internal execute URL remains in web source. The required architecture gates pass 125 unit and 54 PostgreSQL tests after the final implementation changes. Ruff and diff whitespace checks pass. The existing web validation remains current because this audit changed no browser code or request/response schema.
- WP-0.4–0.5 final source scan: 7,290 source/config/documentation files, approximately 80.06 MB, with no leaks. Operator docs were rendered and unrelated generated files restored.
- WP-1.4 triage candidates: assistant-tool tests still target retired file configuration, credential and ledger persistence; these owners have no changes from HEAD. Tests remain intact pending conversion to current PostgreSQL contracts. Current durable proposal behavior has dedicated PostgreSQL integration coverage; the full Python suite is not yet green.
- Workflow recovery regression: the combined approval/workflow run exposed an automatic-supervisor race with a test that explicitly calls `_supervise_once`. The manual recovery scenario now disables automatic scheduling on its own runtime; every state/event assertion remains intact. Background versus synchronous-start concurrency is recorded for WP-6.5; no production lifecycle behavior was changed for this fixture correction.
- WP-1.4 triage candidates: `test_generate_stream_audio_falls_back_to_wav_response` and `test_explicit_hf_token_is_used_only_for_snapshot_download` fail against the unchanged HEAD implementations as well as the working tree. They remain intact and are not quarantined or weakened.
- WP-1.4 triage candidates: two legacy tests in `rpg/test_rpg_direct_turn_routes.py` expect 200 without providing a session required by the unchanged campaign-genesis gate; both return 404 with the HEAD turn mirror as well. They remain intact. Current mirror claim propagation, atomic persistence and exactly-once replay are covered by the new disposable PostgreSQL regression. An initial broad audit run was stopped after old in-memory executions failed before finalizing their claims; their successor polling stalled. The corrected foreground scope is PostgreSQL-only, and the complete focused run now exits successfully. A separate initial chat run omitted the default runtime database and failed closed; rerunning with both URLs set to the same disposable database passes.
- WP-1.1: all 49 Appendix E detectors and the guarded runtime producer are implemented. Both conflicted files now collect all 38 tests. Empty, interrupted and internally failed collection cannot certify a report. Snapshot verification checks the digest and child probes execute the copied tooling. The existing unit architecture gate passes all 125 tests. The invalid prose runner is archived as documentation, its callers use pytest, and the Windows wrapper rejects unknown suites with exit status 2. The final legacy-config runtime probe collects 15,615 tests and observes 92 collection errors; those tests remain pending WP-1.4 rather than being suppressed. The initial local baseline was generated and its fresh ratchet check passed; source-bound runtime evidence is refreshed after the lint and scanner changes. Canonical locked Linux/Python 3.11 CI verification remains pending.
- WP-1.1–1.2: the final combined detector/probe suite passes all 143 regressions, including 41 lint tests. Ruff passes for every new architecture tool and focused test. All 5,463 tracked non-vendor Python files compile without execution. The lint inventory records violations by stable identity and occurrence count; adding lines cannot evade it, and fixes require shrinking it. Package cycles include longer strongly connected components with each edge separately recorded. All 119 existing migrations are protected without changing historical duplicate names. Migration violations cannot become exceptions. The initial inventory has no compilation or migration errors, and its full local check passes. The source scan covers 7,304 files / approximately 81.32 MB with no leaks. Negative checks detect all six custom token families and new generic/custom credentials at the checksum-registry path despite its exact hash exception.
- WP-1.2 acceptance audit: the three missed foreign writes and two false positives now have regression coverage and are corrected in the shared owner. All 220 combined checker/probe tests pass, including 104 lint tests and additional cases for scopes, branches, registries, setter aliases, typed factories, metaclasses and stable fingerprints. Ruff passes for the changed tools and checker tests. The preserved original source snapshot matches runtime digest `f48a22949b74b8561a1fdc62ea380f4204241b453014c334087de01dfb8f025b`; corrected measurements of those same inputs produce 503 AL003 occurrences and 136 AL004 occurrences. The current production lint inventory equals that corrected original inventory. Baseline correction evidence is archived separately; canonical CI certification remains pending.
- WP-0.5 follow-up: the undefined-name scan caught an out-of-scope connection ID in the STT background-feed error handler. It now uses the middleware request ID or a generated fallback. Two new failure-path regressions cover both cases and verify private response details. All 44 focused model-service/live-STT tests pass after the fix; F821 is zero in the changed files.
- WP-1.3 inspection: the initial non-vendor `src`/`scripts` F821 scan reports 241 findings, including the known NPC initiative defect and retired Flask handlers. These are recorded for correction and reachability review; no suppression was added.
- WP-1.3 preparation: a digest-pinned, non-root Python 3.11.16 Linux container and isolated pip-tools 7.6.1 resolver are ready. The draft gateway lock compiles with 63 distributions and 1,904 SHA-256 hashes. A fresh Linux environment installs it successfully using `--require-hashes`. The real production module imports successfully with networking disabled and a read-only, verified tracked-source snapshot; it does not eagerly import the gateway or model libraries. This draft remains under ignored task tooling; existing runtime installations, requirements and setup paths have not been replaced. Its newer framework versions require focused behavior validation or alignment with the currently tested pins before promotion.
- No real credential was rotated, history rewritten, operator database migrated, or operator data deleted. No PR/commit exists yet. Explicit task-owned new source, configuration and documentation files are staged for the tracked-file scan; Git index writes were approved by the sandbox reviewer. Unrelated untracked operator artifacts remain untouched.

- WP-1.3 implementation: root Python 3.11 packaging/tooling configuration and runtime-specific dependency inputs are now committed. The retired Python 3.10 Trading compatibility tests were converted to assert the Python 3.11/no-monkey-patch contract. The RPG initiative opening bonus now has an owning-module default instead of depending on sitecustomize.
