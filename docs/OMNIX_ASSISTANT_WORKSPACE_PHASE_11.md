# Omnix Assistant Workspace Phase 11 — Scoped Memory System

Phase 11 adds scoped memory contracts for persistent assistant context.

## Scope

- Model global, workspace, project, and session memory scopes.
- Distinguish user-saved, imported, and assistant-suggested records.
- Require confirmation for assistant-suggested memory.

## Acceptance criteria

- Memory records can be filtered by scope.
- Pinning is immutable.
- Assistant-suggested records are detectable for confirmation flows.
