# Omnix Assistant Workspace Phase 20 — Live Session State Machine

Phase 20 adds deterministic live session mode contracts.

## Scope

- Define stable session modes.
- Validate mode names.
- Derive allowed input and output transitions.

## Acceptance criteria

- Unknown modes are rejected.
- Input can start only from ready or muted modes.
- Output can start only from working mode.
