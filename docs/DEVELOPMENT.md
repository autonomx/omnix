# Omnix Development Guide

This guide explains how to extend Omnix without creating parallel infrastructure or weakening its authority boundaries. Read [ARCHITECTURE.md](ARCHITECTURE.md) first for the system model and [SETUP.md](SETUP.md) for a working development environment.

## Development principles

Before implementation, treat these as hard platform rules:

1. Add browser UI to `src/apps/web`; do not create another frontend stack.
2. Keep authoritative domain state in backend/domain services.
3. Use typed API contracts between the browser and backend.
4. Reuse shared providers/models, jobs/runs, assets, events, settings, and diagnostics.
5. Long-running work must be represented as a job/run.
6. Generated outputs must be represented as assets/artifacts.
7. Tool/agent authority must be registered and policy-governed.
8. Secrets belong in environment/credential stores, not browser state or source control.
9. Compatibility routes may delegate to legacy/domain code, but new UI must not depend on the retired classic frontend.
10. Tests must validate the final candidate state, not merely that a tool call occurred.

## Repository entry points

### Frontend

```text
src/apps/web/src/
├─ api/          shared gateway client and generated contracts
├─ app/          routes, module catalog, application shell
├─ design/       shared UI primitives/tokens
├─ events/       event-stream client
├─ features/     product workspaces and shared feature components
└─ main.tsx      browser entry point and global styles
```

### Backend

```text
src/app/
├─ gateway/          browser-facing API aggregation
├─ providers/        provider/model registry and adapters
├─ jobs/             shared long-running job model
├─ assets/           shared artifacts/assets
├─ persistence/      PostgreSQL authority and migrations
├─ agent_runtime/    semantic routing, planning, execution, review
├─ assistant_tools/  governed integration adapters
├─ chat/             chat/session generation
├─ rpg/              deterministic RPG domain
└─ trading/          trading data/research/replay/strategy systems
```

Python tests live primarily under `src/tests`. Frontend tests live next to features and under the web app test configuration.

## Adding or changing a browser module

Top-level routes are defined in `src/apps/web/src/app/modules.ts` and dispatched by the app router/workspace layer.

For a new routed workspace:

1. Add a stable module ID, route, label, summary, and capability metadata to the module catalog.
2. Add the React workspace under `src/apps/web/src/features/<feature>/`.
3. Wire it through `ModuleWorkspace.tsx` or the router's specialized path.
4. Reuse `WorkspacePanel` and existing design primitives.
5. Fetch backend-owned state through the shared API client/TanStack Query.
6. Keep transient layout/selection state local or in a scoped Zustand store.
7. Add loading, error, empty, disabled, and accessibility states.
8. Add unit/component tests and browser tests for critical flows.
9. Update [FEATURES.md](FEATURES.md) and this documentation when the user-visible capability changes.

Do not put feature data in hard-coded UI mocks once an authoritative backend contract exists.

## API development

### Prefer coherent resource namespaces

New APIs should follow the platform's resource model, for example:

```text
/api/chat/...
/api/rpg/...
/api/storyteller/...
/api/podcast/...
/api/voice/...
/api/stt/...
/api/image-generation/...
/api/trading/...
/api/jobs/...
/api/assets/...
/api/providers/...
/api/models/...
/api/settings/...
/api/diagnostics/...
```

A compatibility route is acceptable during migration if it delegates to the real domain service. It should not become a second implementation of domain logic.

### Pydantic contracts

Define explicit request/response models. Avoid returning unstructured dictionaries when a stable contract exists. Validate enums/ranges/nullable fields on the backend and keep the frontend model generated or synchronized from OpenAPI.

### Regenerate frontend contracts

After backend OpenAPI changes:

```bash
npm --workspace @omnix/web run api:generate
npm --workspace @omnix/web run api:check
```

The generated contract must be part of the same change so CI and reviewers evaluate the code against the actual API surface.

## Server state vs browser state

Use TanStack Query for server state. Use Zustand/component state for transient view state.

Good browser-owned examples:

- which tab is active;
- whether a rail is collapsed;
- form drafts before submission;
- chart viewport/layout;
- selected asset before persistence;
- playback position.

Bad browser-owned examples:

- committed RPG HP/inventory/XP;
- whether a job actually completed;
- authoritative provider health;
- accepted agent evidence;
- paper-account balances/fills when a backend account exists;
- server settings that other processes consume.

## Long-running work: use jobs/runs

Do not keep an HTTP request open for an operation that can take seconds/minutes and needs progress, cancellation, retries, logs, or resource scheduling.

