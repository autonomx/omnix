# Hermes Diagnostics Validation

This document records the validation contract for the diagnostics helpers and routes.

## Status route

Expected path: `/api/hermes/status`

Expected disabled-state checks:

- HTTP status is 200.
- `enabled` is false when `HERMES_ENABLED=false`.
- `state` is `disabled`.
- diagnostics metadata includes `test_dry_run_only: true`.

Expected offline-state checks:

- HTTP status is 200.
- `enabled` is true when Hermes is enabled.
- `state` is `offline` when the sidecar is unreachable.
- the payload includes the configured base URL.

## Test route

Expected path: `/api/hermes/test`

Expected checks:

- HTTP status is 200.
- response includes `dry_run: true`.
- request content and session id are echoed in the request payload.
- diagnostics metadata still reports `test_dry_run_only: true`.
- the helper remains non-mutating.

## Follow-up

The next available code-test slice should convert this contract into unit tests once connector writes to test files are accepted.
