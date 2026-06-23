# Omnix Assistant Workspace Phase 24 — Playback Queue

Phase 24 adds pure playback queue contracts.

## Scope

- Model playback queue items.
- Enqueue playback items immutably.
- Track the active playback item.

## Acceptance criteria

- Queue items are copied into state.
- Enqueue preserves existing items.
- Active item selection is deterministic.
