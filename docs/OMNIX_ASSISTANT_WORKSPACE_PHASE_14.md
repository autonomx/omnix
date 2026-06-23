# Omnix Assistant Workspace Phase 14 — Workspace and Project Instructions

Phase 14 adds instruction records for global, workspace, project, and session scopes.

## Scope

- Model instruction scope, content, priority, and enabled state.
- Select enabled records.
- Sort records deterministically by priority and id.
- Filter records by active scopes.

## Acceptance criteria

- Disabled instructions are excluded from active context.
- Higher-priority instructions sort first.
- Scope filtering is deterministic.
