# Hermes Observability Notes

This note captures the current observable surfaces for the Omnix Hermes integration.

## Current surfaces

- Settings shows whether Hermes is disabled, offline, or reachable.
- Settings can run a safe dry-run smoke test.
- Dry-run output includes a compact ok/dry-run summary.
- Assist Core stores pending review data and action rows under the Assist Core data folder.

## Constraints

- Normal Chat remains the default path.
- Agent Chat remains opt-in.
- Dry-run paths must not mutate application state.
- Browser UI must not run arbitrary shell commands.

## Follow-up

A later slice can add a dedicated UI panel for viewing recent Assist Core rows once the API shape is finalized.
