# Adding and retiring an app

A module is an optional Omnix capability (audiobook, image, trading, …) that the gateway composes from one declaration. [ADR-0016](ADR-0016-platform-tiers.md) sets the rules every module follows:

- **Tiers.** A module is a platform capability, which other modules build on, or an app, which is a product no other module imports.
- **Imports.** Modules import each other only through `contracts.py`, and only in the `depends_on` or `uses` direction.
- **Two registration lines.** Outside its own folders, a module is registered by one line in `src/app/runtime/feature_catalog.py` and, if it has a web side, one line in `src/apps/web/src/app/modulesManifest.ts`.

Two scripts add and remove those lines and everything around them:

- `scripts/new_module.py` scaffolds a working module.
- `scripts/retire_module.py` takes one out without stranding its data or its in-flight work.

This guide walks through both. Run the commands from the repository root, with `OMNIX_DATABASE_URL` pointing at your development database. The recipe tests `src/tests/kernel/test_module_recipe.py` and `test_module_retirement_recipe.py` run the same steps on every change.

## Adding an app

### 1. Scaffold

```sh
python scripts/new_module.py field-notes --tier app --web
```

The id is lowercase words joined by `-`, and the Python package is the id with `_` (`field_notes`). Use `--tier platform` for a capability other modules will build on. Leave out `--web` for a backend-only module.

The script writes a small working module:

| Path | What it is |
|---|---|
| `src/app/field_notes/feature.py` | The `FEATURE = FeatureModule(...)` declaration, and nothing else. |
| `contracts.py` | What other modules may import: DTOs and ports. |
| `declarations.py` | What the kernel reads without loading the module. It imports kernel modules only. It holds the settings section (`SETTINGS`), retention handlers (`RETENTION`), capacity counts (`CAPACITY`) and the read and write permissions (`PERMISSIONS`). |
| `service.py`, `repository.py` | Workflow and transactions, and the SQL, one method per intent. |
| `jobs.py` | An example durable job (`field_notes.note`) on the shared worker. |
| `routes.py` (with `--web`) | The HTTP API under `/api/field-notes`. |
| `migrations/NNNN_field_notes_initial.sql` | A workspace-owned table under row-level security, a child table that follows its parent row, and the retention policy row. |
| `src/tests/field_notes/` | The module's tests. `scripts/test_module.py` runs them. |
| `src/apps/web/src/features/field-notes/` (with `--web`) | `module.ts` (the manifest: route, `backendModules`, `apiPrefixes`) and its test, `index.ts`, `api/gateway.ts` (the typed client) and the workspace component. |

It also edits the two registration files and regenerates the API contract files: `openapi.json`, `route-owners.json`, the core types and each feature's `api/generated.ts`. If the web packages are not installed, it skips the web types and says so. Run `npm --prefix src/apps/web run api:types` once they are installed.

### 2. Migrate and run

```sh
PYTHONPATH=src python -m app.persistence migrate
```

The runner finds the module's `migrations/` folder by convention, enabled or not, because the schema is a release artifact and not a feature flag. Start the gateway as usual. The module is on with `OMNIX_FEATURES=all` (the default) and off with `OMNIX_FEATURES_DISABLED=field-notes`.

### 3. Build the module

Replace the example item and note with your own model, keeping these rules.

**Declaration.** `feature.py` lists what the module contributes:

| Field | Use |
|---|---|
| `tier` | `"platform"` or `"app"`. |
| `routers`, `internal_routers` | Router factories: the public HTTP and WebSocket API, and service-token-only surfaces. |
| `job_handlers` | Durable jobs on the shared worker, which claims them, renews leases and handles cancellation. |
| `scheduled_tasks`, `background_workers` | Periodic work, and long-running loops owned by the background runtime. |
| `outbox_consumers` | Durable consumers of outbox events (`app.events.outbox_relay.OutboxConsumer`). |
| `contributions` | Implementations of typed ports declared in another module's contract (`app.runtime.ports`), such as an assistant tool for `TOOL_DECLARATIONS`. Declaring a tool grants nothing: grants, approvals and the tool policy still decide. |
| `repositories` | Repository specs the kernel builds per unit of work. |
| `depends_on` | Modules this one cannot run without. Startup fails if one is disabled. |
| `uses` | Modules whose contracts this one imports but can run without. The code must handle their absence. |
| `requires` | Runtime capabilities the module needs (`SERVE_API`, `RUN_JOB_WORKERS`, …). |

