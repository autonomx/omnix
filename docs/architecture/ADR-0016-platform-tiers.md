# ADR 0016: Platform tiers and module boundaries

Status: accepted (2026-10-04).

Context: Omnix is a modular monolith (ADR-0010, ADR-0011, ADR-0014, ADR-0015) that will keep gaining AI apps. Today, adding one means editing central lists:
- `layers.toml`;
- the feature catalog;
- `SCHEMA_KNOWN`;
- the hard-coded row-level security list in `0106_row_level_security.sql`;
- the kernel tool catalog;
- settings profiles in `app/platform`;
- the shared web `api/` folder.

On top of that, some module-to-module imports go both ways, and the contract rule allows that. This ADR fixes the target. The [platform architecture roadmap](../PLATFORM_ARCHITECTURE_ROADMAP_2026-10-04.md) sequences the work.

## Goal

Adding an app hand-edits only the app's own folders, plus two registration lines: the backend feature catalog and the web module manifest. Generated files don't count, provided one documented command regenerates them and a check verifies them. Retiring an app touches the same two lines.

## Tiers

| Tier | Contents | May import |
|---|---|---|
| Kernel | Runtime, config, settings, security, observability, events and outbox, persistence, jobs, assets, the tool capability registry, conversation contracts, the `FeatureModule` SDK | Kernel |
| Shared services | LLM providers (including the Hermes sidecar client), prompts, the model catalog | Kernel, shared services |
| Platform capabilities | Chat, memory, characters, companion activity, speech, image, agents, research | Kernel, shared services, declared platform contracts |
| Apps | RPG, trading, audiobook, story, desktop companion, character interactions, and every future app | Kernel, shared services, declared platform contracts; never another app |
| Composition | Gateway, workers, launcher, runtime composition | Anything; nothing imports it |

How tiers are assigned:
- A module declares its tier in a required `FeatureModule.tier` field (`"platform"` or `"app"`) with no default. The architecture lint reads that field; there is no hand-kept list of platform or app packages.
- The kernel and shared-service lists in `layers.toml` stay. They change only when the platform changes.
- Every `app.*` package and loose file must belong to a tier. An unclassified one is a lint error.

## Dependency rules

1. **Contracts only.** A module may import another module only through its contract: `contracts` or a `contracts/` package.
2. **One direction.** If B declares `depends_on=("a",)`, B may import A's contract; A may not import B's. The `depends_on` graph between platform capabilities is acyclic, at any import scope, including imports inside functions.
3. **Apps never import apps.** This includes another app's contract.
4. **Ports for upward needs.** When a module needs behaviour from a module above it, or work done in the same transaction, it defines a port: a `Protocol` in its own contract. Modules contribute implementations through `FeatureModule.contributions`, and the composition root binds them.
   - Ports that modules implement are "at most one" or "many", ordered by explicit priority and then module id. The consumer handles absence explicitly.
   - Only composition binds an "exactly one" port.
   - Typed ports replace the string-keyed `FeatureModule.hooks`; the two never coexist.
5. **Events for reactions that can run later.** A reaction that already runs after the producer's commit uses a typed event in the producer's contract, delivered through the outbox. Restructuring never turns a same-transaction reaction into an eventually consistent one.

## Contributions, not central lists

A module owns, and contributes by declaration, everything the platform needs from it. The platform never names a module.

- **Tables and migrations.**
  - A module's migrations live in its own `migrations/` folder.
  - The runner finds migrations by filesystem convention in three places: the kernel folder, a `migrations/` folder next to a `feature.py`, and retired-module folders. It never reads the feature catalog.
  - `SCHEMA_KNOWN` is derived from the migrations it finds.
  - A table's owner is the module whose migrations create it. Historical tables use a frozen, reviewed ownership map that rejects new entries.
  - Only the owner's code and migrations touch its tables. The kernel is covered by the same rule. Modules may register rows only in named kernel registration tables, with `INSERT … ON CONFLICT DO NOTHING`.