A feature should create a shared job with:

- `module`;
- stable job `type`;
- `resource_class`;
- priority;
- structured `input_ref`/`input_payload`;
- meaningful ordered stages;
- output references that point to assets/artifacts.

The worker/runtime should update shared status/progress. The browser observes the job via Query + shared events and invalidates feature data when outputs appear.

### Stage names should be semantic

Prefer:

```text
ingest-sample → build-profile → preview → store-profile
```

instead of opaque stages such as `step1`, `step2`, `step3`.

## Generated outputs: use assets/artifacts

If an operation produces a durable file/result, register it in the shared asset system.

An asset should have enough metadata to answer:

- What is it?
- Which module/job created it?
- Where is it stored?
- What MIME/content type is it?
- When was it created?
- What domain-specific metadata is needed to reopen/reuse it?

Feature workspaces can filter the library, but should not create hidden private output directories with no shared asset record.

## Events and realtime

Use the shared `/events` client for one-way server updates such as jobs, assets, provider/model refresh, and diagnostics.

Use WebSocket/bidirectional transports only when interaction requires it, for example live voice. Do not add independent polling loops where the shared event stream can invalidate Query state.

If polling is necessary for recovery/fallback, bound it and stop polling terminal state.

## Providers and models

A provider is a reusable capability source, not a feature-local HTTP client.

When adding a provider:

1. Implement/adapt it in the shared provider layer.
2. Advertise explicit capabilities.
3. Surface health/readiness and useful diagnostic metadata.
4. Register discovered models/resources through the shared model facade.
5. Keep credentials in provider/environment/credential storage.
6. Make feature selection capability-driven rather than checking a provider name whenever possible.
7. Add provider tests for success, failure, auth, timeout, and malformed responses.

Features should ask for a provider with the needed capability (LLM/TTS/STT/image/etc.) and respect Settings defaults.

## Model residency

Model files being installed is not the same as model weights being resident in memory. Image Generation explicitly models this distinction with download/status/load/unload actions.

Use the same principle for other heavyweight runtimes when needed:

```text
installed → service reachable → model loadable → model loaded → feature ready
```

Diagnostics should identify the failing layer rather than returning a generic unavailable state.

## Settings development

Settings categories and metadata live under the web Settings feature registry.

Every setting should identify:

- stable key;
- category and section;
- value kind/default;
- scope;
- persistence owner;
- writable/read-only state;
- when it takes effect;
- whether restart is required;
- search aliases where useful.

Environment-owned values must not become writable browser controls unless an explicit secure backend mutation contract is added.

When adding a setting, update the relevant runtime consumer and test both persistence and effective behavior. A control that saves but is never read by the runtime is not complete.

## Assistant tool/capability development

The canonical capability registry is `src/app/agent_runtime/capabilities.py`. Browser-facing assistant tools are projected through `src/app/assistant_tools/registry.py`.

Do not add a model tool by only changing a prompt. Register its authority explicitly.

A capability definition should specify:

- canonical ID/namespace;
- human name/description;
- execution zone;
- effect (read/create/mutate/delete/execute);
- risk;
- scope type;
- approval policy;
- network/credential requirements;
- confirmation/destructive flags;
- provider/category;
- visibility to assistant/Hermes;
- bounded input/output schema.

### Authority and approval are separate

Approval policy must never grant a capability that the run was not issued. A model with permission to auto-run safe actions does not gain unrelated workspace, Git, network, or destructive authority.

### Broker external effects

Network integrations and external mutations should be broker mediated. Validate:

- connection identity;
- allowed operation;
- argument bounds;
- confirmation policy;
- audit record;
- timeout/failure behavior;
- idempotency or duplicate-send behavior when applicable.

## Generalized agent/runtime development

Agent-runtime changes require stronger correctness than ordinary chat features because the runtime can edit files, run tests, and interact with external systems.

### Preserve identities

Keep explicit identities for:

- run and attempt;
- workspace/baseline;
- candidate workspace state;
- authoritative `RunChangeSet`;
- acceptance plan;
- evidence subject/source;
- reviewer/review snapshot;
- resource grants and consumed budgets.

Do not validate one candidate and then return another.

### Planning and TaskGraph

Planning, TaskGraph compilation, scheduling, optimization, revision, and recovery should remain durable enough to resume/diagnose. A tool completion alone is not acceptance.

### Acceptance and evidence

Success criteria should compile to objective checks where possible. Evidence must be tied to returned source content and the correct subject, not echoed queries/prompts or stale workspace data.

For coding work, final validation should inspect the candidate-bound change set and run tests/checks against the final candidate state.

