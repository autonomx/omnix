# Omnix Assistant Workspace — Tool Execution UX

This slice turns capability/tool events into user-visible execution rows.

## Added

- `tool-execution-view.ts` maps typed `tool_call` and `tool_result` events into deterministic rows.
- `ToolExecutionPanel.tsx` renders approval prompts, running/completed/failed/denied state, and retry actions.
- Denied capability results now remain `denied` in typed tool result events instead of being collapsed to `failed`.
- Barrel exports expose the view model and panel from `assistant-workspace`.

## Acceptance

- Pending tool calls produce `approve` and `deny` actions.
- Failed tool calls produce a `retry` action.
- Completed and denied rows do not expose stale approval actions.
- Tool arguments and results are summarized with stable key ordering for deterministic UI/test output.
