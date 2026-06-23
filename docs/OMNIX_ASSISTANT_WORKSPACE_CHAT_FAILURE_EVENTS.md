# Omnix Assistant Workspace — Chat Failure Events

This slice makes chatbot/provider request failures replayable inside the assistant workspace activity stream.

## What changed

- Added a typed `operation_failed` assistant workspace event.
- Added a chatbot failure event helper for chat request errors.
- Projected failure events into timeline rows with `status: failed`.
- Wired `ChatbotWorkspace` mutation errors into the configured assistant workspace event store.
- Added tests that verify a failed gateway request appears in the activity panel and persists to storage.

## Why

Before this slice, chat/provider errors were transient UI alerts. They were visible to the current user, but they were not part of the replayable workspace event stream and could not be inspected later through the assistant workspace activity panel.

## Acceptance

- A failed chat request appends a typed `operation_failed` event.
- The event includes operation, message, optional status code, provider/model IDs, and submitted content details.
- The activity panel renders the failure with provenance source `operation_failed`.
- The event store persists the failure when persisted events are enabled.