- **Tenant isolation.**
  - Every table a module creates has forced row-level security with a `tenant_isolation` policy, created by the module's own migration, or carries an explicit `omnix:tenant-exempt` comment.
  - A child table uses one fixed `EXISTS`-on-parent policy pattern over a declared foreign key to an isolated parent.
  - A PostgreSQL conformance check verifies all of this.
- **Declarations.**
  - Each module has a kernel-only `declarations.py` holding its settings section and its retention declarations (record type, delete handler, default horizon).
  - Composition imports it for every catalog module, enabled or not, and never imports a disabled module's `feature.py`.
  - A disabled module's settings section is kept unchanged across saves.
  - The operator-editable retention row stays authoritative; a module's default only seeds a missing row.
- **Tools.**
  - Modules declare their tools.
  - Declaring a tool makes it available; it never grants it. Issuance, approval and execution stay with the capability registry, approval policy and `CapabilityExecutor`.
  - Each grant, approval or proposal records a hash of the capability's definition: every field except an explicit display-only list.
  - The executor refuses a call when the capability is missing or its hash differs. Grants without a hash fail closed.
  - A whole-catalog digest across processes is a diagnostic only.
- **Web.**
  - Each web feature owns its API clients and its generated types. Its manifest maps it to backend module ids.
  - Route ownership comes from a generated side file, so the OpenAPI document is unchanged.
  - Feature code imports schemas only from its own generated file, which re-exports any shared schema.

## Module anatomy

Each module has:
- `feature.py`, the declaration and the only file the catalog imports;
- a contract;
- `declarations.py`, kernel-only;
- `service.py`, with no SQL;
- `*_repository.py`, holding all SQL, against the module's own tables only;
- `routes.py`, HTTP only;
- `migrations/`.

Tests live in `src/tests/<python_package>/`.

## Module lifecycle

A module is `active`, `draining` or `retired`. This state is durable in PostgreSQL. `draining` and `retired` override runtime config; `active` defers to it.

**While a module is draining:**
- new work is refused, except follow-up jobs submitted by the module's own running jobs, until the drain timeout;
- its handlers and outbox consumers stay registered, so in-flight work can finish.

**Retiring a module:**
1. Refuse if another module depends on it.
2. Drain.
3. Record a final state in PostgreSQL for the remaining jobs, outbox deliveries, approvals and scheduled runs.
4. Move its migrations into a tombstone folder that is still discovered.
5. Keep its settings in a generated `tombstone.py`.

**Recovery:**
- A job or event type listed in a tombstone is failed once.
- Any other type without a handler stays queued and raises an age alert. Workers claim only the types they handle, so disabled features and rolling upgrades are normal.

## Consequences

- **Lint.** The architecture lint gains:
  - tier classification from `FeatureModule.tier`;
  - the one-direction contract rule;
  - AL015, for reciprocal dependencies at any import scope;
  - AL016, for SQL and migration table ownership.

  Each starts from a recorded baseline and can only shrink, per ADR-0015.
- **Existing violations.** Today's 59 layer violations, about 27 reverse-direction contract imports and 3 hidden cycles are recorded rather than accepted. The roadmap drives them to zero.
- **Folders.** Moving packages into tier folders, moving the web package, and splitting into separate Python distributions are decisions deferred to the owner. Once tiers are declared, folder location adds readability but no boundary. Model servers move to `src/services/`.
- **Authority is unchanged.** Nothing in this ADR widens agent, worker or trading authority. Profiles remain ceilings, approval policy never expands issued capabilities, research stays evidence, and PostgreSQL stays authoritative for recovery.

## Alternatives rejected

- **Microservices per app.** They would add network contracts between every module, with no isolation gain beyond ADR-0011 and ADR-0012.
- **A PostgreSQL schema per module for existing tables.** It would mean rewriting every SQL statement. Ownership plus AL016 gives the same boundary.
- **Central tier, ownership or route-tag lists.** Every new app would have to edit them.
- **A kernel that reads the feature catalog.** That would be a kernel→feature dependency.
- **Refusing execution on a catalog-digest mismatch.** It would refuse valid executions during rolling upgrades and MCP policy reloads.
- **Failing every job without a handler.** It would fail valid queued work.
- **Folder moves first.** Moving folders without enforcement changes nothing.
