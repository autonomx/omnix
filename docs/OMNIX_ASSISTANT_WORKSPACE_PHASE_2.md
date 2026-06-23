# Omnix Assistant Workspace Phase 2

Phase 2 adds conversation engine contracts for durable turns with metadata.

## Scope

- ConversationTurnRole
- MessageContent
- TokenUsage
- ConversationTurnMetadata
- ConversationTurn
- ConversationState
- pure helpers for appending and reading turns

## Acceptance Criteria

- Conversations are modeled as turns, not UI-owned message bubbles.
- Turn roles include user, assistant, tool, and system.
- Provider/model/latency/token metadata can be attached to assistant turns.
- The conversation state owns no UI behavior.

## Files

- `apps/web/src/features/assistant-workspace/conversation.ts`
- `apps/web/src/features/assistant-workspace/conversation.test.ts`
