# Assistant Workspace Activity Wiring

This slice wires the assistant workspace activity panel into the live chatbot workspace.

## What changed

- Chatbot messages are projected into typed assistant workspace events.
- The chatbot workspace writes those events into the assistant workspace event store.
- Persisted event storage uses the configured assistant workspace storage key when enabled.
- `AssistantWorkspaceActivityPanel` renders replayable activity from the same event stream as the conversation.

## Acceptance

- The dashboard shows real chat activity events instead of an isolated component fixture.
- User and assistant messages produce stable `user_message` / `assistant_message` event IDs.
- The activity panel displays source event provenance for rendered timeline rows.
- Tests verify the rendered activity panel and persisted replay events.
