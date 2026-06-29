# Local Checks

This note records local checks for a developer workstation environment.

## Preconditions

- Backend can start locally.
- Web app can reach the backend API.
- Optional local services can be toggled depending on the scenario.

## Scenarios

### Disabled state

Expected:

- Settings shows the feature as disabled.
- Disabled is not displayed as an error.
- Status payload reports the disabled state.
- Smoke check reports dry-run state.

### Offline state

Expected:

- Settings shows offline when a configured local service is unreachable.
- Status payload includes the configured base URL.
- Smoke check remains safe.

### Reachable state

Expected:

- Settings shows reachable when the local service is running.
- Status payload includes health and capability details.
- Smoke check completes and reports dry-run state.

### Chat mode

Expected:

- Normal Chat remains the default path.
- Agent Chat remains opt-in.
- Agent Chat surfaces backend/result state clearly.

## Result template

Record local results with date, commit SHA, scenario, pass/fail, and notes.
