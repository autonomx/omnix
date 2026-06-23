# Omnix Assistant Workspace Phase 17 — Conversation Timeline

Phase 17 adds pure timeline item contracts for rendering ordered assistant workspace activity.

## Scope

- Define timeline item kinds.
- Sort timeline rows deterministically.
- Filter timeline rows by kind.

## Acceptance criteria

- Timeline sorting is stable by timestamp and id.
- Timeline filtering is deterministic.
- Timeline notes can be created without UI state.
