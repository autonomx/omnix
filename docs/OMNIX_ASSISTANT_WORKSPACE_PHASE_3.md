# Omnix Assistant Workspace Phase 3

Phase 3 adds the first event architecture contracts.

## Scope

- Event type list.
- Event type union.
- Base event shape with workspace, optional project, optional session, payload, and timestamp.
- Event type guard.

## Acceptance Criteria

- Meaningful assistant workspace changes can be represented as events.
- Events are scoped to workspaces and optionally projects or sessions.
- UI state can later be projected from event lists instead of owned by components.

## Files

- `apps/web/src/features/assistant-workspace/events.ts`
