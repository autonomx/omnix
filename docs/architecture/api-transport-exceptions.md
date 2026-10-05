# API transport exceptions

Browser-facing JSON routes have typed request and response contracts in OpenAPI. Streaming and file-transfer routes declare their media type and transport shape there; they do not use JSON response models. Keep this inventory exact and update it with the route implementation.

| Source | Method | Route path | Transport |
|---|---|---|---|
| `src/app/chat/assistant_context/routes.py` | POST | `/api/assistant/context/chat/sessions/{session_id}/messages/stream` | Server-Sent Events |
| `src/app/agent_runtime/api.py` | GET | `/api/agent-runs/{run_id}/events/stream` | Server-Sent Events |
| `src/app/agent_runtime/task_graph_api.py` | GET | `/api/task-graph-runs/{run_id}/events/stream` | Server-Sent Events |
| `src/app/character_interactions/routes.py` | POST | `/api/chat/sessions/{session_id}/live-call/greeting/stream` | Server-Sent Events |
| `src/app/gateway/kernel_routes/core_chat_routes.py` | POST | `/api/chat/sessions/{session_id}/messages/stream` | Server-Sent Events |
| `src/app/gateway/kernel_routes/core_jobs_routes.py` | GET | `/events` | Server-Sent Events |
| `src/app/gateway/kernel_routes/core_jobs_routes.py` | GET | `/api/jobs/events` | Server-Sent Events |
| `src/app/chat/live_chat_speculation.py` | POST | `/api/live/speculation/sessions/{session_id}/stream` | Server-Sent Events |
| `src/app/chat/live_chat_speculation_handshake.py` | POST | `/api/live/speculation/sessions/{session_id}/{generation_id}/stream` | Server-Sent Events |
| `src/app/chat/live_chat_speculation_inline_stream.py` | POST | `/api/live/speculation/sessions/{session_id}/start-stream` | Server-Sent Events |
| `src/app/rpg/api/feature_routes/rpg_narrative_delivery_routes.py` | GET | `/api/rpg/narrative-responses/{response_id}/stream` | Server-Sent Events |

WebSocket routes are absent from OpenAPI by protocol definition. The gateway and feature routes are:

| Source | Route path |
|---|---|
| `src/app/audiobook/streaming.py` | `/ws/audiobook` |
| `src/app/live_speech/api_stub.py` | `/v1/realtime` |
| `src/app/voice/stt_proxy_routes.py` | `/api/stt/ws/transcribe` |
| `src/app/voice/tts_pcm_websocket.py` | `/api/tts/stream/websocket` |
| `src/app/voice/tts_live_call_websocket.py` | `/api/tts/live-call/websocket` |
| `src/app/trading/api.py` | `/api/trading/stream` |

HTTP routes below transfer file bytes or redirect the browser. Their OpenAPI responses describe the actual media type, binary schema, redirect status, or empty body. They are documented separately from JSON response models.

| Source | Method | Route path | Transport |
|---|---|---|---|
| `src/app/audiobook/routes.py` | DELETE | `/api/audiobook/projects/{project_id}` | 204 No Content |
| `src/app/audiobook/routes.py` | GET | `/api/audiobook/projects/{project_id}/source/download` | Source file bytes; format-specific media type |
| `src/app/audiobook/routes.py` | GET | `/api/audiobook/projects/{project_id}/cover` | JPEG or PNG bytes |
| `src/app/audiobook/routes.py` | GET | `/api/audiobook/projects/{project_id}/previews/{job_id}/audio` | WAV audio bytes |
| `src/app/audiobook/routes.py` | GET | `/api/audiobook/projects/{project_id}/exports/{export_id}/download` | Audio file bytes; format-specific media type |
| `src/app/assistant_tools/routes.py` | GET | `/api/assistant/tools/connect/google/callback` | 303 OAuth result redirect |
| `src/app/assistant_tools/routes.py` | GET | `/api/assistant/tools/connect/github/callback` | 303 OAuth result redirect |
| `src/app/gateway/kernel_routes/core_assets_routes.py` | GET | `/api/assets/{asset_id}/audio` | Audio file bytes with Range support; media type from the asset |
| `src/app/gateway/kernel_routes/core_assets_routes.py` | GET | `/api/assets/{asset_id}/download` | Asset file bytes as an attachment; media type from the asset |
| `src/app/security/auth/routes.py` | GET | `/api/auth/local/callback` | 303 launcher sign-in redirect that sets the session cookies |
| `src/app/security/auth/routes.py` | GET | `/api/auth/oidc/login` | 302 redirect to the identity provider |
| `src/app/security/auth/routes.py` | GET | `/api/auth/oidc/callback` | 303 sign-in result redirect that sets the session cookies |
| `src/app/security/auth/routes.py` | POST | `/api/auth/logout` | 204 empty response that clears the session cookies |
| `src/app/agent_runtime/preview_api.py` | GET | `/api/agent-runs/{run_id}/workspace-preview/{asset_path}` | Allowlisted preview file bytes or HTML source text |
| `src/app/characters/live2d_avatar.py` | GET | `/api/character-live2d/runtime/{filename}` | Runtime script or binary bytes |
| `src/app/characters/live2d_avatar.py` | GET | `/api/character-live2d/assets/{asset_id}/{asset_path}` | Live2D model asset bytes |
| `src/app/voice/live_voice_cue_asset_routes.py` | GET | `/api/voice/cues/{voice_id}/{cue_id}/{variant_id}.wav` | WAV audio bytes |
| `src/app/image/routes/assets.py` | GET | `/api/assets/{asset_id}/file` | Allowlisted image bytes |
| `src/app/rpg/api/feature_routes/rpg_map_editor_routes.py` | POST | `/api/rpg/map-editor/export` | Validated JSON document download |
| `src/app/rpg/api/feature_routes/rpg_world_bundle_routes.py` | GET | `/api/rpg/worlds/{world_id}/export` | ZIP archive bytes |
| `src/app/gateway/kernel_routes/__init__.py` | GET | `/metrics` | Prometheus text exposition |
| `src/app/trading/strategy_api.py` | DELETE | `/api/trading/strategies/{strategy_id}` | 204 No Content |

