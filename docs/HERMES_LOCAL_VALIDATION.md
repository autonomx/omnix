# Hermes Local Validation Pass

This pass records the local checks needed to validate the Hermes integration in a developer workstation environment.

## Preconditions

- Omnix backend can start locally.
- Web app can reach the backend API.
- Hermes sidecar can be disabled, offline, or reachable depending on the scenario.

## Scenarios

### 1. Disabled

Environment:

```bash
HERMES_ENABLED=false
```

Expected:

- Settings shows Hermes as disabled.
- Disabled is not displayed as an error.
- `/api/hermes/status` returns `state: disabled`.
- `/api/hermes/test` returns `dry_run: true`.

### 2. Enabled but offline

Environment:

```bash
HERMES_ENABLED=true
HERMES_BASE_URL=http://127.0.0.1:8642
```

Expected with no sidecar running:

- Settings shows offline.
- Status payload includes base URL and error detail.
- Dry-run result stays safe and non-mutating.

### 3. Reachable

Environment:

```bash
HERMES_ENABLED=true
HERMES_BASE_URL=http://127.0.0.1:8642
```

Expected with sidecar running:

- Settings shows reachable.
- Status payload includes health and capabilities.
- Dry-run result completes and reports `dry_run: true`.

### 4. Chat mode

Expected:

- Normal Chat remains the default provider path.
- Agent Chat remains opt-in.
- Agent Chat surfaces backend/result state clearly.

## Result template

Record local results with:

- date;
- commit SHA;
- scenario;
- pass/fail;
- notes;
- screenshots/log snippets if useful.
