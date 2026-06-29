# Hermes Local Checks

Phase 14 records the local checks for the Hermes integration path.

## Checks

1. Settings shows Hermes disabled without an error when Hermes is not enabled.
2. Settings shows offline when Hermes is enabled and the sidecar is not reachable.
3. Settings shows reachable when the sidecar health and capability calls succeed.
4. The Settings smoke test returns a dry-run result.
5. Normal Chat remains the default path.
6. Agent Chat remains opt-in.
7. Catalog payload rows are marked non-mutating.
8. Review card copy is informational.

## Expected local command set

Run the project checks normally used for the RPG branch, including the deterministic PR gates and any local frontend checks available in the developer environment.

## Notes

This file is a checklist only. It does not claim local execution results.