The only internal route excluded from OpenAPI is `POST /api/hermes/assistant/tools/execute`, the service-token assistant-tool executor. It is mounted through `FeatureModule.internal_routers` and retains its explicit `require_service_token` dependency. Internal routes are not a general-purpose exception category; new internal handlers must use the feature's internal router and service-token authorization.

A route must not use `include_in_schema=False` merely because it is experimental. Browser-facing JSON routes require typed request and response models. File-transfer and redirect routes must document their response media type or status as shown above.

## Web client types outside the gateway contract

Web code types gateway calls with the generated OpenAPI types (`src/apps/web/src/api/generated/core.ts` and each feature's `api/generated.ts`), and stream messages with the Zod schemas in `src/apps/web/src/api/schemas/` and next to each protocol's types. The declarations below have names that look like API contracts but describe something else: another service's protocol, a browser-internal message, or a document the web client owns. The `web_handwritten_api_types` metric skips them. Each row must match at least one declaration (the metric refuses stale rows), and a pattern covers only the files and names it states.

| Web source | Type | What it describes |
|---|---|---|
| `src/apps/web/src/features/assistant/workspace/provider-adapters.ts` | `*` | Request and response bodies of external provider HTTP APIs (Anthropic Messages, OpenAI Chat Completions) |
| `src/apps/web/src/features/assistant/workspace/provider.ts` | `Model*` | The browser's model provider interface |
| `src/apps/web/src/features/assistant/workspace/speech-services.ts` | `*` | The speech service's HTTP protocol (a separate speech host, not the gateway) |
| `src/apps/web/src/features/assistant/workspace/tool-registry.ts` | `ToolExecutionRequest` | Calls into the browser's tool registry |
| `src/apps/web/src/features/assistant/workspace/events.ts` | `AssistantWorkspaceEventPayload` | Records of the browser event store |
| `src/apps/web/src/features/assistant/workspace/companion-initiative-arbiter.ts` | `CompanionInitiativeRequest` | Arbitration between the browser's initiative sources |
| `src/apps/web/src/features/assistant/workspace/desktop-companion-delivery.ts` | `DesktopCompanionDeliveryRequest` | An entry of the browser's delivery queue |
| `src/apps/web/src/features/assistant/workspace/desktop-companion-expression-enricher.ts` | `MutableDeliveryRequest` | The same queue entry while it is enriched |
| `src/apps/web/src/features/assistant/workspace/desktop-temporal-capture.ts` | `TemporalDesktopPayload` | A browser capture result, later mapped into `AssistantContextChatRequest` and `DesktopCompanionObserveRequest` fields |
| `src/apps/web/src/features/assistant/workspace/live-voice-cue-asset-bridge.ts` | `*Payload` | Window event details between the voice cue modules |
| `src/apps/web/src/features/assistant/workspace/live-voice-unified-audio-controller.ts` | `LiveVoiceRequestPayload` | The browser correlation id (`live_voice_turn_id`) the chat request carries for fetch middleware; the gateway ignores it |
| `src/apps/web/src/features/storyteller/StoryAudioPanel.tsx` | `StoryAudioWebSocketPayload` | The start message on the `/ws/audiobook` WebSocket |
| `src/apps/web/src/features/storyteller/storyModel.ts` | `StoryGenerationRequest` | Mutation variables; the wire body is `CreateJobRequest` |
| `src/apps/web/src/features/trading/indicators/indicatorWorkerProtocol.ts` | `IndicatorWorker*` | Messages to and from the indicator Web Worker |
| `src/apps/web/src/features/trading/indicators/indicatorScheduler.ts` | `PendingRequest` | The scheduler's record of a worker request |
| `src/apps/web/src/features/trading/persistence/workspaceDocument.ts` | `*` | Trading workspace document content, stored in `TradingDocument.payload` and owned by the web client |
| `src/apps/web/src/features/trading/TradingWatchlist.tsx` | `WatchlistPayload` | Watchlist document content in `TradingDocument.payload` |
| `src/apps/web/src/features/trading/tradingFormula.ts` | `TradingFormulaPayload` | Formula document content in `TradingDocument.payload` |
| `src/apps/web/src/features/rpg/*` | `*` | The RPG web surface, which is being retired and keeps its handwritten clients until then (DECISIONS 2026-10-03) |

Stream and WebSocket messages are checked at runtime where they enter the app: chat, job event and trading stream messages and job output references in `src/apps/web/src/api/schemas/streams.ts`; the live STT, PCM control and speculation messages in `src/apps/web/src/features/assistant/workspace/live-voice-messages.ts`; story audio control messages in `src/apps/web/src/features/storyteller/storyAudioMessages.ts`.
