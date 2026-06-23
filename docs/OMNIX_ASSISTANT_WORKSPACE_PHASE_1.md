# Omnix Assistant Workspace Phase 1

Phase 1 adds core domain contracts for the assistant workspace platform.

## Scope

- Workspace
- Project
- ChatSession
- ChatSessionMode
- stable reference helpers
- relationship validation helpers

## Acceptance Criteria

- Projects are linked to workspaces.
- Chat sessions are linked to workspaces and optional projects.
- Session mode is represented as text, voice, or mixed.
- The contracts are pure and do not depend on UI state.

## Files

- `apps/web/src/features/assistant-workspace/domain.ts`
- `apps/web/src/features/assistant-workspace/domain.test.ts`