Factories receive a `FeatureContext`: runtime configuration, capabilities, kernel services and a logger. A module never imports the gateway composition root and never patches other packages at import time.

**Routes.**

- Use a module-level `router = APIRouter()` with module-level handlers, never handlers defined inside a factory.
- Request bodies are Pydantic models. Declare a `response_model` for every route.
- Handlers translate domain exceptions to status codes (missing → 404, validation → 422, state conflict → 409) and hold no business logic.
- Blocking work runs off the event loop: plain `def` handlers run in the threadpool, and `async def` handlers call blocking services through `asyncio.to_thread`.
- Stream uploads with a hard cap that also holds for chunked bodies, and stream downloads. `src/app/audiobook/routes.py` shows both.

**Service and repositories.**

- The service opens a `unit_of_work`, takes the locks a decision needs, and commits once. It never calls `connection.execute`.
- Repositories take the connection, filter every statement by `workspace_id`, and are named by meaning (`lock_render_settings`), not by SQL.
- A module touches only its own tables. It reaches kernel and other modules' data through their repositories and contracts. The architecture lint enforces this (AL016).

**Schema.**

- Migrations are forward-only, in the module's `migrations/` folder, with the `-- omnix-migration: phase=… transactional=…` header and a number above every existing one.
- Every table either has forced row-level security with the tenant policy, as in the scaffold, or states why it holds no workspace data in an `omnix:tenant-exempt:` table comment.
- A JSONB column read by queries needs an entry in `resources/architecture/jsonb-decisions.json`.

**Durable work.**

- Prefer `job_handlers` on the shared worker.
- A job a handler submits while it runs is recorded as that job's follow-up.
- A module with its own claim loops follows the audiobook lease pattern: claim with a short lease, renew it from a heartbeat, publish results only with the job's own lease token, and resume retries from durable checkpoints.

**Providers.** Depend on provider ports (`app.providers.*`), not on a concrete provider module. Import heavy provider code on demand, so registering the module's routes stays cheap.

**Settings.** Read your section with `module_settings("field_notes", FieldNotesSettingsProfile)` from `app.settings.effective_defaults`. It returns the section typed as the model `declarations.py` declares.

**Permissions.** `declarations.py` declares the module's `<package>:read` and `<package>:write` permissions (`FeaturePermissions`). Reads need the read permission, and every other method needs the write permission. A route can require its own permission with `requires(...)`.

**Web.** The feature imports only its own `api/gateway.ts` client and the kernel's shared code. Keep `backendModules` and `apiPrefixes` in `module.ts` in step with the routes. Rerun the generators after changing routes:

```sh
python scripts/export_gateway_openapi.py src/apps/web/src/api/generated/openapi.json
npm --prefix src/apps/web run api:types
```

### 4. Check

```sh
git add src/app/field_notes src/tests/field_notes src/apps/web/src/features/field-notes
python scripts/check_module.py field-notes
```

The architecture lint and conformance read only files git knows about, so stage the new module first. The script reports each of these steps:

1. that git knows every file of the module;
2. the architecture lint, failing only on new violations in the module's files;
3. module conformance (feature, contract, migrations, declarations, tests, web), with no gap beyond the module's entry in `resources/architecture/module-conformance-baseline.json`;
4. mypy on the package;
5. `scripts/test_module.py field-notes`, which runs the module's tests and its characterization scenarios;
6. with a web side, the tests of each web feature that lists the module in `backendModules`, and the web typecheck.

Use `--skip-web` while the web side is not yet ready. Before you open a pull request, also run the repository gates the module touches: `python scripts/architecture_lint.py --check`, `python scripts/architecture_metrics.py --check`, and `npm --prefix src/apps/web run build` for web changes.

## Retiring an app

