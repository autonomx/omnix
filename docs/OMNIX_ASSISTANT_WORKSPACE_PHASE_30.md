# Phase 30 — Assistant Workspace Runtime Configuration

## Goal

Move assistant workspace production defaults into a durable runtime configuration layer that can be supplied by Vite environment values and consumed by app surfaces.

## Implementation

- Adds `runtime-config.ts` for assistant workspace identifiers, provider/model defaults, STT/TTS service URLs, voice defaults, event storage key, and feature flags.
- Supports deterministic defaults when environment values are absent.
- Adds unit coverage for default behavior, environment overrides, empty strings, and boolean parsing.
- Wires the Chatbot workspace dashboard and default provider/model form values to the runtime config.

## Environment keys

- `VITE_ASSISTANT_WORKSPACE_ID`
- `VITE_ASSISTANT_PROJECT_ID`
- `VITE_ASSISTANT_PROVIDER_ID`
- `VITE_ASSISTANT_MODEL_ID`
- `VITE_ASSISTANT_STT_URL`
- `VITE_ASSISTANT_TTS_URL`
- `VITE_ASSISTANT_TTS_VOICE`
- `VITE_ASSISTANT_EVENT_STORAGE_KEY`
- `VITE_ASSISTANT_LIVE_ENABLED`
- `VITE_ASSISTANT_PERSISTED_EVENTS`
- `VITE_ASSISTANT_TOOL_EXECUTION`

## Acceptance

- Runtime config can be built from explicit test inputs or `import.meta.env`.
- Chatbot workspace uses configured default provider and model values.
- Dashboard reflects configured workspace/project IDs and persisted event/tool feature flags.
