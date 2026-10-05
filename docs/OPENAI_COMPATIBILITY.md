# OpenAI-compatible endpoints

Omnix exposes one OpenAI-shaped HTTP surface and can also call upstream
providers that implement the OpenAI chat-completions contract. Keep them
separate when configuring clients:

| Surface | Base URL | Purpose | Authority boundary |
| --- | --- | --- | --- |
| Agent model gateway | `http://127.0.0.1:8000/api/agent-model/v1` | Omnix agent-runtime model calls | Requires an existing durable run and exact run-bound model; budgets and provider selection are enforced by Omnix |
| Upstream compatible provider | Configured provider URL, usually ending in `/v1` | LM Studio, llama.cpp, OpenRouter, Azure-compatible deployments, or another OpenAI-shaped service consumed by Omnix | Provider credentials and upstream policy remain external to Omnix |

The word “compatible” means that the request and response shapes are close
enough for common clients. It does not mean that every OpenAI product,
parameter, authentication mode, tool behavior, or realtime event is
implemented. Check the endpoint tables and limitations below before connecting
an external application.

```omnix-diagram openai-compatibility
```

Local clients that need a general `/v1` chat endpoint, such as Open WebUI,
SillyTavern or SDK scripts, should use the model server directly: LM Studio
(`http://127.0.0.1:1234/v1`) or a llama.cpp server. Omnix no longer ships a
standalone compatibility server on port `8101`; its chat and transcription
endpoints returned placeholder text, and its speech endpoint duplicated the
TTS service.

## Agent model gateway

The main FastAPI gateway exposes a second, stricter OpenAI-shaped surface at
`/api/agent-model/v1`. It is intended for Omnix's governed agent runtime and
Pi/Codex-style model transports, not as a general public proxy.

### Endpoint reference

| Method | Path | Required headers | Purpose |
| --- | --- | --- | --- |
| `GET` | `/api/agent-model/v1/models` | `X-Omnix-Agent-Run-Id` | Return the one model bound to the durable agent run |
| `POST` | `/api/agent-model/v1/chat/completions` | `X-Omnix-Client`; `X-Omnix-Agent-Run-Id`; optional `X-Omnix-Agent-Session-Id` | Run a model call within the existing run's provider, model, context, budget, and policy boundary |

The model endpoint returns an OpenAI-style `object: "list"` response. The
returned model ID has the form `<provider_id>::<model_id>` and must be passed
unchanged to `chat/completions`.

Example discovery request:

```bash
curl http://127.0.0.1:8000/api/agent-model/v1/models \
  -H "X-Omnix-Agent-Run-Id: <durable-agent-run-id>"
```

Example completion request:

```bash
curl http://127.0.0.1:8000/api/agent-model/v1/chat/completions \
  -H "X-Omnix-Agent-Run-Id: <durable-agent-run-id>" \
  -H "X-Omnix-Agent-Session-Id: <optional-session-id>" \
  -H "X-Omnix-Client: cli" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "openai_compatible::local-model",
    "messages": [
      {"role": "user", "content": "Continue the active implementation task."}
    ],
    "temperature": 0.2,
    "max_tokens": 800,
    "stream": true
  }'
```

The example provider/model pair is illustrative. Use the exact ID returned by
`/models` for the selected run. The run's durable model specification is the
authority; a caller cannot use this route to switch providers or models.

### Supported request features

`chat/completions` accepts the standard fields needed by the agent transport:

- `model` and `messages` are required.
- `stream` selects a server-sent event response.
- `tools` and `tool_choice` may be passed through as model-call options.
- `temperature`, `max_tokens`, and `reasoning_effort` are supported when the
  selected provider supports them.
- Message content can be plain text or a list containing text and image parts.
- `X-Omnix-Agent-Session-Id` binds compatible conversation state for providers
  that support it.

Streaming responses use `chat.completion.chunk` objects followed by
`data: [DONE]`. Provider usage is recorded when available so the durable run
budget can be enforced.

### Security and failure semantics

The custom Omnix headers bind the request to a run; they are not a replacement
for gateway authentication. Protect the gateway with the deployment's normal
auth and network controls.

The gateway deliberately adds an authoritative run context to every provider
call, validates the requested model against the run specification, and bounds
output tokens against the run budget. Model output can contain tool-call
proposals, but this endpoint does not grant capabilities or execute tools.

Common responses include:

| Status | Meaning |
| ---: | --- |
| `403` | Requested model is outside the durable run specification |
| `404` | Agent run does not exist |
| `409` | Run budget is exhausted or a local agent budget rule rejected the call |
| `502` | Provider returned an invalid response or output could not be metered when metering is required |
| `503` | The selected provider is unavailable |

## OpenAI-compatible upstream providers

Omnix can consume an upstream service that implements the OpenAI chat
completions contract through the `openai_compatible` provider. Configure its
base URL, API key, and model in the provider/settings surface. The provider
normalizes the base URL and calls:

| Method | Upstream path | Used for |
| --- | --- | --- |
| `POST` | `<base_url>/chat/completions` | Non-streaming and streaming chat |
| `GET` | `<base_url>/v1/models` or the provider's configured model discovery path | Model discovery where supported by the selected adapter |

For the shared OpenAI-compatible provider, configure the base URL as the API
root expected by the adapter. A common local example is
`http://127.0.0.1:1234/v1`; the provider then appends `/chat/completions`.
The provider sends `Authorization: Bearer <api_key>` and requires a non-empty
API key even when a local server ignores it. For a local server, use a dummy
non-secret value only when the server is restricted to the local machine.

Typical compatible targets include LM Studio, llama.cpp servers, OpenRouter,
Azure-style deployments, and other services that preserve the chat-completion
request/response shape. Capability and parameter support still varies by
provider; expose only the options the target can honor.

## Realtime boundary

Omnix also exposes `WS /v1/realtime` for its live-speech service when the
realtime routes are mounted. Its event names intentionally resemble an
OpenAI/Hugging Face realtime subset, but it is an Omnix protocol with Omnix
session, transcript, STT, TTS, interruption, and policy semantics. It is not a
drop-in implementation of the full OpenAI Realtime API.

Use the Live Chat feature and the live-speech compatibility/status contracts to
discover the current event flow. Do not assume that an HTTP `/v1` client can
switch to this WebSocket without implementing the Omnix realtime handshake and
event types.

## Troubleshooting checklist

1. Confirm the main gateway is running on port `8000`.
2. For the agent gateway, verify the run ID exists and call `/models` first.
3. Use the exact `<provider_id>::<model_id>` returned for that run.
4. Check provider/model readiness in `/providers`, `/models`, and
   `/diagnostics` in the web app.
5. Inspect the selected worker, job/run state, logs, and event stream before
   changing client parameters.

## Source of truth

- Agent model gateway: `src/app/platform/agent_runtime/model_gateway.py`
- Shared upstream provider: `src/app/providers/openai_compatible_provider.py`
- Realtime compatibility metadata: `src/app/platform/live_speech/compat.py`
- Provider architecture and authority rules: [ARCHITECTURE.md](ARCHITECTURE.md)
- Local service setup: [SETUP.md](SETUP.md)