### Independent review

Reviewer input should be the intended run-owned subject. Avoid copying unrelated pre-existing dirty paths into a reviewer snapshot. Reviewer identity, verdict, findings, and revision cycles should remain attributable.

### Recovery and budgets

Failures should be classified: transient process/network failure, failed test, acceptance failure, evidence gap, review issue, exhausted resource policy, etc. Recovery should react to the cause rather than blindly repeat the same action.

Resource limits are safety/operational policy. They should not be mistaken for proof of progress or quality.

## RPG development

The RPG simulation is authoritative and deterministic.

When adding gameplay systems:

1. Implement state transitions in the simulation/domain layer.
2. Define turn/action contracts.
3. Validate inputs and deterministic outputs.
4. Persist authoritative state/checkpoints.
5. Let LLM/Hermes layers narrate or propose around the state, not mutate it outside the domain path.
6. Add deterministic tests before UI polish.
7. Add replay/endurance tests for cross-turn behavior where relevant.

The React workspace should render projections from backend/session state, not infer missing game truth.

## Trading development

Keep these layers separate:

```text
market data
  ↓
research / indicators / catalysts
  ↓
strategy signals
  ↓
risk / qualification
  ↓
paper execution simulation
  ↓
outcomes / reports / learning
```

LLM/Hermes analysis may enrich research/ranking/veto flows, but should not silently bypass deterministic risk/execution authority.

When adding market-data support, preserve provider/binding provenance and interval availability. When adding execution simulation, model spreads/slippage/halts/partial fills where the strategy requires realism.

## Persistence and migrations

PostgreSQL is the supported structured runtime backend.

When a durable schema changes:

1. add a migration using the persistence migration framework;
2. test a clean database and an upgrade path;
3. run:

```bash
python -m app.persistence migrate
python -m app.persistence verify
```

4. update persistence repositories/services;
5. include integration tests that use `OMNIX_TEST_DATABASE_URL` when the behavior depends on PostgreSQL semantics.

Do not introduce a parallel SQLite production path.

## Secrets and credentials

Never commit:

- provider API tokens;
- database passwords/DSNs;
- OAuth refresh tokens;
- GitHub/Google credentials;
- device passwords;
- private model repository tokens.

Use environment/configuration/credential stores. The Windows PostgreSQL launcher path uses DPAPI-protected current-user storage for the DB URL.

Logs and diagnostics should redact known secret fields and credential-bearing URLs.

## Testing strategy

### Frontend

Run at minimum for changed UI:

```bash
npm run web:typecheck
npm run web:test
npm run web:build
```

Run Playwright/e2e for navigation or integration-critical behavior:

```bash
npm run web:test:e2e
```

### Backend

Run focused tests while iterating, then the broader applicable suite:

```bash
pytest <focused-test-paths>
pytest
```

Use opt-in live-model/provider tests only when the required service and credentials are intentionally available. A unit/CI path should not fabricate authoritative external success when production behavior requires a real adapter.

### Persistence

```bash
python -m app.persistence verify
```

### API contract

```bash
npm --workspace @omnix/web run api:check
```

### Tests should cover failure modes

For a new capability, include cases such as:

- provider unavailable;
- authorization failure;
- invalid input;
- timeout/cancel;
- job failure/retry;
- stale/out-of-order events;
- missing asset;
- permission/capability denial;
- approval required;
- restart/recovery when durable state is involved.

## Pull-request checklist

Before opening or merging a PR:

- [ ] User-visible behavior is documented.
- [ ] Backend remains authoritative for domain state.
- [ ] No duplicate provider/job/asset/event infrastructure was added.
- [ ] API types were regenerated if contracts changed.
- [ ] Database migrations were added/verified if schema changed.
- [ ] Capabilities/approval policy were updated for new tool authority.
- [ ] Secrets are not present in source, fixtures, logs, or screenshots.
- [ ] Focused tests pass.
- [ ] Typecheck/build pass for web changes.
- [ ] The complete final diff was reviewed, including call sites and failure paths.
- [ ] Legacy browser UI was not reintroduced.

## Documentation maintenance

Keep these files synchronized with shipped behavior:

- `docs/FEATURES.md` for feature/user-surface changes.
- `docs/ARCHITECTURE.md` for topology/authority/platform changes.
- `docs/SETUP.md` for prerequisites/configuration/service startup changes.
- `docs/DEVELOPMENT.md` for contribution/workflow rules.
- `docs/index.html` for the browsable overview.

The documentation should describe current behavior first. Planned work should be clearly labeled as planned rather than written as if it already ships.
