# Omnix Assistant Workspace Phase 18 — Composer and Control Dock

Phase 18 adds pure composer state contracts.

## Scope

- Define composer controls for provider, model, identity, workspace, project, memory, library, tools, and voice.
- Enable submit only when draft text is non-empty.
- Toggle controls without mutating state.

## Acceptance criteria

- Empty drafts cannot submit.
- Control toggles are deterministic.
- Composer state is UI-framework independent.
