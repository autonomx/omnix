# Omnix Assistant Workspace — Activity Panel

This slice exposes the typed event stream and tool execution UX together as a React panel.

## Added

- `AssistantWorkspaceActivityPanel.tsx` renders timeline rows from replay events.
- The activity panel embeds `ToolExecutionPanel` so approval, deny, and retry callbacks can be wired by the app shell.
- The panel keeps conversation, tool, and provenance activity in one user-visible view.
- Public exports expose the panel and props from the assistant workspace barrel.

## Acceptance

- Empty event streams render a deterministic empty state.
- User message and tool call events appear in the timeline.
- Pending tool calls expose approve/deny actions through passed handlers.
