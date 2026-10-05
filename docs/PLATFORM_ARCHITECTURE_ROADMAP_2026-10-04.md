# Omnix platform architecture roadmap: a platform for a growing number of AI apps

Date: 2026-10-04. Baseline commit: `6d839964e` (branch `refactor-audit`). Revision 6, which applies the reviews of revisions 1 to 5 (see §8).

Follows: [enterprise roadmap](ENTERPRISE_ARCHITECTURE_ROADMAP_2026-09-27.md) and its [progress log](roadmap/PROGRESS.md).

The enterprise roadmap made the modular monolith real:
- one `FeatureModule` contract and catalog;
- kernel packages that no longer import features (WP-2.5, WP-2.6, WP-2.7);
- no runtime patching (Phase 3);
- an architecture lint with a shrinking baseline (WP-1.2).

This roadmap does not change that architecture. It finishes the job for one goal:

> **Adding an app means hand-editing only the app's own folders plus two files: one catalog line on the backend and one manifest line on the web.**

Generated files don't count, provided one documented command regenerates them and a check verifies them. Examples are the OpenAPI document, the web types, the migration checksums and the ownership manifests. Hand-edited central lists do count. Every central list a new app would otherwise have to edit gets derived from what the module declares.

---

## Contents

1. [Target architecture](#1-target-architecture)
2. [Where we are](#2-where-we-are)
3. [Rules of engagement](#3-rules-of-engagement)
4. [Program structure](#4-program-structure)
5. [Work packages](#5-work-packages)
   - [Phase PA-0 — Decision and guardrails](#phase-pa-0--decision-and-guardrails)
   - [Phase PA-1 — Dependency direction](#phase-pa-1--dependency-direction)
   - [Phase PA-2 — Modules own what they contribute](#phase-pa-2--modules-own-what-they-contribute)
   - [Phase PA-3 — Platform capabilities behind ports](#phase-pa-3--platform-capabilities-behind-ports)
   - [Phase PA-4 — Adding and retiring an app are recipes](#phase-pa-4--adding-and-retiring-an-app-are-recipes)
   - [Phase PA-5 — Physical layout](#phase-pa-5--physical-layout)
   - [Phase PA-6 — Certification](#phase-pa-6--certification)
   - [Track R — RPG bounded contexts](#track-r--rpg-bounded-contexts)
6. [Decisions considered and rejected](#6-decisions-considered-and-rejected)
7. [Progress](#7-progress)
8. [Revision history](#8-revision-history)

---

## 1. Target architecture

### 1.1 Four tiers

| Tier | What belongs here | May import |
|---|---|---|
| **Kernel** | Runtime, config, settings, security, observability, events/outbox, persistence/unit of work, jobs, assets/blobs, the tool capability registry, conversation contracts, the `FeatureModule` SDK. | Kernel only. |
| **Shared services** | LLM providers (including the Hermes sidecar client, `app/providers/hermes_client.py`), prompt rendering, the model catalog and downloads (`app/models`). | Kernel, shared services. |
| **Platform capabilities** | Reusable AI capabilities that apps build on: conversation engine (chat), memory, characters, companion activity, speech (voice, live voice, live speech), media (image), agents (agent runtime, assistant tools), research. | Kernel, shared services, and the contract of a platform capability it declares in `depends_on`. |
| **Apps** | User-facing products: RPG (including its Hermes flows in `app/rpg/hermes`), trading, audiobook, story, desktop companion, character interactions, and every future app. | Kernel, shared services, and the contract of a platform capability it declares in `depends_on`. **Never another app.** |
| *Composition* | Gateway, worker, worker runtime, launcher, `production.py`, `runtime_composition.py`. | Anything. Nothing imports composition. |

"Hermes" means two different things in this codebase:

- **The Hermes sidecar client** is a shared service. Agent runtime, chat, research, RPG and trading all use it.
- **`app/rpg/hermes`** is RPG's own sequence and approved-flow feature.

This document always says which one it means.

**How a module gets its tier.** A module declares its tier as `FeatureModule.tier` (`"platform"` or `"app"`). The field is required and has no default, so a new feature can't silently get a tier. The lint reads that declaration; it doesn't keep a hand-written list. The kernel and shared-service lists in `layers.toml` stay, because they change only when the platform itself changes, never when an app is added.

Rules that follow from the tiers:

1. **A contract dependency has one direction.** If B declares `depends_on=("a",)`, B may import A's contract. A may **not** import B's contract. Today's lint allows both directions; see PA-0.2.
2. **What counts as a contract.** A module's contract is the `contracts` module, or every submodule of a `contracts/` package.
3. **No dependency cycles.** The `depends_on` graph between platform capabilities is acyclic.
4. **Apps never import each other.**
5. **Reactions that can run later use events.** When a module reacts to another module's state change and the reaction can safely run later, it uses a typed event in the producer's contract, delivered by the outbox (`FeatureModule.outbox_consumers`).
6. **Same-transaction needs use ports.** If a module needs something done in the same transaction, or needs behaviour from a module above it, it defines a port: a `Protocol` in its own contract. The composition root binds an implementation to that port. This typed mechanism replaces today's string-keyed `FeatureModule.hooks`.

   A port that modules implement is "at most one" or "many". To import the port, an implementer must list the consumer in `depends_on`, so the consumer can't depend on the implementer without a cycle, and the implementer can be disabled on its own. Only the composition layer can bind an "exactly one" port.
7. **Contributions, not central lists.** Apps contribute declarations, and the platform never names them. That covers:
   - tools, settings sections, retention declarations (delete handler and default horizon; the database row stays authoritative), permissions and web manifests;
   - tables and migrations, including each table's tenant row-level security (RLS), which the module's own migration enables.

### 1.2 Module anatomy

The current [FeatureModule guide](architecture/FEATURE_MODULE_GUIDE.md) already defines `feature.py`, `routes.py`, `service.py` and `*_repository.py`. This layout extends it.

```
<module>/
├── feature.py         # the FeatureModule declaration (id, tier, depends_on, contributions, ...)
├── contracts.py       # or contracts/ : public DTOs, events, ports; the only thing other modules import
├── domain/            # optional: pure rules, no I/O (large modules)
├── service.py         # workflows and transaction boundaries; no SQL
├── *_repository.py    # all SQL, only against the module's own tables
├── routes.py          # HTTP only
├── declarations.py    # settings section + retention declarations (record type, delete handler, default horizon); kernel imports only
└── migrations/        # SQL migrations for the module's own tables, including their RLS (PA-2.3)
src/tests/<python_package>/   # the module's tests, named after its Python package (e.g. agent_runtime)
```

Composition imports `declarations.py` directly, by convention (`app.<package>.declarations`), for **every** catalog module, enabled or not. It never imports a disabled module's `feature.py`, which loads routers, job handlers and repositories. So `declarations.py` imports kernel code only: a disabled feature's heavy dependencies may not be installed.

### 1.3 Target folder structure

| Status | What moves |
|---|---|
| **Committed** | Model servers to `src/services/` (PA-5.1). Packages with no clear home get one, and runtime data leaves the source tree (PA-5.2). |
| **Decision gate** (PA-5.3) | Grouping packages into tier folders. Once tiers are declared, moving folders adds readability but no boundary. |

```
src/
├── app/
│   ├── kernel packages (runtime, config, settings, security, observability, events,
│   │                    persistence, jobs, assets, capabilities, conversation, caching)
│   ├── providers/ prompts/ models/      # shared services
│   ├── <platform capability packages>   # gate PA-5.3: optionally under app/platform/
│   ├── <app packages>                   # gate PA-5.3: optionally under app/apps/
│   └── composition packages             # gate PA-5.3: optionally under app/composition/
├── services/                            # separately run model servers: tts/ stt/ image/
├── apps/web/src/
│   ├── app/ api/ design/ shared/ events/   # shell, transport, core client
│   └── features/<feature>/                 # UI, module.ts manifest, api/ (its clients, generated types)
└── tests/<python_package>/ + tests/kernel/ + tests/e2e/ ...
```

---

## 2. Where we are

All values were measured at `6d839964e` with `scripts/architecture_lint.py` and source scans. PA-0.3 turns every row into a ratchet metric.

| Metric | Now | Target |
|---|---|---|
| AL001 layer violations | 59 | 0 |
| — feature → feature, undeclared or not through the contract | 48 | 0 |
| — kernel/shared → feature (`assets→image`, `providers→image`, `providers→rpg`) | 3 | 0 |
| — non-composition → `app.runtime_composition` (chat 2, characters 2, assets, assistant_memory, providers, research) | 8 | 0 |
| Imports against `depends_on` direction, allowed today because the contract rule accepts either direction (mostly in `app.chat`: memory 10, research 5, characters 4, agent runtime 3, tools 2, memory v2 2, rpg 1) | ≈27 | 0 |
| Module-level package cycles (AL002) | 0 | 0 |
| Reciprocal package pairs at any import scope (function-level imports hide them from AL002): `chat↔agent_runtime`, `chat↔rpg`, `agent_runtime↔assistant_tools` | 3 | 0 |
| `app.*` packages and files the layer policy doesn't cover: `app.models`, `app.data`, `app.testing` (empty), loose files such as `tts_http_client.py` and `voice_debug.py`, plus the stale `app.hermes` entry | ≥ 4 + loose files | 0 |
| Packages in a feature tier with no `feature.py`, so no `depends_on` to check against (`assistant_memory_v2`, `replay`) | 2 | 0 |
| String-keyed runtime hooks (`FeatureModule.hooks`, used by assistant tools and by characters for image's avatar hooks) | 3 specs in 2 modules | 0 (replaced by typed ports) |
| Tools for specific apps defined in the kernel catalog (`_DEFAULT_CAPABILITIES` in `app/capabilities/registry.py`: `trading.*`, `market.*`, `research.*`). Not counted: `hermes.get_status` and `hermes.get_diagnostics_schema`, which belong to the shared Hermes sidecar service and stay in the kernel, and kernel-generic tools (calendar, home, weather). | 3 families | 0 |
| Feature-specific settings profiles inside `app/platform` (`settings_profile_rpg/podcast/story/voice.py`) | 4 | 0 |
| Module tables named in kernel retention code (`app/persistence/retention.py`: `omnix_agent_runs`, `omnix_agent_run_events`, `omnix_trading_strategy_events`) | 3 | 0 |
| Module repositories inside the kernel `persistence` package (`rpg_narration_event_repository.py`, imported by `retention.py`) | 1 | 0 |
| Tables whose tenant RLS is enabled only by the hard-coded list in `0106_row_level_security.sql` | all tenant tables | historical only; new tables enable their own |
| Tables (215) with a declared owner (frozen historical map or derived) | 0 | 215 |
| Migration files in the kernel directory. Versions are full filename stems; 17 numeric prefixes are reused, and the highest is `0126`. By filename, 36 are trading, 24 RPG, 18 agent, 15 memory and 10 audiobook. Some files, such as `0007_remaining_modules.sql`, create tables for several owners. | 146 | kernel-owned and multi-owner historical files only |
| `SCHEMA_KNOWN` hand-set to the newest migration | hand-edited | derived |
| Feature-specific clients in the shared web `api/` folder (12 `rpg*`, 3 `hermes*`) | 15 | 0 |
| Generated web API types | one 49,267-line `types.ts` | per feature plus core |
| Model server entrypoints in the root of `src/` (`tts_server.py`, `parakeet_stt_server.py`, `parakeet_stt_runtime.py`, `nemotron_eou_stt_server.py`) | 4 | 0 |
| Loose `.py` modules in the root of `src/app/` (besides `__init__.py`) | 13 | composition files only |
| Tracked runtime data in the source tree (`src/app/data/sessions.json`, `voice_clones.json`) | 2 | 0 |
| Central files hand-edited to add an app | not measured (today at least `layers.toml`, `feature_catalog.py`, `migrations.py`, `modulesManifest.ts`) | 2 |

What the enterprise roadmap already delivered, and this roadmap builds on:

- `FeatureModule` with routers, jobs, workers, scheduled tasks, repositories, hooks, outbox consumers, settings, permissions and lifecycle;
- the lazy feature catalog with `depends_on` validation;
- the web module manifests (`defineModule`), with the view API firewall and the feature-boundary test (WP-9.7);
- `layers.toml` with `feature_contract_module = "contracts"`;
- the ownership rules for platform-table SQL and blob-store construction;
- migration discipline (AL014) and the ratchet.

---

## 3. Rules of engagement

1. **The invariants from the enterprise roadmap (its §1.1) and from [AGENTS.md](../AGENTS.md) still hold.**
   - Profiles are ceilings, not grants.
   - Approval policy never expands issued capabilities.
   - PostgreSQL is authoritative for recovery decisions.
   - Research never gains trading execution authority.
   - No restructuring WP may change authority, approval or order behaviour as a side effect.
2. **Behaviour stays the same.** A WP changes where code lives and how it is reached, not what it does. These must not change unless a WP names the change explicitly:
   - the OpenAPI document (`npm --prefix src/apps/web run api:check`);
   - the characterization goldens (`chat-live-sse-turn`, live voice, `rpg-production-turn`);
   - the tool-catalog golden (PA-1.4);
   - persisted settings documents;
   - the transaction boundaries of existing reactions.
3. **Ratchet.** Every PR leaves the lint and metric baselines equal or better, and lowers them when it removes violations.
4. **Moves are separate from edits.** A file move is its own commit, made with `git mv`, with no content changes. Add bulk-move commits to `.git-blame-ignore-revs`.
5. **Validation is local.** Run:
   - the focused tests;
   - `ruff check` on the changed paths;
   - `python scripts/architecture_lint.py --check`;
   - the architecture gates (`scripts/run_architecture_gates.py`);
   - the web `test`, `typecheck` and `api:check` scripts when web code changes.

   Do not wait on GitHub Actions during roadmap work.
6. **Log decisions.** Deviations go to [DECISIONS.md](roadmap/DECISIONS.md) under their `PA-` id. Status goes to §7 of this file.
7. **PR size.** Aim for about 1,500 changed lines or fewer, excluding pure moves and generated files.

---

## 4. Program structure

```
PA-0 decision + guardrails
  ├─► PA-1.3 step 1 (ports mechanism) ─► PA-1 rest ─► PA-3 capability ports ─────────────┐
  └─► PA-2 modules own contributions ─► PA-4.1–4.4 recipes (built and tested) ───────────┴─► PA-6 certification (drills)

merge of refactor-audit ─► PA-5.1, PA-5.2 (model servers, packages with no clear home, runtime data)
PA-1 to PA-4 + merge ─► PA-5.3–5.5 decision gates
Track R (RPG bounded contexts): after WP-8.6; runs on its own schedule; gates nothing above.
```

- PA-0 starts now.
- PA-1.3 step 1 (the `contributions` mechanism) lands before PA-1.1, which uses it. The rest of PA-1 and all of PA-2 can run in parallel.
- Memory work is done last, in PA-3.2, after the owner's memory v2 live switch, which follows the merge of `refactor-audit` to `main`. Until then, no WP builds a port for memory v1 code.
- The recipes (PA-4.1 to PA-4.4) need PA-1 and PA-2, not PA-3. Only the certification drills (PA-6) wait for PA-3, including memory.
- PA-5.1 and PA-5.2 need only the merge of `refactor-audit` to `main`, because moves conflict with open branches. Don't land them while a WP-12.1 certification measurement is running.
- The decision gates PA-5.3 to PA-5.5 wait for PA-1 to PA-4 and the merge.
- Track R improves RPG maintainability but doesn't serve the add-an-app goal. It does not gate PA-5 or PA-6.

---

## 5. Work packages

### Phase PA-0 — Decision and guardrails

#### PA-0.1 — ADR-0016: platform tiers and module boundaries

- **Goal:** record §1 as an accepted ADR, so later WPs cite a decision rather than this document.
- **Steps:**
  1. Write `docs/architecture/ADR-0016-platform-tiers.md`. It covers:
     - the tiers and how a module declares its tier;
     - the one-direction contract rule and what counts as a contract;
     - no app-to-app imports;
     - events versus ports (rules 5 and 6);
     - contributions over central lists;
     - the "two hand-edited files" goal and what counts as generated;
     - the module anatomy.
  2. Record the rejected alternatives from §6.
  3. Link the ADR from `docs/ARCHITECTURE.md` and the FeatureModule guide.
- **Acceptance:** the owner accepts the ADR (human gate).

#### PA-0.2 — Declared tiers and a one-direction contract rule

- **Goal:** the lint gets each module's tier from the module itself, covers every `app.*` package, and rejects contract imports that go against `depends_on`.
- **Design decisions:**
  - **Tier field.** Add `tier: Literal["platform", "app"]` to `FeatureModule` as a required field with no default, placed right after `title` (neither `id` nor `title` has a default). Set it in every `feature.py`:
    - **platform:** chat, assistant-memory, characters, companion-activity, voice, live-voice, live-speech, image, assistant-tools, agent-runtime, research.
    - **app:** rpg, the RPG Hermes feature, trading, audiobook, story, desktop-companion, character-interactions.
  - **How the lint maps code to a module.** The lint statically reads the catalog and the `tier` and `depends_on` of each feature. A package's module is the feature whose `feature.py` lives in it or in its parent package.
  - **Kernel and shared-service lists.** Those lists in `layers.toml` stay. They change only when the platform changes.
  - **Packages with no `feature.py`.**
    - `assistant_memory_v2` counts as part of the `assistant-memory` module until PA-3.2 merges the two.
    - `replay` counts as part of `rpg` and moves into RPG in PA-1.5.
    - These two are the only transitional entries, in a `[package_modules]` table in `layers.toml`. The table must be empty once PA-1.5 and PA-3.2 are done.
  - **Every `app.*` package and loose file must be covered:**
    - `app.models` → shared services;
    - `app.testing` (empty) → delete;
    - `app.data` → runtime data, handled in PA-5.2 and excluded from code analysis;
    - loose files → the tier of their owner, as found by reading each file.

    An uncovered package or file is a lint error. Remove the stale `app.hermes` entry.
  - **Contract imports.** Accept `<pkg>.contracts` and `<pkg>.contracts.*`.
  - **Direction.** `declared_contract_dependency` accepts only `target in source.depends_on`. Remove the reverse-direction clause.
  - **No app-to-app contracts.** Apps never import another app's contract.
  - **Baseline.** Re-seed it once, in the same PR, so the newly visible violations (the ≈27 reverse imports) are recorded rather than failing. The PR lists them.
- **Tests:** synthetic regressions in the lint test suite:
  - a reverse-direction contract import fails;
  - an app→app contract import fails;
  - an import from a `contracts/` subpackage passes when declared;
  - an uncovered `app.*` package fails;
  - a new feature declaring `tier="app"` is classified without editing `layers.toml`.
- **Acceptance:** `architecture_lint.py --check` passes on the re-seeded baseline, and the policy digest changes exactly once.

#### PA-0.3 — Metrics for this roadmap

- **Goal:** every row in §2 is a ratchet metric in `metrics-baseline.json`.
- **New metrics:**
  - `reverse_contract_imports`
  - `any_scope_package_cycles`
  - `app_to_app_imports`
  - `uncovered_app_modules`
  - `composition_imports_outside_composition`
  - `string_runtime_hooks`
  - `kernel_tools_naming_apps`
  - `platform_feature_specific_files`
  - `module_repositories_in_kernel`
  - `web_feature_clients_in_shared_api`
  - `src_root_service_entrypoints`
  - `tracked_runtime_data_in_src`
- **Metrics that need later machinery** are added by the WP that builds it: `tables_without_owner`, `historical_owner_map_additions`, `kernel_named_module_tables` and `cross_module_sql` in PA-2.2 (the ownership map and AL016); `app_migrations_in_kernel_dir` in PA-2.3; `tables_without_isolation_or_exemption` in PA-4.1 (a PostgreSQL check).
- **New lint rule AL015:** reciprocal package dependencies at any import scope, including function-level imports. AL002 stays module-level; AL015 catches the cycles that lazy imports hide. Pairs with composition are excluded, because an import into composition is already an AL001 violation.
- **Acceptance:** the metrics report the values in §2, and AL015 is baselined at its measured value.

---

### Phase PA-1 — Dependency direction

#### PA-1.1 — Kernel and shared services stop importing modules

- **Addresses:** `assets→image`, `providers→image`, `providers→rpg`.
- **Depends on:** PA-1.3 step 1 (the `contributions` mechanism).
- **Steps:**
  1. Read each import.
  2. Move the type it needs into kernel or shared contracts, or add a port (PA-1.3 mechanism) that the owning module binds.
- **Acceptance:** AL001 entries whose source is in the kernel or shared services: 0.

#### PA-1.2 — Nothing outside composition imports `runtime_composition`

- **Addresses:** 8 imports from chat, characters, assets, assistant_memory, providers and research.
- **Design decision:**
  - A module receives its collaborators through `FeatureContext.services` (`KernelServices`) or through a port.
  - If a collaborator is missing from `KernelServices`, add it there as a typed field.
  - Do not add a new service locator.
- **Acceptance:** `composition_imports_outside_composition`: 0.

#### PA-1.3 — Typed ports replace string hooks; chat stops importing its dependents

- **Addresses:**
  - the reverse imports in `app.chat`;
  - the `chat↔agent_runtime` and `chat↔rpg` cycles;
  - `FeatureModule.hooks` and `app/runtime/hooks.py`. That registry is string-keyed, process-global, allows one handler per name, and silently returns a default when a hook is missing.
- **Design decisions:**
  - **One mechanism.** `FeatureModule.contributions: tuple[ContributionSpec, ...]` replaces `FeatureModule.hooks`; the two never coexist. A `ContributionSpec` holds:
    - the port type: a `Protocol` from the consuming module's contract;
    - a factory taking `FeatureContext`;
    - a `priority: int`.
  - **Port cardinality.** Each port declares its cardinality: exactly one, at most one, or many.
    - **Module-implemented ports** are *at most one* or *many*. The consumer handles absence explicitly, so the feature-disable matrix still passes. Catalog validation rejects a `ContributionSpec` from a module that targets an *exactly one* port.
    - **Exactly one ports** are bound only by the composition layer, for example a kernel service implementation. A missing binding is a startup error, never a silent default.
    - Composition also fails at startup if an *at most one* port has two implementations.
  - **Ordering.** Implementations of a *many* port are ordered by `(priority, module id)`. The order is deterministic and tested. `depends_on` depth is not an order.
  - **Chat owns the prompt, in two separate steps:**
    1. Chat defines `PromptContextContributor`, and contributors move to it while **keeping today's budgeting**: each contributor still sizes its own context exactly as it does now.
    2. A separate step moves budget allocation into chat. Contributors then return candidates with size estimates, and chat allocates and truncates. This step is proved byte-identical by its own golden comparison.

    Other chat ports include `TurnToolProvider`, `ResearchRunner` and `CharacterResolver`.
  - **Shared types.** Transcript and session types that dependents need live in `app.conversation`, a kernel package (WP-2.9). Dependents import them from there, not from chat.
- **Steps:** one PR each:
  1. Add `contributions` and the binder.
  2. Port the existing hooks: the assistant-tools capability hook, and characters' `image.character_avatar.*` hooks, which become an image-owned port that characters implements.
  3. Chat dependents, keeping today's budgeting, in this order: research, characters, assistant tools / agent runtime, RPG.
  4. Move prompt budget allocation into chat (its own PR, with its own byte-identical golden comparison).
  5. Delete `hooks.py` and `FeatureModule.hooks`.

  Memory is not ported here; see PA-3.2.
- **Tests:**
  - the characterization goldens are unchanged, and the prompts they capture are byte-identical (ordering and budget preserved);
  - for each port, the feature-disable matrix (WP-2.2): chat serves a turn without the contributor;
  - startup fails for an unbound *exactly one* port, and for an *at most one* port with two implementations;
  - catalog validation rejects a module contribution that targets an *exactly one* port.
- **Acceptance:**
  - `string_runtime_hooks`: 0;
  - `reverse_contract_imports` in `app.chat` is 0, except the memory imports left for PA-3.2;
  - AL015 has no pair that includes chat.

#### PA-1.4 — Apps contribute tools; the agents capability never imports apps

- **Addresses:**
  - `_DEFAULT_CAPABILITIES` in `app/capabilities/registry.py`, which defines app tools (`trading.*`, `market.*`, `research.*`) in the kernel;
  - `assistant_tools→trading` (4), `agent_runtime→trading` (2), `assistant_tools→research` (1);
  - `agent_runtime↔assistant_tools` (5 / 1).
- **Design decisions:**
  - **Tool declarations.** The owning module declares each tool as a `ToolSpec` through `FeatureModule.tools`. Kernel-generic tools (calendar, home, weather and the like) stay in the kernel catalog until an owner module exists for them.
  - **Availability, not authority.** Declaring a tool makes it *available*. It never grants it. Issuance, approval and execution stay with the capability registry, approval policy and `CapabilityExecutor`, unchanged. Trading tools keep their risk class and authorization gate; the paper-trading authorization stays owned by trading. The `hermes_visible` flag (visibility to the Hermes sidecar) keeps its meaning.
  - **Grants are bound to the definition they were issued for.** When a grant, approval or proposal is issued, it records a hash of that capability's definition. At check and execute time, the executor recomputes the hash from the running catalog. It refuses the call if the capability is missing or its hash differs.
    - **The hash is defined by exclusion.** It covers every `Capability` field **except** an explicit display-only list: `name`, `description`, `category`, `aliases`, `assistant_visible` and `hermes_visible`. So it includes `id`, `namespace`, `execution_zone`, `effect`, `risk`, `scope_type`, `approval_policy`, `requires_confirmation`, `destructive`, `network_required`, `credential_required`, `requires_connection`, `audited`, `enabled`, `provider` and the input and output schemas, and any field added later is covered automatically.
    - `provider` is in the hash because, for MCP and browser tools, it names the backend that serves the tool (for example `"agent-browser"`). Changing the backend must invalidate existing grants.
    - A test fails if a new `Capability` field is added to the display-only list without a reviewed comment.
    - This fails closed when a tool disappears (feature disabled or module retired).
    - It also fails closed when a definition changes, for example a risk-class change.
    - It tolerates processes that legitimately run different catalogs. That happens during a rolling upgrade (WP-6.7), and when processes pick up an MCP policy change at different moments, because `_capability_registry_for` reloads per process on a new policy signature.

    Grants issued before this WP have no hash. They are refused and must be re-issued; record the count in the PR. This includes the grants of durable agent tasks still running across the deploy.
    - **Recovery handles those refusals.** A refused call reaches the run as an ordinary capability denial: the run records it and requests approval again, through the normal approval flow. It neither crashes nor retries silently.
    - The deploy runbook still recommends deploying this WP when no durable agent runs are active, to avoid asking for approvals again.
  - **Catalog digest is a diagnostic only.** Each process reports a whole-catalog digest with its health. A mismatch across processes is surfaced in diagnostics and alerts, but never refuses an execution.
  - **Agent packaging.** `agent_runtime` and `assistant_tools` form one agents capability. Either merge them, or route the 5 `agent_runtime→assistant_tools` imports through `assistant_tools.contracts` and remove the reverse import. Record the choice in DECISIONS.md.
- **Tests:**
  - a **permanent** tool-catalog golden covering names, schemas, risk classes, required approvals and visibility flags, for both "all features" and "trading disabled";
  - a stored grant for a removed tool is refused;
  - a stored grant whose capability changed risk class or `scope_type` is refused;
  - a durable agent run holding a pre-WP grant receives a denial and re-requests approval after a restart;
  - a grant executes on a worker whose whole catalog differs only in unrelated tools (a rolling-upgrade or MCP reload window), and the diagnostic records the mismatch.
- **Acceptance:**
  - `kernel_tools_naming_apps`: 0;
  - the agents capability imports no app;
  - AL015 has no pair that includes `agent_runtime`.

#### PA-1.5 — Remaining module edges

| Edge | Resolution |
|---|---|
| `replay→rpg` (6) | `app/replay` only adapts RPG (`RpgReplayPersistenceAdapter`). Move it into RPG. |
| RPG Hermes feature depends on `rpg` | Both are app-tier features in one package tree. Treat them as one app for the app-to-app rule, through a `parent` field on the Hermes feature. |
| `desktop_companion→companion_activity` (5), `→chat` (3), `→assistant_memory_v2` (3), `→assistant_memory` (1) | App→platform imports: route through each capability's contract and declare the missing `depends_on`. Memory imports wait for PA-3.2. |
| `trading→research` (4) | Declare `research` in trading's `depends_on` and import its contract. Research output stays evidence only (the AGENTS.md trading rule). |
| `rpg→image` (2), `characters→image` (1) | Declare `image` and import its contract. |
| `assistant_memory→assistant_memory_v2` (2), `chat→assistant_memory_v2` (2), `assistant_memory→assistant_tools` (1) | Left for PA-3.2. |

- **Acceptance:**
  - AL001 is 0, apart from the memory entries assigned to PA-3.2;
  - `app_to_app_imports` is 0;
  - AL015 is 0.

---

### Phase PA-2 — Modules own what they contribute

#### PA-2.1 — Dissolve `app/platform`; settings sections move to their owners

- **Addresses:** `settings_profile_rpg.py`, `settings_profile_podcast.py`, `settings_profile_story.py` and `settings_profile_voice.py` in `app/platform`. Today `settings_profile_models.py` aggregates them.
- **Design decisions:**
  - **Declaration.** Each module declares its settings section in its `declarations.py` (§1.2), which imports kernel code only. A lint check enforces this.
  - **Composition imports declarations, not features.** The composition root imports `app.<package>.declarations` directly, by convention, for **every catalog module, enabled or not**, plus the retired tombstones (PA-4.3). It passes the collected sections to the settings service. It never imports a disabled module's `feature.py`, and the settings kernel never reads the catalog. This follows the same rule as the schema (PA-2.3).
  - **Disabled sections are kept.** A disabled feature's section stays present and is kept unchanged across saves. It is never dropped.
- **Steps:**
  1. Move each profile section to its owner.
  2. Move the rest of `app/platform` to its owners:
     - settings control and repositories → `app/settings`;
     - diagnostics and reports → `app/observability`;
     - the audio cache → speech;
     - `voice_cloning_defaults` → voice;
     - `legacy_sessions` → its owner, or delete it if unreachable.
  3. Delete the empty package.
- **Tests:**
  - persisted settings documents load and round-trip byte-for-byte (fixture from current settings);
  - with a feature disabled, saving another section preserves the disabled feature's section exactly;
  - in a clean interpreter, importing every `declarations.py` loads no module outside the kernel and the module's own `declarations` (checked through `sys.modules`);
  - with every feature disabled, building the settings profile imports no `feature.py`;
  - the OpenAPI document is unchanged.
- **Acceptance:** `platform_feature_specific_files` is 0, and `app/platform` is removed.

#### PA-2.2 — Derived table ownership and a SQL ownership rule

- **Goal:** every table has exactly one owner, and only the owner's code and migrations touch it. New tables get their owner derived; the historical tables get theirs from a frozen map that no new app ever edits. This generalizes AL006 to all 215 tables.
- **Why ownership of historical tables can't be fully derived:**
  - **Some files create tables for several owners.** For example, `0007_remaining_modules.sql` creates provider, prompt, research, report, module-record and runtime tables, and one file can't live in several module folders.
  - **Filename tokens aren't module ids.** `agent`, `memory` and `companion` stand for `agent-runtime`, `assistant-memory` and `companion-activity`. Many tokens aren't modules at all: `legacy`, `cutover`, `typed`, `row`, `data`, `device`, `remaining` and others.
- **Design decisions:**
  - **Historical owners are a frozen map.** `resources/architecture/historical-table-owners.json` maps every table created by a migration that stays in the kernel folder to its owning module id (or `kernel`), and to its tenant status: `rls` (covered by `0106`) or `tenant_exempt`, with a reason. It is reviewed by hand once, in this WP. After PA-2.3 the lint **rejects any new entry**: a table created by a new migration must not appear in it. A new app never touches the map.
  - **New tables get a derived owner.** A table created by a migration in a module's `migrations/` folder is owned by that module.
  - **Generated, checked view.** `resources/architecture/table-owners.json` combines the frozen map and the derived owners. It is generated by `scripts/architecture_metrics.py --update` and verified by the lint. Nobody edits it by hand.
  - **AL016, SQL ownership.** In a module's Python code, a SQL string that references a table owned by another module is a violation, where "references" means a table position: after `FROM`, `JOIN`, `INTO`, `UPDATE`, `TABLE` or `REFERENCES`. Kernel tables are reachable only through kernel repositories. Bare words such as `jobs` or `sessions` outside table positions are never matched.
  - **AL016 covers migrations too.** A migration in module X's folder that runs `ALTER`, `DROP`, `CREATE INDEX … ON`, `INSERT`, `UPDATE` or `DELETE` against module Y's table is a violation. Two exceptions:
    - A foreign key that `REFERENCES` a kernel table is allowed.
    - **Kernel registration tables.** Modules may register rows in a named list of kernel tables, kept in the lint configuration. Today the list holds only `omnix_retention_policies`. Only `INSERT … ON CONFLICT DO NOTHING` is allowed there, and only for record types the same module declares in its `declarations.py`. Any other statement against a registration table, or a row for another module's record type, is a violation.
  - **Kernel code that names module tables uses contributions.** A kernel service can't route a fix "through the owner's repository" the way a module can. Today the kernel retention worker (`app/persistence/retention.py`) names `omnix_agent_runs`, `omnix_agent_run_events` and `omnix_trading_strategy_events`, and it imports an RPG repository that lives in the kernel package.
    - **The database row stays authoritative.** Retention horizons live in `omnix_retention_policies`, whose `retention_days`, `enabled` and `metadata.maintenance_only` operators can edit. Code only maps each record type to its delete handler. A module therefore declares a `RetentionDeclaration` in its `declarations.py`, containing:
      - the record type;
      - a **delete handler**, a function in the module with the signature `(connection, days, batch) -> int`. A handler is needed rather than a (table, age column) pair, because agent retention keeps milestone events (`AGENT_EVENT_KEEP_PREFIXES`);
      - a **default** horizon.
    - **Defaults are only seeds.** The module's own migration seeds the `omnix_retention_policies` row with the default horizon using `INSERT … ON CONFLICT (record_type) DO NOTHING`, so values operators have already set are never overwritten.
    - **The kernel worker only reads.** Composition collects the declarations and passes them to the retention worker. The worker reads the database rows as it does today and calls the declared handler for each record type. A declared record type with no row is reported, not invented.
    - **Handlers delete only their own tables.** AL016 applies to a handler as to any module code.
    - **Move the RPG repository.** `app/persistence/rpg_narration_event_repository.py` moves into RPG, and its delete handler is contributed through RPG's retention declaration.

    Any other kernel code that names module tables gets the same treatment, through a declaration or a port.
  - **AL016 covers kernel code too.** SQL in a kernel package that references a module-owned table is a violation. A kernel package that contains a module's repository is a violation. This catches what "kernel tables only through kernel repositories" missed.
- **New metrics:**
  - `tables_without_owner`
  - `historical_owner_map_additions`
  - `kernel_named_module_tables`
  - `cross_module_sql`
- **Steps:**
  1. Write and review the historical map.
  2. Generate the combined file.
  3. Add AL016 for code and migrations, with a baseline.
  4. Drive the baseline to zero, routing each fix through the owner's repository or contract.
- **Tests:** AL016 synthetic regressions:
  - a table position matches;
  - a column or prose use of the same word does not;
  - a CTE alias does not;
  - a migration altering another module's table fails;
  - a new kernel-folder migration that adds a row to the historical map fails.
- **Acceptance:**
  - every table has an owner, either historical or derived;
  - the historical map is frozen (lint-enforced);
  - `cross_module_sql` is 0.

#### PA-2.3 — Migrations live with their owning module

- **Design decisions:**
  - **Discovery by filesystem convention, in exactly three places.** The runner (`app/persistence/migrations.py`) never reads the feature catalog, so the kernel imports no feature. It finds every module's migrations, enabled or not: a schema is a release-level artifact, not a feature flag. It reads only:
    1. the kernel folder `src/app/persistence/migrations/`;
    2. a `migrations/` folder that sits next to a `feature.py`;
    3. the retired-module folders `src/app/persistence/retired/<python_package>/migrations/` (PA-4.3).

    A `.sql` file in any other `migrations/` folder is a lint error. For example, `src/app/rpg/persistence/migrations/` holds RPG save-format migrations (`v1_to_v2.py` …), and a `.sql` file there must never silently become a schema migration.
  - **Versions.** A version is the full filename stem, as it is today (`version=path.stem`). Numeric prefixes are already reused (17 of them), so a stem must be unique across all directories. Ordering stays lexical by stem. A new migration takes a number above the current highest, so cross-directory ordering is the same as today.
  - **`SCHEMA_KNOWN`** is computed as the highest discovered stem and is no longer hand-edited. `SCHEMA_MIN_CONTRACT` stays hand-set: it is a deliberate compatibility decision made only with contract migrations, and adding an app never changes it.
  - **Identity across moves.** AL014 and `migration-checksums.json` identify a migration by stem and checksum, not by path, so moving a file is not a change. `_CANONICAL_MIGRATION_CHECKSUMS` and `_LEGACY_MIGRATION_CHECKSUMS` stay keyed by stem.
  - **Tables stay where they are.** Existing tables stay in the `public` schema under their current names (see §6).
- **New metrics:**
  - `app_migrations_in_kernel_dir`
- **Steps:**
  1. Land discovery, the computed `SCHEMA_KNOWN` and stem-based AL014. Tests cover a duplicate stem across directories, a moved but unchanged file, an unchanged computed `SCHEMA_KNOWN`, and a stray `.sql` file under a non-schema `migrations/` folder (a lint error).
  2. From then on, new migrations go into module directories.
  3. In one pure-move PR, move each existing migration whose statements touch only one module's tables (per the PA-2.2 map) into that module's folder. Migrations that touch several owners, such as `0007_remaining_modules.sql`, or only kernel tables stay in the kernel folder permanently.
- **Tests:**
  - a fresh database migrates to the same schema dump before and after the move;
  - an already-migrated database reports nothing pending;
  - the rolling-upgrade rehearsal (WP-6.7) passes.
- **Acceptance:**
  - `app_migrations_in_kernel_dir` is 0, meaning no single-owner app migration remains in the kernel folder; multi-owner historical files are listed and frozen;
  - `SCHEMA_KNOWN` is derived.

#### PA-2.4 — Web: each feature owns its API clients and generated types

- **Design decisions:**
  - **Route ownership without changing OpenAPI.** The gateway already knows which feature mounted each route. `scripts/export_gateway_openapi.py` also writes a generated `route-owners.json` (operation → feature id), built from the feature registry. The OpenAPI document is unchanged; no tags are added.
  - **Backend modules per web feature.** Each web manifest declares `backendModules: readonly string[]`. Web feature folder names don't match backend ids (for example `storyteller`, `podcast`, `voice-cloning`, `conversation-production`). The mapping lives in each feature's own `module.ts`, not in a central list.
  - **Shared schemas.**
    - A schema reachable from more than one backend module's operations is *defined* in `api/generated/core.ts`. A schema reachable from only one module is defined in that feature's generated file.
    - Each feature's `generated.ts` **re-exports every schema its operations reach**, shared ones included. Hand-written feature code imports schemas only from its own generated file, never from `core.ts` directly; an ESLint rule enforces this.
    - So when a new app starts using a schema and the definition moves into `core.ts`, only generated files change. No hand-written import elsewhere breaks.
- **Steps:**
  1. Move the 12 `rpg*` and 3 `hermes*` client files (with their tests) from `src/apps/web/src/api/` into `features/rpg/api/`. `api/` keeps transport, `http.ts`, `fetchPipeline.ts`, `errors.ts`, `authClient.ts`, `jobProgress.ts`, `schemas` and the core generated client.
  2. `api:types` generates `features/<feature>/api/generated.ts` and `api/generated/core.ts` from `openapi.json` plus `route-owners.json`. `api:check` covers every generated file.
  3. Add ESLint boundary rules:
     - a feature imports `api/` transport and its own `api/`, never another feature's;
     - hand-written feature code imports generated schemas only from its own `generated.ts`.
- **Acceptance:**
  - `web_feature_clients_in_shared_api` is 0;
  - `api/generated/types.ts` is removed;
  - the OpenAPI document is unchanged;
  - web `test`, `typecheck`, `lint` and `api:check` pass.

#### PA-2.5 — Tests grouped by module

- **Design decision:** don't move the whole test estate at once.
  - New tests go to `src/tests/<python_package>/`, named after the module's Python package (`agent_runtime`, `assistant_memory`), not its feature id. Feature ids such as `agent-runtime` can't be Python package names, and `src/tests/rpg/` already exists as a package.
  - `src/tests/kernel/`, `e2e/`, `characterization/` and `support/` stay cross-cutting.
  - Existing tests move when their module's work touches them.
- **Steps:** add `scripts/test_module.py <module_id>`. It maps the feature id to its Python package through the catalog, then runs `src/tests/<python_package>/` plus the module's characterization goldens.
- **Acceptance:** every catalog module has a test directory, and `test_module.py` runs for each one.

---

### Phase PA-3 — Platform capabilities behind ports

#### PA-3.1 — Every platform capability publishes a contract

- **Goal:** apps reach each capability only through its contract: typed `Protocol`s and DTOs, versioned by additive change.
- **Steps:** for each capability (chat, characters, companion activity, speech, image, agents, research):
  1. Inventory what apps import today.
  2. Add the missing contract types.
  3. Turn on mypy strict for the contract (extending the WP-1.6 strict patterns).

  Memory gets its contract in PA-3.2.
- **Acceptance:** contracts are strict-typed, and apps import no platform module other than its contract (enforced by PA-0.2).

#### PA-3.2 — Memory: one implementation, one contract, its chat port

- **Depends on:** the owner's memory v2 live switch, which follows the merge to `main`.
- **Steps:**
  1. After the switch, adapt any v1 code that is still reachable to v2, or delete it.
  2. Merge `assistant_memory` and `assistant_memory_v2` into one `memory` capability with one contract.
  3. Memory implements chat's `PromptContextContributor` (PA-1.3), which removes the remaining reverse imports in `app.chat`.
  4. Route desktop companion's memory imports through the contract.
  5. Empty the `[package_modules]` table.
- **Tests:**
  - the chat golden prompts stay byte-identical, or any change is the documented result of the switch itself;
  - the memory v2 suites pass.
- **Acceptance:**
  - one memory package;
  - `reverse_contract_imports` is 0;
  - AL001 is 0.

#### PA-3.3 — Speech capability

- **Steps:**
  1. Group voice, live voice and live speech under one speech contract: STT/TTS session ports and the realtime transport.
  2. `live_voice→chat` (12 imports, already declared) goes through the chat ports from PA-1.3.
- **Acceptance:** the live voice goldens are unchanged, and speech imports chat only through its contract.

#### PA-3.4 — Deferred reactions through events

- **Scope:** only reactions that already tolerate running later. That means the reaction:
  - currently runs after the producer's commit, in a background task or job, or a later request;
  - is idempotent, or can be made idempotent.

  Reactions that run inside the producer's transaction move to a port called within the producer's unit of work, not to an event. This keeps rule 2 (transaction boundaries unchanged).
- **Steps:**
  1. Inventory the direct cross-module reaction calls, and classify each one as same-transaction or deferred.
  2. Turn each deferred reaction into a typed event in the producer's contract, delivered through the outbox (WP-5.3).
  3. Turn each same-transaction reaction into a port.
- **Acceptance:**
  - no module calls another module's service directly to react to a state change;
  - each event consumer has an idempotency test (the same event delivered twice);
  - each moved reaction has a test asserting its original timing (same transaction, or after commit).

---

### Phase PA-4 — Adding and retiring an app are recipes

- **Depends on:** PA-1 and PA-2. It does not depend on PA-3, so the memory switch doesn't block it. The conformance test (PA-4.1) baselines modules that PA-3 hasn't finished yet, and the baseline must be empty before PA-6.

#### PA-4.1 — Module conformance test

- **Checks:** every catalog module has:
  - `feature.py` exporting `FEATURE`, with `tier` set;
  - a contract;
  - migrations only in its own directory, touching only its own tables;
  - its settings section and retention declarations in a kernel-only `declarations.py`, with each declared record type seeded in `omnix_retention_policies` by its own migration;
  - a test directory named after its Python package;
  - **tenant isolation, secure by default**, checked on PostgreSQL after migrating a fresh database. Every table that a module's migrations create must be one of these:
    - **isolated:** row-level security enabled **and forced**, plus a `tenant_isolation` policy. When the table has `workspace_id`, the policy is `workspace_id = current_setting('omnix.workspace_id', true)` with the `omnix.system` bypass, the same as `0106`. A child table without its own `workspace_id` must use one fixed pattern: `USING (EXISTS (SELECT 1 FROM <parent> p WHERE p.<key> = <child>.<foreign key>))`, with the same `WITH CHECK`. Here `<parent>` is itself isolated with forced RLS, so the parent's policy applies inside the subquery, and `<foreign key>` is a declared foreign key to `<parent>.<key>`.
      - The check reads `pg_policies` and the catalog. It confirms the expression matches the pattern, the foreign key exists, and the parent is isolated, recursively for grandchildren.
      - Any other expression fails, including a placeholder such as `USING (true)`.
      - The scaffold also generates an example child table, and the PA-4.2 second-tenant read test covers it;
    - **exempt:** carries `COMMENT ON TABLE … IS 'omnix:tenant-exempt: <reason>'`, and the check lists every exemption in its report.

    The check covers every table, whether or not it has a `workspace_id` column, so a new table without isolation fails whichever module owns it. Historical tables take their status from the frozen PA-2.2 map: `0106` covers the isolated ones, and the map records the exempt ones, so they don't each need a new comment;
  - a web manifest with `backendModules`, when it serves UI routes.
- **Acceptance:** the test runs in the unit suite and passes for every module.

#### PA-4.2 — Scaffold

- **Steps:** add `python scripts/new_module.py <id> --tier app|platform [--web]`. It generates:
  - the anatomy in §1.2, with an example route, durable job, settings section, retention declaration (with its delete handler and the seed row in the migration) and permission;
  - an example table migration that has a `workspace_id` column and, in the same migration, runs `ENABLE ROW LEVEL SECURITY` and `FORCE ROW LEVEL SECURITY` and creates the tenant policy with the same expression `0106_row_level_security.sql` uses. It also creates an example child table with the fixed `EXISTS` parent policy. A new app never edits a kernel migration to get RLS;
  - the test directory;
  - the web feature with `module.ts`;
  - the catalog line and the web manifest line.

  It then runs the generators (OpenAPI, web types, checksums, ownership file) and prints the files changed outside the module, split into hand-edited and generated.
- **Tests:** a recipe test scaffolds a module into a temporary copy, then:
  1. boots the gateway with the module enabled, calls its route, runs its job and reads its setting, then checks that a second tenant can't read or write the first tenant's rows in either the parent or the child table;
  2. disables the module and checks that every gate still passes;
  3. asserts that the only hand-edited files outside the module are the 2 registration files.
- **Acceptance:** the recipe test passes.

#### PA-4.3 — Retiring a module

- **Why:**
  - **Migrations.** Deleting a module's files breaks databases that already applied its migrations. The runner rejects an unknown *contract* migration (`MigrationDriftError`), and the module's tables would be left without an owner.
  - **Durable work in flight.** A module also leaves durable work behind: queued or running jobs for its job handlers, scheduled tasks, undelivered outbox events for its consumers, and pending approvals or proposals for its tools. Recovery would try to resume work that no longer has a handler. PostgreSQL is authoritative for recovery decisions (AGENTS.md), so that work must reach a final state in the database before the code goes.
- **A draining state.** Disabling a feature unregisters its job handlers, so "disable, then wait for running jobs" would only wait out the timeout. Retirement therefore needs a state between enabled and disabled. Add a durable module state in a kernel table (`active`, `draining`, `retired`), read by every process. In `draining`:
  - the module's routes reject new work (`503` with `Retry-After`);
  - its scheduled tasks don't start new runs;
  - new job submissions for its types are refused, **except** follow-up jobs submitted from inside a running job of the same module. A follow-up is identified by the submitting job's execution context and recorded as the new job's parent. It is accepted until the drain timeout, so a handler that queues its own next step doesn't fail its parent;
  - its job handlers and outbox consumers **stay registered**, so in-flight work, including accepted follow-ups, can finish.
- **Which source wins.** A feature's on/off setting lives in runtime config; the module state lives in PostgreSQL.
  - `draining` and `retired` in the database **override** the config: a module in either state behaves as described here, even in a process whose config enables it.
  - `active` defers to the config. Turning a feature off in config alone behaves as it does today: its handlers aren't registered in that process, and its jobs wait in the queue.
- **Procedure** (documented and scripted as `scripts/retire_module.py <id>`):
  1. **Refuse** if any other catalog module lists this module in `depends_on`.
  2. **Drain.** Set the module to `draining`. Wait, up to a bounded drain timeout, for its running jobs to finish and its outbox deliveries to be consumed.
  3. **Cancel what's left.** With the handlers still registered, the script records a final state in PostgreSQL for each remaining kind of in-flight work, with reason `module_retired`. It does this through the kernel services, never by deleting rows:
     - **jobs:** cancel running and queued jobs;
     - **outbox:** dead-letter undelivered events for its consumers;
     - **approvals and proposals:** expire the pending ones for its tools;
     - **scheduled tasks:** record their final run state.
  4. **Check.** The script verifies that no non-terminal job, outbox delivery or approval for the module remains, and stops if one does.
  5. **Disable and remove registration.** Set the module to `retired`, disable the feature, and remove its catalog line and web manifest line.
  6. **Tombstone.** Create `src/app/persistence/retired/<python_package>/`, named after the Python package so it can be imported. It holds:
     - the module's `migrations/` folder, moved there. It is still discovered, so every applied version stays known, and the ownership file lists its tables as owned by `retired:<module_id>`;
     - a kernel-only `tombstone.py`, generated by the script, with the settings section stub (so stored values survive) and the module's retired job types, outbox event types and tool ids.

     Composition and recovery read tombstones by convention, with no central list. A later settings migration may drop the stub.
  7. **Optional data deletion** needs the owner's approval (human gate). It is a new contract migration in the tombstone folder that drops the tables, shipped under the normal expand/contract rules. The tombstone stays after it is applied.
  8. **Tools disappear** from the catalog. Stored grants fail closed (PA-1.4).
- **Recovery hardening (part of this WP):**
  - **Fail only retired types.** A job whose type is listed in a tombstone is moved to a terminal failed state with reason `module_retired`, once. The same applies to an outbox event whose type is listed in a tombstone, which is dead-lettered.
  - **Leave other unknown types queued.** Workers claim only the types they have handlers for (`claim_next` filters `job_type = ANY(...)`), so a job of a feature that is disabled, disabled only in some processes, or newer than the claiming worker during a rolling upgrade, simply waits. Recovery never fails it. If such a job stays unclaimed beyond a configured age, an alert fires (`job_unclaimed_too_long`, with type and age). Unknown outbox consumers are treated the same way.
- **Tests:** a recipe test retires the scaffolded module on a database that applied its migrations and holds one queued job, one running job, one undelivered event and one pending approval for it. Afterwards:
  - during draining, the running job **completes** with its handler still registered, including a follow-up job it submits;
  - new submissions from outside the module are refused;
  - a process whose config enables the module still refuses new work while the database says `draining`;
  - the remaining items are terminal, with reason `module_retired`;
  - the runner reports no drift;
  - startup succeeds, and other modules' gates pass;
  - its stored settings values are intact.

  Separately:
  - a job of a retired type is failed once;
  - a job of a type that is merely disabled stays queued and raises the age alert, and runs once the feature is re-enabled;
  - a job of a type known only to a newer gateway stays queued on an older worker;
  - retiring a module that another module depends on is refused.
- **Acceptance:** the recipe test passes. Retirement hand-edits the same 2 registration files, plus the scripted tombstone moves.

#### PA-4.4 — Per-module checks and guide

- **Steps:**
  1. Add `scripts/check_module.py <id>`. It runs the module-scoped lint, mypy on the module, `test_module.py`, and the web tests and typecheck for the feature's web side.
  2. Rewrite the FeatureModule guide as "Adding and retiring an app", built on the two scripts.
- **Acceptance:** the guide's walkthrough works as written.

---

### Phase PA-5 — Physical layout

- **Depends on:**
  - **PA-5.1 and PA-5.2:** only `refactor-audit` merged to `main`, with no other long-lived branches open (human gate: the owner picks the window). Don't land them while a WP-12.1 certification measurement is running.
  - **PA-5.3 to PA-5.5:** PA-1 to PA-4 as well, because they are decisions about the end state.
- **Method:** each move is a pure `git mv` commit, plus an import-rewrite commit produced by `scripts/rewrite_imports.py` (AST-based, idempotent). Both commits go into `.git-blame-ignore-revs`. In the same PR, update `layers.toml`, the feature catalog, Docker and Compose, the launcher, `[production].entrypoints`, the docs and AGENTS.md.

#### PA-5.1 — Model servers into `src/services/`

- **Steps:** move these files into `src/services/{tts,stt,image}/`, each with its existing lock file:
  - `tts_server.py`
  - `parakeet_stt_server.py`
  - `parakeet_stt_runtime.py`
  - `nemotron_eou_stt_server.py`
  - `app/image_service_app.py`
  - `app/image_service_runtime.py`
- **Acceptance:**
  - `src_root_service_entrypoints` is 0;
  - the Compose `gpu` profile and the launcher start every service;
  - the WP-0.5 service-credential tests pass.

#### PA-5.2 — Packages with no clear home; runtime data out of the source tree

- **Steps:**
  1. Move the loose `src/app/*.py` modules into their owners:
     - `errors.py`, `text.py`, `memory_contracts.py` and `memory_policy.py` → kernel packages;
     - `tts_http_client.py`, `tts_stream_audio.py` and `voice_debug.py` → speech;
     - `image_http_client.py` → image;
     - `runtime_document_services.py` → its owner.
  2. Move `src/app/data/sessions.json` and `voice_clones.json` out of the source tree, into the configured runtime data directory, with a one-time copy on startup if they are missing. Remove them from git.
- **Acceptance:**
  - the root of `src/app/` holds only `__init__.py` and composition files;
  - `tracked_runtime_data_in_src` is 0.

#### PA-5.3 — Tier folders (decision gate)

- **Option:** move platform capabilities to `app/platform/<capability>/` (grouped as speech, media and agents), apps to `app/apps/<id>/`, and composition to `app/composition/`.
- **Why it is a gate:** once tiers are declared in `FeatureModule.tier` (PA-0.2), folders add readability but no boundary, and the move touches most imports. Do it only if the owner wants the readability; record the decision either way.

#### PA-5.4 — Web package at the repository root (decision gate)

- **Option:** move `src/apps/web` to `web/`.
- **Trade-off:** this removes the confusion between `src/app` (Python) and `src/apps` (web), but it touches the `npm --prefix` commands, CI, Docker and AGENTS.md. Do it only if the owner wants it.

#### PA-5.5 — Separate Python distributions (decision gate)

- **When:** only on a concrete need that lint enforcement can't meet, for example shipping one app without the others, or conflicting dependencies.
- **Why not otherwise:** a uv workspace adds packaging cost but no boundary beyond what PA-0.2, AL015 and AL016 already enforce.

---

### Phase PA-6 — Certification

#### PA-6.1 — Re-measure and drill

- **Depends on:** PA-1 to PA-4, including PA-3.2 (memory), and PA-5.1 and PA-5.2.
- **Steps:**
  1. Re-measure every metric in §2.
  2. **Add drill.** Someone who did not build the scaffold adds a toy app with a route, a durable job, a table, a settings section and a web workspace, using only the guide. Record the time taken, and the hand-edited and generated files outside the module.
  3. **Retire drill.** Retire the toy app with `retire_module.py` on a database that applied its migrations.
- **Acceptance:**
  - every §2 target is met;
  - each drill hand-edits only the 2 registration files outside the module;
  - the retired app leaves no migration drift;
  - the results are recorded in §7.

---

### Track R — RPG bounded contexts

- **Depends on:** WP-8.6 done. Runs on its own schedule and gates nothing in PA-0 to PA-6.
- **Why:** RPG is about half of all backend Python (≈286k lines, 1,199 files, 172 top-level entries, ≈100 subpackages). A module that size has no internal boundary.

#### R-1 — Context map

- **Steps:**
  1. Cluster RPG's internal import graph.
  2. Propose contexts. Starting point:
     - **genesis:** world forge, world generation, profiles;
     - **session:** turn pipeline, foreground turn record, game loop;
     - **narration:** dialogue, dialogue context, response generation;
     - **rules:** combat, economy, items, abilities, action resolution;
     - **map:** grid runtime, map actions;
     - **lore:** campaign, journal, lore;
     - **RPG Hermes;**
     - **replay.**
  3. Write the map to `docs/architecture/RPG_CONTEXTS.md`, with each context's contract and acyclic dependencies.
- **Acceptance:** the owner approves the map (human gate).

#### R-2 — Intra-RPG boundary lint

- **Steps:**
  1. Replace `[rpg_core]` in `layers.toml` with `[rpg_contexts]`.
  2. A context imports another only through its contract, following the context dependency order.
  3. Baseline the current violations.
- **Acceptance:** the lint runs and the baseline is recorded.

#### R-3 — Move RPG into its contexts

- **Steps:** one context per PR series: a pure move, then import fixes, then a baseline shrink.
- **Tests:**
  - the `rpg-production-turn` golden and the 50-turn replay are unchanged;
  - the RPG test estate passes.
- **Acceptance:** RPG has 15 or fewer top-level entries, and the intra-RPG baseline is 0.

---

## 6. Decisions considered and rejected

| Option | Decision | Reason |
|---|---|---|
| Microservices per app | Rejected | One owner, one machine or a small cluster, and shared GPU capacity. The modular monolith with separate model services (ADR-0011, ADR-0012) provides isolation without network contracts between every module. |
| Tier lists in `layers.toml` | Rejected for platform and app tiers | A central list means every new app edits it. The tier is declared in `FeatureModule.tier`. |
| Hand-maintained table ownership file | Rejected | It would be a central list every new app edits. New tables get a derived owner. Historical tables use a frozen map, which the lint closes to new entries. |
| Deriving every historical owner from filenames | Rejected | Some files create tables for several owners (`0007_remaining_modules.sql`), and many filename tokens aren't module ids. |
| Migration runner or settings kernel reading the feature catalog | Rejected | That would be a kernel→feature dependency. Migrations are found by a filesystem convention; settings sections are passed in by composition. |
| Discovering any `.sql` under any `migrations/` folder | Rejected | Folders such as `rpg/persistence/migrations/` hold save-format migrations, and a `.sql` file there would silently become a schema migration. Only three places are read. |
| Refusing execution on a whole-catalog digest mismatch | Rejected | It would refuse valid executions during rolling upgrades and MCP policy reloads. Grants carry a per-capability definition hash instead, which is stricter and tolerates rollouts. |
| Backfilling definition hashes for pre-existing grants | Rejected | It would assume each grant was issued for today's definition. Unhashed grants fail closed and are re-issued. |
| Deleting a module with work still in flight | Rejected | Recovery would resume jobs with no handler. Retirement first drives jobs, tasks, outbox deliveries and approvals to a final state recorded in PostgreSQL. |
| Failing every job whose type has no registered handler | Rejected | Workers claim only the types they handle, so such jobs legitimately wait: a temporarily disabled feature, a feature enabled in only some processes, or a rolling upgrade. Only types listed in a retirement tombstone are failed. Others stay queued and raise an age alert. |
| Disabling a feature before waiting for its running jobs | Rejected | Disabling unregisters the handlers, so the wait would only run out the timeout. A durable `draining` state keeps the handlers while refusing new work. |
| Adding new tables to the RLS list in `0106` | Rejected | It means editing a kernel migration for every app. Each module's own migration enables and forces RLS for its tables, and a PostgreSQL conformance check covers every tenant table. |
| Collecting settings through each module's `FeatureModule` | Rejected | It would import every `feature.py`, which loads routers, handlers and repositories even for disabled features. Composition imports the kernel-only `declarations.py` directly. |
| Retention horizons declared in code | Rejected | They would override horizons operators have already set in `omnix_retention_policies`. Code declares the handler and a default that is seeded only if the row is missing. |
| Checking RLS only on tables with a `workspace_id` column | Rejected | A child table without the column would ship unisolated. Every table must be isolated or explicitly exempt. |
| A grant hash listing the fields it covers | Rejected | A field added later would be silently uncovered. The hash covers every field except an explicit display-only list. |
| Feature code importing shared schemas from `core.ts` | Rejected | Moving a schema into core would break hand-written imports in an unrelated feature. Each feature's generated file re-exports what it uses. |
| Adding OpenAPI tags to identify route owners | Rejected | It changes the OpenAPI document. A generated `route-owners.json` carries the mapping instead. |
| Dropping a disabled feature's settings section | Rejected | The next save would lose its values. Sections follow the schema rule: always present. |
| Keeping `FeatureModule.hooks` alongside typed ports | Rejected | Two extension mechanisms, one of them untyped, with silent defaults. Ports replace hooks. |
| Turning every cross-module reaction into an event | Rejected | It changes same-transaction reactions into eventually consistent ones. Events are only for reactions that already run later. |
| One PostgreSQL schema per module (`rpg.*`, `trading.*`) | Rejected for existing tables; allowed for new modules if the owner chooses | Moving 215 tables means rewriting every SQL statement and risks recovery-sensitive paths. Derived ownership plus AL016 gives the boundary without the rewrite. |
| Separate Python distributions now | Deferred (PA-5.5) | Lint enforces the boundary; packaging adds release and lock-file cost. |
| Moving folders first, or making tier folders mandatory | Rejected | Folders without enforcement change nothing, and once tiers are declared, folders add no boundary. Tier folders are a decision gate (PA-5.3). |
| Moving all tests at once | Rejected | Large churn and no boundary gain. Tests move with the work that touches them (PA-2.5). |
| RPG decomposition gating the platform work | Rejected | It doesn't serve the add-an-app goal and is blocked on WP-8.6. It runs as Track R. |

---

## 7. Progress

| WP | Status | PRs | Date | Metric deltas | Notes |
|---|---|---|---|---|---|
| PA-0.1 | done | — | 2026-10-04 | — | [ADR-0016](architecture/ADR-0016-platform-tiers.md) accepted by the owner; linked from `ARCHITECTURE.md` and the FeatureModule guide |
| PA-0.2 | done | — | 2026-10-04 | AL001: 59 → 110 (policy re-seed: 27 reverse-direction contract imports, 26 imports of `runtime_document_services`, 16 from the newly covered `character_interactions`; −8 now inside one module); uncovered `app.*` modules: 0; lint regressions: 11 new | Required `FeatureModule.tier`; tiers read from `feature.py`, not `layers.toml`; one-direction contract rule; `contracts/` packages accepted; stale `app.hermes` removed; transitional `[modules.package_owners]` for `assistant_memory_v2`, `replay`, `image_http_client`. Feature matrix, lint/metrics tests (270), unit gate, mypy and metrics check pass |
| PA-0.3 | done | — | 2026-10-04 | New ratchets: reverse_contract_imports 22, any_scope_package_cycles 7 (AL015), app_to_app_imports 0, uncovered_app_modules 0, composition_imports_outside_composition 32, string_runtime_hooks 3, kernel_tools_naming_apps 3, platform_feature_specific_files 4, module_repositories_in_kernel 1, web_feature_clients_in_shared_api 15, src_root_service_entrypoints 4, tracked_runtime_data_in_src 2 | AL015 rule (any-scope reciprocal dependencies, composition excluded). Six table/SQL/RLS metrics move to PA-2.2, PA-2.3 and PA-4.1. Lint and metrics tests (253) and the metrics check with a fresh runtime report pass |
| PA-1.1 | done | — | 2026-10-04 | AL001 110 → 107; AL015 7 → 5 (`assets<->image`, `providers<->rpg` gone); kernel/shared → feature imports: 0 | `LEGACY_IMAGE_MANIFEST` (assets kernel, at most one) and `PROVIDER_CATALOGS` (providers, many) ports; image and RPG contribute. The kernel/shared imports of `runtime_composition` remain for PA-1.2 |
| PA-1.2 | done | — | 2026-10-04 | composition_imports_outside_composition 32 → 0; AL001 107 → 69 (with PA-1.3 work); boot imports 2077 (unchanged) | `runtime_document_services` deleted (23 call sites use their own persistence); assist review documents moved into chat; repository factories moved to their owners; 4 unused factories deleted; chat's default store comes from the composition-bound `CHAT_STORE_FACTORY` port |
| PA-1.3 | in progress | — | 2026-10-04 | string_runtime_hooks 3 → 0; reverse_contract_imports 22 → 16; AL015 5 → 2; boot imports 2077 | Steps 1, 2 and 5 done (typed ports; hooks deleted). Step 3: RPG, research and agents/tools done (`ASSIST_READOUTS`, `CHAT_RESEARCH`, `TYPED_TURN_ROUTER`); chat store wiring done (`CHAT_STORE_FACTORY`). Remaining: characters (needs conversation-segment ownership moved out of characters), step 4 (prompt budget); memory excluded (PA-3.2) |
| PA-1.4 | done | — | 2026-10-04 | kernel_tools_naming_apps 3 → 0; AL001 41 → 22 (with the PA-1.3 agents work); AL015 4 → 2 (only kernel pairs left: `assets<->persistence`, `persistence<->security`) | Tools declared through `TOOL_DECLARATIONS`; proposals and agent approvals bound to the capability definition hash (fail closed; migration 0127); catalog digest in diagnostics; permanent tool-catalog golden; agents capability one-way (agent runtime `uses` chat and tools; `TYPED_TURN_ROUTER`, `AGENT_RUN_WORKSPACES`); agent evidence's trading subject through `SECURITY_INSTRUMENTS` |
| PA-1.5 | in progress | — | 2026-10-04 | AL001 69 → 41; app_to_app_imports 0 | New `FeatureModule.uses` (optional contract dependency). Trading uses research, RPG uses image, desktop companion uses assistant-memory; character interactions, desktop companion, RPG and characters import platform services only through contracts (lazy exports). `replay` was folded into the RPG unit in PA-0.2. Remaining: memory imports (PA-3.2) |
| PA-2.1 | not started | — | — | — | Needs a design first: the settings profile is one typed API document with every module's section and module-dispatched job defaults; assembling it from declared sections at composition must keep the OpenAPI document and persisted settings unchanged |
| PA-2.2 | in progress | — | 2026-10-04 | tables_without_owner 0; historical_owner_map_additions 0; cross_module_sql 84 → 70 (AL016); kernel_named_module_tables 36 → 22; module_repositories_in_kernel 1 → 0 | Frozen historical owner map (248 tables) and generator; AL016 for Python SQL and module-folder migrations, with the retention registration exception. Module declarations: a module's kernel-only `declarations.py` (next to `feature.py`, found by convention like migrations) declares its retention record types with their delete handlers and its capacity row counts; the retention worker, the lifecycle capacity report and cleanup read them, so kernel `retention.py` and `lifecycle.py` no longer name RPG, agent-runtime or trading tables. The RPG narration event repository moved to `app/rpg/persistence/`. Remaining AL016: legacy cutover importers, the RPG foreground submission repositories, prompt and provider repositories in kernel persistence, module-record and asset SQL in modules, conversation segments |
| PA-2.3 | done | — | 2026-10-04 | app_migrations_in_kernel_dir 110 → 0; SCHEMA_KNOWN derived | Discovery in three places, derived `SCHEMA_KNOWN`, stem-based AL014, stray `.sql` lint; 110 single-owner migrations moved to their modules (schema dump identical on fresh databases); 37 kernel and multi-owner migrations stay |
| PA-2.4 | done | — | 2026-10-05 | web_feature_clients_in_shared_api 15 → 0; `api/generated/types.ts` removed; OpenAPI unchanged | Step 1: the 12 RPG and 3 Hermes clients moved into `features/rpg/api/`. Step 2: the RPG methods and foreground-turn submission left core `api/client.ts` (`features/rpg/api/rpgSessionClient.ts`). Step 3a: `omnix/no-core-feature-import` keeps `api/`, `events/`, `design/` and `shared/` free of feature imports; the assistant's events augment `OmnixEventMap` from `features/assistant/assistantEvents.ts`. Route owners: the feature registry records which feature mounted each operation and `api:schema` writes `route-owners.json` (607 operations, 71 kernel). Types: `api:types` (`scripts/generate-api-types.mjs`) writes `api/generated/core.ts` (kernel operations, 115 shared schemas) and 12 `features/<name>/api/generated.ts` files from each manifest's `backendModules` (and settings' `usesOperations`); 7 features have a typed `api/gateway.ts`. The core client's agent-run, task-graph, workflow, deep-research and context-chat calls moved to `features/assistant/api/assistantClient.ts`, voice library and voice job history to `features/voice/api/voiceClient.ts`, story assets to `features/storyteller/api/storyClient.ts`. `omnix/own-generated-api-types` keeps feature code on its own `generated.ts`. Web test (1482), typecheck, lint and the generated-file reproducibility check pass |
| PA-2.5 | done | — | 2026-10-05 | catalog modules with a test directory 5 → 18 of 18 | `scripts/test_module.py <module_id>` runs `src/tests/<package>/` (the last part of the catalog package, so `hermes` for `app.rpg.hermes`) plus the characterization scenarios whose `MODULES` tuple lists the module (`--list` prints the targets). Thirteen new directories were seeded with 50 existing tests (`git mv`) that import only that module, from `app/`, `unit/` and `gateway/` (no directory conftest); CI workflows, the architecture gates, Ruff per-file ignores and guides follow the moves. Every seeded module passes through `test_module.py`; `test_test_module.py` checks each catalog module has a directory with tests |
| PA-3.1 | not started | — | — | — | |
| PA-3.2 | blocked | — | — | — | Waits for the memory v2 live switch |
| PA-3.3 | not started | — | — | — | |
| PA-3.4 | not started | — | — | — | |
| PA-4.1 | done | — | 2026-10-05 | conformance baseline: 27 static gaps (9 modules without a contract, 18 without `declarations.py`); 49 tables neither isolated nor exempt (34 memory v2, 7 trading, 2 agent-runtime slots, 2 companion-activity, 1 RPG narration, 2 kernel) | `scripts/module_conformance.py` checks feature/tier, contract, migrations (own tables only, none left in the kernel folder), `declarations.py` (present, kernel-only imports), test directory and web `backendModules`; `src/tests/kernel/test_module_conformance.py` requires the gaps to equal `resources/architecture/module-conformance-baseline.json`, which only shrinks. The tenant check migrates a fresh PostgreSQL database and accepts forced row-level security with a `tenant_isolation` policy in either `0106` form (the `EXISTS` child form only through a declared foreign key to an isolated parent), or an exemption: 20 historical kernel tables carry a reviewed `tenant_exempt` reason in the frozen owner map. The retention-seed part of the declarations check lands with `declarations.py` (PA-2.1, PA-2.2) |
| PA-4.2 | not started | — | — | — | |
| PA-4.3 | not started | — | — | — | |
| PA-4.4 | in progress | — | 2026-10-05 | — | Step 1 done: `scripts/check_module.py <id> [--skip-web]` runs the architecture lint (failing only on new violations in the module's files), the module's conformance against its baseline entry, mypy on its package, `test_module.py`, and the web tests of each feature listing it in `backendModules` plus the web typecheck. Step 2 (the "Adding and retiring an app" guide) waits for the scaffold and retirement scripts (PA-4.2, PA-4.3) |
| PA-5.1 | blocked | — | — | — | Waits for the merge to `main` |
| PA-5.2 | blocked | — | — | — | Waits for the merge to `main` |
| PA-5.3 | decision | — | — | — | Owner decides |
| PA-5.4 | decision | — | — | — | Owner decides |
| PA-5.5 | decision | — | — | — | Only on a concrete trigger |
| PA-6.1 | blocked | — | — | — | |
| R-1 | blocked | — | — | — | Waits for WP-8.6 |
| R-2 | blocked | — | — | — | |
| R-3 | blocked | — | — | — | |

---

## 8. Revision history

**Revision 6 (2026-10-04)** applies a review of revision 5. That review judged the roadmap finished as a plan and recommends starting PA-0.1.

- **Kernel registration tables (PA-2.2).** AL016 now allows a module's migration to run `INSERT … ON CONFLICT DO NOTHING` on a named list of kernel tables (today only `omnix_retention_policies`), and only for the module's own declared record types. Without this, the retention seed row would fail the lint.
- **Child-table isolation (PA-4.1)** must use one fixed `EXISTS`-on-parent pattern over a declared foreign key to an isolated parent. The check verifies the pattern, so a placeholder such as `USING (true)` fails. The scaffold generates an example child table, and the second-tenant test covers it.

**Revision 5 (2026-10-04)** applies a review of revision 4. Every finding was checked against the code before it was applied. The review found nothing that blocks the owner from accepting ADR-0016 (PA-0.1); its findings were details inside individual work packages, and all of them are fixed here.

- **Secure by default (PA-4.1).** Every table a module creates must have forced RLS with a `tenant_isolation` policy or carry an explicit `omnix:tenant-exempt` comment, whether or not it has a `workspace_id` column. Child tables check isolation through their parent. Historical tables take their status from the frozen PA-2.2 map.
- **Draining (PA-4.3)** accepts follow-up jobs submitted from inside a running job of the same module, until the drain timeout. `draining` and `retired` in the database override the config; turning a feature off in config alone behaves as it does today.
- **Retention (PA-2.2).** The `omnix_retention_policies` row stays authoritative, because operators can edit it. A module declares its record type, a delete handler (agent retention keeps milestone events, which a table/column pair can't express) and a default horizon that its migration seeds only if the row is missing.
- **RPG repository in the kernel.** `rpg_narration_event_repository.py` moves into RPG and is now counted in §2. AL016 now also covers kernel code: no SQL against module tables, and no module repositories in a kernel package.
- **Grant hash (PA-1.4)** now includes `provider`, which names the backend serving MCP and browser tools.

**Revision 4 (2026-10-04)** applies a review of revision 3. Every finding was checked against the code before it was applied. That review considered the roadmap ready for the owner to accept through ADR-0016 (PA-0.1), with its remaining details to be fixed before PA-4.1 and PA-4.3 start (done in revision 5).

- **Tenant isolation for new tables.** Each module's own migration enables and forces RLS and creates the tenant policy, and the scaffold's example migration shows how. The conformance test (PA-4.1) checks on PostgreSQL that every table with a `workspace_id` column has forced RLS and the `tenant_isolation` policy. A new app never edits `0106_row_level_security.sql`.
- **Recovery (PA-4.3)** fails only job and event types listed in a retirement tombstone. Any other unknown type stays queued and raises an age alert, because workers claim only the types they handle (`claim_next`): disabled features and rolling upgrades are normal.
- **Draining (PA-4.3).** A new durable `draining` state keeps handlers registered while refusing new work. Retirement drains first, then cancels what's left, then disables.
- **Grant hash (PA-1.4)** is defined by exclusion: every `Capability` field except a display-only list, which brings in `scope_type`, `destructive`, `network_required`, `credential_required`, `requires_connection` and `audited`. Durable agent runs holding pre-WP grants receive an ordinary denial and request approval again.
- **Declarations (§1.2, PA-2.1).** A kernel-only `declarations.py` holds the settings section and the retention policies. Composition imports it directly for every module, enabled or not, and never imports a disabled `feature.py`.
- **Retention (PA-2.2)** policies are contributed by their modules. The kernel retention worker no longer names module tables.
- **Wording:**
  - tombstone folders are named after Python packages, with a generated `tombstone.py`;
  - only the composition layer binds an "exactly one" port, because modules that implement a port can always be disabled on their own.

**Revision 3 (2026-10-04)** applies a review of revision 2. Every finding was checked against the code before it was applied.

- **Table ownership (PA-2.2).** Historical owners come from a frozen, reviewed map, because `0007_remaining_modules.sql` creates tables for several owners and filename tokens aren't module ids. The lint rejects new entries, and new tables get a derived owner. AL016 now covers migrations too. Multi-owner historical files stay in the kernel folder.
- **Migration discovery (PA-2.3)** reads only the kernel folder, `migrations/` next to a `feature.py`, and the retired folders. A stray `.sql` file anywhere else is a lint error.
- **Settings (PA-2.1).** Sections are passed in by composition; the settings kernel never reads the catalog. Each `settings.py` imports kernel code only, and retired-section stubs live in the tombstone folder.
- **Tool authority (PA-1.4).** Grants carry a hash of the capability's definition, and the executor refuses a missing or changed definition. The whole-catalog digest is a diagnostic only, so rolling upgrades and MCP policy reloads no longer refuse valid executions.
- **Retirement (PA-4.3)** first drives the module's jobs, scheduled tasks, outbox deliveries and approvals to a final state recorded in PostgreSQL. It refuses to retire a module another module depends on. Recovery fails a job with an unknown type once, instead of looping.
- **Port cardinality (PA-1.3).** Catalog validation rejects an "exactly one" port whose implementer can be disabled on its own; upward ports are "at most one" or "many". Moving to ports and moving the prompt budget into chat are now separate steps, each proved byte-identical.
- **Shared schemas (PA-2.4).** Each feature's generated file re-exports every schema it uses, so moving a schema into `core.ts` never breaks hand-written code.
- **Ordering:**
  - PA-1.3 step 1 lands before PA-1.1;
  - the recipes (PA-4) need PA-1 and PA-2, not PA-3;
  - only the drills (PA-6) wait for memory;
  - PA-5.1 and PA-5.2 need only the merge.
- **Smaller fixes:**
  - `FeatureModule.tier` is required, with no default;
  - test folders are named after Python packages;
  - §2 says the `hermes.*` sidecar tools stay in the kernel and aren't counted.

**Revision 2 (2026-10-04)** applies a review of revision 1. Every finding was checked against the code at `6d839964e` before it was applied.

- **The goal counts hand-edited files only, and the central lists are now derived:**
  - the tier is declared in `FeatureModule.tier`;
  - table ownership comes from where the migrations live;
  - `SCHEMA_KNOWN` is computed;
  - route ownership comes from the feature registry.
- **Migration discovery** uses a filesystem convention, so the kernel never reads the catalog.
- **Retiring a module is new (PA-4.3)**, with tombstoned migrations, so the runner never sees applied versions as unknown.
- **Deferred reactions only (PA-3.4).** Events are limited to reactions that already run later; same-transaction reactions use ports.
- **Settings sections are always present (PA-2.1).** A disabled feature's section is never dropped.
- **The OpenAPI document stays unchanged (PA-2.4).** Route ownership comes from a generated side file instead of tags. The rule for schemas shared by several modules is defined, and each web manifest maps its folder to backend module ids.
- **Typed ports replace `FeatureModule.hooks` (PA-1.3).** Each port declares its cardinality, contributors have explicit priorities, chat owns the token budget, and memory is ported last.
- **Tool catalog safeguards (PA-1.4):** stored grants for absent tools fail closed, processes must agree on a catalog digest, and the catalog golden is permanent. The kernel tool catalog's app tools are now counted in §2.
- **Lint coverage (PA-0.2):**
  - `contracts/` subpackages are accepted;
  - every `app.*` package must be covered by the layer policy;
  - the stale `app.hermes` entry is removed;
  - `assistant_memory_v2` and `replay` get a transitional owner.
- **AL016** matches only table positions in SQL.
- **RPG decomposition is now Track R** and gates nothing. Tier folders are a decision gate. Model servers and packages with no clear home stay committed work (PA-5.1, PA-5.2).
- **§2 corrections:**
  - 146 migration files, not 126 (17 numeric prefixes are reused, and the highest is 0126);
  - 15 RPG and Hermes web clients, not 16;
  - 13 loose modules in `src/app`, not 17;
  - tracked runtime JSON in `src/app/data` is added;
  - "Hermes" is disambiguated: the sidecar client in providers versus RPG's `app/rpg/hermes`.
