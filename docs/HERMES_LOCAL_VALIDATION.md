# Local Validation Pass

This note records local checks for a developer workstation environment.

## Preconditions

- Backend can start locally.
- Web app can reach the backend API.
- Optional sidecar services can be toggled depending on the scenario.

## Scenarios

### 1. Disabled state

Expected:

- Settings shows the feature as disabled.
- Disabled is not displayed as an error.
- Status payload reports the disabled state.
- Smoke check reports dry-run state.

### 2. Offline state

Expected:

- Settings shows offline when a configured local service is unreachable.
- Status payload includes the configured base URL.
- Smoke check remains safe.

### 3. Reachable state

Expected:

- Settings shows reachable when the local service is running.
- Status payload includes health and capability details.
- Smoke check completes and reports dry-run state.

### 4. Chat mode

Expected:

- Normal Chat remains the default path.
- Agent Chat remains opt-in.
- Agent Chat surfaces backend/result state clearly.

## Result template

Record local results with date, commit SHA, scenario, pass/fail, and notes.
