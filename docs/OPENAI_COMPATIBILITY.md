# OpenAI-compatible endpoints

Omnix exposes two different OpenAI-shaped HTTP surfaces and can also call
upstream providers that implement the OpenAI chat-completions contract. Keep
these surfaces separate when configuring clients:

| Surface | Base URL | Purpose | Authority boundary |
| --- | --- | --- | --- |
| Standalone compatibility server | `http://127.0.0.1:8001/v1` | Local clients such as Open WebUI, SillyTavern, scripts, and SDK examples | Legacy/local compatibility layer; chat and transcription are currently placeholder implementations |
| Agent model gateway | `http://127.0.0.1:8000/api/agent-model/v1` | Omnix agent-runtime model calls | Requires an existing durable run and exact run-bound model; budgets and provider selection are enforced by Omnix |
| Upstream compatible provider | Configured provider URL, usually ending in `/v1` | LM Studio, llama.cpp, OpenRouter, Azure-compatible deployments, or another OpenAI-shaped service consumed by Omnix | Provider credentials and upstream policy remain external to Omnix |

The word “compatible” means that the request and response shapes are close
enough for common clients. It does not mean that every OpenAI product,
parameter, authentication mode, tool behavior, or realtime event is
implemented. Check the endpoint tables and limitations below before connecting
an external application.

```omnix-diagram openai-compatibility
```

## Standalone local compatibility server

The standalone server is implemented in `src/openai_api.py`. It is useful for
local integrations that expect a conventional `/v1` base URL. Start it from
the repository root with a loopback bind:

```powershell
$env:PYTHONPATH = "src"
python -m uvicorn openai_api:app --app-dir src --host 127.0.0.1 --port 8001
```

Or run the module's built-in entry point:

```powershell
python src/openai_api.py
```

The built-in entry point listens on `0.0.0.0:8001`; use the Uvicorn command
when the API should remain local to the workstation. The server currently has
no authentication middleware and allows all CORS origins. Do not expose it to
an untrusted network without placing it behind an authenticated reverse proxy
and an explicit network policy.

### Endpoint reference

| Method | Path | Purpose | Current behavior |
| --- | --- | --- | --- |
| `GET` | `/health` | Process and service status | Returns server status, TTS availability, STT availability, and a timestamp |
| `GET` | `/v1/models` | List model IDs | Returns the models declared in `AVAILABLE_MODELS` in `src/openai_api.py` |
| `POST` | `/v1/chat/completions` | Chat completion | Accepts standard messages and streaming mode, but currently returns deterministic placeholder text rather than calling the configured LLM provider |
| `GET` | `/v1/audio/voices` | List voices | Returns built-in compatibility voices plus discoverable custom voice profiles |
| `GET` | `/v1/audio/voices/{voice_id}` | Read one voice | Returns voice metadata or `404` |
| `GET` | `/v1/audio/voices/{voice_id}/preview` | Preview a voice | Currently returns a JSON placeholder message; it is not an audio preview response |
| `POST` | `/v1/audio/speech` | Text to speech | Routes through the shared TTS provider and returns streamed audio when a provider is configured and ready |
| `POST` | `/v1/audio/transcriptions` | Audio transcription | Route exists, but currently returns a placeholder transcript and does not yet implement OpenAI-style multipart upload processing |

The FastAPI-generated reference is also available while the server is running:

- Swagger UI: `http://127.0.0.1:8001/docs`
- OpenAPI JSON: `http://127.0.0.1:8001/openapi.json`

### Chat completion example

The standalone API accepts the familiar chat-completions shape:

```bash
curl http://127.0.0.1:8001/v1/chat/completions \
  -H "Authorization: Bearer local-dev-only" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "mistral-7b-instruct-v0.2",
    "messages": [
      {"role": "user", "content": "Summarize the Omnix workspace in one sentence."}
    ],
    "temperature": 0.7,
    "stream": false
  }'
```

The standalone server does not currently validate the bearer token. The header
is shown because many OpenAI-compatible clients send it automatically; it is
not a substitute for deployment authentication.

For streaming, set `"stream": true`. The response uses server-sent events with
`data: ...` JSON chunks and a final `data: [DONE]` marker. The current stream is
also deterministic placeholder output.

### OpenAI Python client example

Install the client in the active environment if it is not already available:

```bash
pip install openai
```

Then point its base URL at the standalone server:

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://127.0.0.1:8001/v1",
    api_key="local-dev-only",
)

models = client.models.list()
print([model.id for model in models.data])

completion = client.chat.completions.create(
    model="mistral-7b-instruct-v0.2",
    messages=[{"role": "user", "content": "Hello from an OpenAI-compatible client."}],
)
print(completion.choices[0].message.content)
```

### Speech example

The speech route follows the common JSON request shape and returns an audio
stream. The selected voice must be available to the shared TTS provider:

```bash
curl http://127.0.0.1:8001/v1/audio/speech \
  -H "Authorization: Bearer local-dev-only" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "tts-1",
    "voice": "alloy",
    "input": "Omnix speech compatibility test.",
    "response_format": "mp3"
  }' \
  --output omnix-speech.mp3
```

The requested `response_format` becomes the response media type, but the
actual encoding is supplied by the configured TTS provider. Verify the worker
output before relying on a format in an automated pipeline.

## Agent model gateway

The main FastAPI gateway exposes a second, stricter OpenAI-shaped surface at
`/api/agent-model/v1`. It is intended for Omnix's governed agent runtime and
Pi/Codex-style model transports, not as a general public proxy.

### Endpoint reference

| Method | Path | Required headers | Purpose |
| --- | --- | --- | --- |
| `GET` | `/api/agent-model/v1/models` | `X-Omnix-Agent-Run-Id` | Return the one model bound to the durable agent run |
| `POST` | `/api/agent-model/v1/chat/completions` | `X-Omnix-Agent-Run-Id`; optional `X-Omnix-Agent-Session-Id` | Run a model call within the existing run's provider, model, context, budget, and policy boundary |

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

1. Confirm the process and port: `8001` for the standalone server or `8000` for
   the main gateway.
2. Check `/health`, `/docs`, or `/openapi.json` on the standalone server.
3. For the agent gateway, verify the run ID exists and call `/models` first.
4. Use the exact `<provider_id>::<model_id>` returned for that run.
5. Check provider/model readiness in `/providers`, `/models`, and
   `/diagnostics` in the web app.
6. Inspect the selected worker, job/run state, logs, and event stream before
   changing client parameters.
7. Treat placeholder responses from `src/openai_api.py` as compatibility
   scaffolding, not evidence that a production LLM or STT backend is connected.

## Source of truth

- Standalone compatibility surface: `src/openai_api.py`
- Agent model gateway: `src/app/agent_runtime/model_gateway.py`
- Shared upstream provider: `src/app/providers/openai_compatible_provider.py`
- Realtime compatibility metadata: `src/app/live_speech/compat.py`
- Provider architecture and authority rules: [ARCHITECTURE.md](ARCHITECTURE.md)
- Local service setup: [SETUP.md](SETUP.md)
