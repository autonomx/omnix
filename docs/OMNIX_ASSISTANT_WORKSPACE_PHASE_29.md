# Phase 29 — Live Assistant Event Wiring

## Goal

Make live assistant turns replayable by writing the voice transcript, user turn, assembled context summary, and assistant response into the assistant workspace event stream.

## Implementation

- Extends `runLiveAssistantTurn` with optional `eventStore`, `workspaceId`, and `projectId` inputs.
- Records typed assistant workspace events for:
  - `voice_transcript`
  - `user_message`
  - `context_assembled`
  - `assistant_message`
- Returns the recorded events on `LiveAssistantTurnResult` so UI and orchestration layers can inspect what was persisted.
- Keeps the event store optional so existing tests and injected live-session controllers keep working without persistence.

## Acceptance

- Live assistant turns can still run with no event store.
- A live assistant turn with an event store produces replayable typed events for the selected session.
- The assistant message event carries provider, model, and token usage metadata when available.
- Unit coverage verifies the persisted event sequence and payload shape.
