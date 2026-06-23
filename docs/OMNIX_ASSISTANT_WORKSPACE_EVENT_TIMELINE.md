# Omnix Assistant Workspace — Event Timeline Projection

This slice makes the typed event stream directly visible as timeline rows.

## Added

- `createTimelineItemsFromEvents` maps typed workspace events into deterministic timeline items.
- User and assistant message events become turn rows with truncated text labels.
- Tool call/result events become event rows with requested/running/completed/failed/denied status.
- Timeline rows retain `sourceEventType` and `sourceEventId` so UI panels can drill back into audit/provenance records.

## Acceptance

- Timeline items sort deterministically by timestamp and id.
- Tool approval requests and denied results are visible in the same timeline model as conversation turns.
- The helper is exported from the assistant workspace barrel for dashboard and shell integration.
