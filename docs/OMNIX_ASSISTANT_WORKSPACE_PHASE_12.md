# Omnix Assistant Workspace Phase 12 — Memory Management UI Contracts

Phase 12 adds pure view-model helpers for memory management surfaces.

## Scope

- Build rows for global, workspace, project, and session memory views.
- Expose confirmation-oriented actions for assistant-suggested records.
- Support pinned-only and suggested-only filters.

## Acceptance criteria

- Suggested rows expose approve/reject actions.
- Saved rows expose edit, forget, pin, and move-scope actions.
- Filtering is deterministic and framework independent.