Retiring removes a module's code while its data and history stay consistent:

- its migrations stay known to the runner;
- its tables keep an owner;
- its unfinished work reaches a final state in PostgreSQL;
- its stored settings survive.

Deleting the code by hand breaks all four: the runner rejects a database with an applied migration it cannot find, and recovery would keep retrying jobs whose handler is gone.

### 1. Make sure nothing needs it

`retire_module.py` refuses a module, and lists the reasons, while any of these is true:

- another catalog module lists it in `depends_on` or `uses`;
- another web feature lists it in `backendModules`;
- code outside the module's own package and tests imports it.

Remove those dependencies first, in their own change.

### 2. Retire

On a development machine, with one database and one checkout:

```sh
python scripts/retire_module.py field-notes
```

In a deployment, the database step runs against the live database while the current release, which still has the module, keeps running. The file step then ships in the next release:

```sh
OMNIX_DATABASE_URL=<deployment database> python scripts/retire_module.py field-notes --database-only
python scripts/retire_module.py field-notes --files-only    # in the checkout; review, commit, release
```

**The database step**, across every workspace:

1. **Drain.** The script marks the module `draining` in `omnix_module_states`, a state every process reads and that overrides the runtime configuration. In that state:
   - the module's routes answer reads and refuse writes with `503` and `Retry-After`;
   - its scheduled tasks start no new runs;
   - new jobs are refused, except follow-ups its own running jobs submit;
   - its handlers and consumers stay registered, so work in flight can finish.

   The script waits, up to `--drain-timeout` (default 600 seconds), for the module's running jobs to finish and its outbox consumers' deliveries to be consumed.
2. **Cancel what is left,** through the kernel repositories, with reason `module_retired`:
   - waiting jobs are canceled;
   - running jobs are asked to stop, and after `--cancel-grace` (default 30 seconds) any still unfinished are failed;
   - each of its consumers' undelivered events is dead-lettered for that consumer only, so other modules' consumers still receive it;
   - its tools' pending or approved proposals expire.

   Nothing is deleted.
3. **Check.** If any of that work is still not final, the script stops and the module stays `draining`. Rerun the script once the work is final, or undo the retirement with `python scripts/retire_module.py field-notes --reactivate`.
4. **Retire.** The module is marked `retired`. From then on it takes no work in any process.

**The file step:**

- It removes the catalog line and the web manifest line, the module's package, `src/tests/field_notes/` and the web feature folder.
- It removes the module's entry from the conformance baseline.
- It moves `migrations/` to `src/app/persistence/retired/field_notes/migrations/`, where the runner still finds every applied version and the module's tables are owned by `retired:field-notes`.
- It writes the kernel-only `src/app/persistence/retired/field_notes/tombstone.py`:
  - `MODULE_ID`;
  - a settings section stub with the same field, order and alias, which keeps the stored values;
  - the retired `JOB_TYPES`, `OUTBOX_CONSUMERS`, `TOOL_IDS` and `CAPABILITY_IDS`.
- It regenerates the API contract files, unless you pass `--no-generate`.

Review the diff. Outside the module's folders and the tombstone, it touches only the two registration files and the generated contracts.

### 3. What happens afterwards

- **Recovery.** Every minute, recovery fails any job of a tombstone's `JOB_TYPES` that is still unfinished, once, with `module_retired`. Jobs of any other type that no process here handles are not failed: they wait, because the feature may only be disabled or newer than this worker. If one waits longer than `OMNIX_JOB_UNCLAIMED_ALERT_SECONDS` (default 900), recovery logs `job_unclaimed_too_long` with the type and its age.
- **Configuration.** A configuration that still names the module (`OMNIX_FEATURES`, `OMNIX_FEATURES_DISABLED`) still starts. The id is dropped.
- **Tools and grants.** The module's tools leave the catalog. Stored grants and agent-run approvals for them fail closed, because the capability no longer exists.
- **Data.** The module's tables and rows stay. To delete them, add a contract migration to the tombstone's `migrations/` folder that drops them. This needs the owner's approval and ships under the normal expand and contract rules. The tombstone stays after it is applied.
