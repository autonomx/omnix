"""Voice Studio Phase 7 routes: recipes and batches, API clients, the ``/api/voice/v1`` facade, MCP, dictation.

The facade and the MCP endpoint are public paths for the session middleware
(the voice feature declares them): they authenticate with a voice client credential (``client_api.bound_client``)
and run in that credential's workspace. Everything else is a session route.
"""
from __future__ import annotations

import logging
from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Request, Response, UploadFile
from fastapi.routing import APIRoute
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

_ROUTE_SENTINEL = "_omnix_voice_automation_routes_registered"
MCP_PROTOCOL_VERSION = "2025-06-18"
_MAX_DICTATION_BYTES = 20 * 1024 * 1024


# --- models ---------------------------------------------------------------------------------------


class RecipeStep(BaseModel):
    tool: str = Field(max_length=40)
    settings: dict[str, Any] = Field(default_factory=dict)


class Recipe(BaseModel):
    id: str
    name: str
    version: int
    steps: list[RecipeStep]
    created_at: str
    updated_at: str


class RecipeWrite(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    steps: list[RecipeStep] = Field(min_length=1, max_length=12)


class RecipeList(BaseModel):
    recipes: list[Recipe]
    tools: list[str]


class BatchItem(BaseModel):
    id: str
    position: int
    source_asset_id: str
    current_asset_id: str
    step_index: int
    status: str
    job_id: str
    attempts: int
    outputs: list[dict[str, Any]]
    error: str
    output_name: str


class BatchRun(BaseModel):
    id: str
    recipe_id: str
    recipe_version: int
    title: str
    watch_folder: str
    status: str
    created_at: str
    updated_at: str
    steps: list[dict[str, Any]] = Field(default_factory=list)
    counts: dict[str, int] = Field(default_factory=dict)
    items: list[BatchItem] = Field(default_factory=list)


class BatchList(BaseModel):
    runs: list[BatchRun]


class BatchStart(BaseModel):
    recipe_id: str = Field(min_length=1, max_length=200)
    asset_ids: list[str] = Field(min_length=1, max_length=1000)
    title: str = Field(default="", max_length=200)


class ClientCredential(BaseModel):
    id: str
    name: str
    owner_user_id: str
    capabilities: list[str]
    expires_at: str | None = None
    revoked_at: str | None = None
    last_used_at: str | None = None
    created_at: str
    # Present only in the answer that issues it: the token is never shown again.
    token: str | None = None


class ClientCredentialList(BaseModel):
    clients: list[ClientCredential]
    capabilities: list[str]


class ClientCredentialWrite(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    capabilities: list[str] = Field(min_length=1, max_length=10)
    expires_in_days: int | None = Field(default=90, ge=1, le=3650)


class Revoked(BaseModel):
    revoked: bool


class ToolInfo(BaseModel):
    name: str
    description: str
    capability: str
    allowed: bool
    input_schema: dict[str, Any]


class ToolList(BaseModel):
    tools: list[ToolInfo]


class ToolCall(BaseModel):
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolResult(BaseModel):
    result: dict[str, Any]


class SpeakRequest(BaseModel):
    text: str = Field(min_length=1, max_length=20000)
    voice: str = Field(default="", max_length=200)
    language: str = Field(default="en", max_length=16)
    engine: str = Field(default="", max_length=64)


class TranscribeRequest(BaseModel):
    asset_id: str = Field(min_length=1, max_length=200)
    language: str = Field(default="", max_length=16)
    diarize: bool = True
    speakers: int = Field(default=0, ge=0, le=8)


class DesignRequest(BaseModel):
    description: str = Field(min_length=1, max_length=600)
    preview_text: str = Field(default="", max_length=300)
    language: str = Field(default="en", max_length=16)
    seeds: list[int] = Field(default_factory=list, max_length=3)


class IsolateRequest(BaseModel):
    asset_id: str = Field(min_length=1, max_length=200)
    model: str = Field(default="roformer", pattern="^(roformer|demucs)$")


class ClientAudio(BaseModel):
    asset_id: str
    title: str
    mime_type: str
    size: int


class Dictation(BaseModel):
    text: str
    language: str
    duration: float


class DictationWarm(BaseModel):
    ready: bool
    detail: str = ""


# --- helpers ---------------------------------------------------------------------------------------


# Bodies the facade takes: an upload, or JSON (a speak request is at most 20,000 characters).
_FACADE_JSON_BYTES = 1024 * 1024


class CredentialFirstRoute(APIRoute):
    """A facade route that authenticates its voice client credential, and refuses a body without a
    ``Content-Length`` or over its limit, before the body is read: an anonymous caller of a public path
    can neither stream an upload to disk nor a large JSON document into memory."""

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        from .client_api import MAX_CLIENT_AUDIO_BYTES, bound_client

        handler = super().get_route_handler()
        limit = MAX_CLIENT_AUDIO_BYTES if self.path == "/api/voice/v1/audio" else _FACADE_JSON_BYTES

        async def guarded(request: Request) -> Response:
            credential = await bound_client(request.headers.get("authorization"))
            if request.method in {"POST", "PUT", "PATCH"}:
                lengths = request.headers.getlist("content-length")
                if len(lengths) != 1 or not lengths[0].isascii() or not lengths[0].isdecimal():
                    raise HTTPException(status_code=411, detail="content_length_required")
                if int(lengths[0]) > limit:
                    raise HTTPException(status_code=413, detail="request_too_large")
            request.state.voice_client = credential
            return await handler(request)

        return guarded


async def _client(request: Request, authorization: str | None = Header(default=None)) -> dict[str, Any]:  # noqa: B008
    """The credential the route already authenticated (``CredentialFirstRoute``)."""
    from .client_api import bound_client

    credential = getattr(request.state, "voice_client", None)
    return credential if credential is not None else await bound_client(authorization)


def _call(credential: dict[str, Any], name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    from app.persistence.module_states import ModuleNotAcceptingWork

    from .client_api import ClientCapabilityRefused, call_tool

    try:
        return call_tool(credential, name, arguments)
    except ClientCapabilityRefused as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ModuleNotAcceptingWork as exc:
        raise HTTPException(status_code=503, detail=f"module_{exc.state.state}", headers={"Retry-After": "30"}) from exc


def _mcp_result(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _mcp_error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def handle_mcp(credential: dict[str, Any], message: dict[str, Any]) -> dict[str, Any] | None:
    """One MCP JSON-RPC message: initialize, ping, tools/list or tools/call (notifications get no answer)."""
    import json

    from app.persistence.module_states import ModuleNotAcceptingWork

    from .client_api import ClientCapabilityRefused, call_tool, registered_tools

    request_id, method = message.get("id"), str(message.get("method") or "")
    if request_id is None:
        return None  # a notification (notifications/initialized and the like)
    if method == "initialize":
        return _mcp_result(request_id, {"protocolVersion": MCP_PROTOCOL_VERSION,
                                        "capabilities": {"tools": {"listChanged": False}},
                                        "serverInfo": {"name": "omnix-voice", "version": "1.0.0"}})
    if method == "ping":
        return _mcp_result(request_id, {})
    if method == "tools/list":
        tools = [tool for tool in registered_tools().values()
                 if not tool.capability or tool.capability in credential["capabilities"]]
        return _mcp_result(request_id, {"tools": [{"name": tool.name, "description": tool.description,
                                                   "inputSchema": tool.input_schema} for tool in tools]})
    if method == "tools/call":
        params: dict[str, Any] = message["params"] if isinstance(message.get("params"), dict) else {}
        try:
            result = call_tool(credential, str(params.get("name") or ""), params.get("arguments") or {})
        except (ClientCapabilityRefused, LookupError, ValueError, ModuleNotAcceptingWork) as exc:
            return _mcp_result(request_id, {"content": [{"type": "text", "text": str(exc)}], "isError": True})
        except Exception:  # one failing call answers as an error; the rest of a batch still runs
            logger.warning("Voice MCP tool %s failed", params.get("name"), exc_info=True)
            return _mcp_result(request_id, {"content": [{"type": "text", "text": "the tool failed"}], "isError": True})
        return _mcp_result(request_id, {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}],
                                        "structuredContent": result, "isError": False})
    return _mcp_error(request_id, -32601, f"method not found: {method}")


# --- registration ----------------------------------------------------------------------------------


def register_automation_routes(router: APIRouter, state: Any) -> None:
    if getattr(state, _ROUTE_SENTINEL, False):
        return
    setattr(state, _ROUTE_SENTINEL, True)
    from app.runtime.tenant_context import TenantAccessDenied
    from app.security.secrets import SecretStoreUnavailable

    from . import automation, client_api
    from .job_submission import use_job_registry

    use_job_registry(lambda: getattr(state, "job_handler_registry", None))
    facade = APIRouter(route_class=CredentialFirstRoute)

    def _not_found(exc: Exception) -> HTTPException:
        return HTTPException(status_code=404, detail=str(exc) or "not_found")

    # Recipes and batches.
    @router.get("/api/voice/recipes", response_model=RecipeList)
    def list_recipes() -> dict[str, Any]:
        return {"recipes": automation.list_recipes(), "tools": sorted(automation.TOOLS)}

    @router.post("/api/voice/recipes", response_model=Recipe, status_code=201)
    def create_recipe(write: RecipeWrite) -> dict[str, Any]:
        try:
            return automation.save_recipe(name=write.name, steps=[step.model_dump() for step in write.steps])
        except automation.RecipeError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.put("/api/voice/recipes/{recipe_id}", response_model=Recipe)
    def update_recipe(recipe_id: str, write: RecipeWrite) -> dict[str, Any]:
        try:
            return automation.save_recipe(name=write.name, steps=[step.model_dump() for step in write.steps],
                                          recipe_id=recipe_id)
        except automation.RecipeError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except automation.AutomationNotFound as exc:
            raise _not_found(exc) from exc

    @router.delete("/api/voice/recipes/{recipe_id}", response_model=Revoked)
    def delete_recipe(recipe_id: str) -> dict[str, Any]:
        try:
            automation.delete_recipe(recipe_id)
        except automation.AutomationNotFound as exc:
            raise _not_found(exc) from exc
        return {"revoked": True}

    @router.get("/api/voice/batches", response_model=BatchList)
    def list_batches() -> dict[str, Any]:
        return {"runs": automation.list_runs()}

    @router.post("/api/voice/batches", response_model=BatchRun, status_code=201)
    def start_batch(start: BatchStart) -> dict[str, Any]:
        try:
            return automation.start_batch(recipe_id=start.recipe_id, asset_ids=start.asset_ids, title=start.title)
        except automation.RecipeError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except automation.AutomationNotFound as exc:
            raise _not_found(exc) from exc

    @router.get("/api/voice/batches/{run_id}", response_model=BatchRun)
    def get_batch(run_id: str) -> dict[str, Any]:
        try:
            return automation.get_run(run_id)
        except automation.AutomationNotFound as exc:
            raise _not_found(exc) from exc

    @router.post("/api/voice/batches/{run_id}/cancel", response_model=BatchRun)
    def cancel_batch(run_id: str) -> dict[str, Any]:
        try:
            return automation.cancel_run(run_id)
        except automation.AutomationNotFound as exc:
            raise _not_found(exc) from exc

    # API client credentials (workspace admins).
    def _admin_only(exc: Exception) -> HTTPException:
        return HTTPException(status_code=403, detail="workspace_admin_required")

    @router.get("/api/voice/clients", response_model=ClientCredentialList)
    def list_clients() -> dict[str, Any]:
        try:
            return {"clients": client_api.list_credentials(), "capabilities": sorted(client_api.CAPABILITIES)}
        except TenantAccessDenied as exc:
            raise _admin_only(exc) from exc

    @router.post("/api/voice/clients", response_model=ClientCredential, status_code=201)
    def issue_client(write: ClientCredentialWrite) -> dict[str, Any]:
        try:
            return client_api.issue_credential(name=write.name, capabilities=write.capabilities,
                                               expires_in_days=write.expires_in_days)
        except TenantAccessDenied as exc:
            raise _admin_only(exc) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except SecretStoreUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @router.delete("/api/voice/clients/{client_id}", response_model=Revoked)
    def revoke_client(client_id: str) -> dict[str, Any]:
        try:
            return {"revoked": client_api.revoke_credential(client_id)}
        except TenantAccessDenied as exc:
            raise _admin_only(exc) from exc

    # The client facade: credential-authenticated, in the credential's workspace.
    @facade.get("/api/voice/v1/tools", response_model=ToolList)
    def client_tools(credential: dict[str, Any] = Depends(_client)) -> dict[str, Any]:  # noqa: B008
        return {"tools": [{"name": tool.name, "description": tool.description, "capability": tool.capability,
                           "allowed": not tool.capability or tool.capability in credential["capabilities"],
                           "input_schema": tool.input_schema} for tool in client_api.registered_tools().values()]}

    @facade.post("/api/voice/v1/tools/{name}", response_model=ToolResult)
    def client_call(name: str, call: ToolCall, credential: dict[str, Any] = Depends(_client)) -> dict[str, Any]:  # noqa: B008
        return {"result": _call(credential, name, call.arguments)}

    @facade.post("/api/voice/v1/audio", response_model=ClientAudio, status_code=201)
    def client_audio(file: UploadFile = File(...),  # noqa: B008
                     credential: dict[str, Any] = Depends(_client)) -> dict[str, Any]:  # noqa: B008
        """Store a recording for ``transcribe`` or ``isolate`` (a client holding either may upload)."""
        try:
            return client_api.store_client_audio(credential, file.filename or "audio.wav", file.file)
        except client_api.ClientCapabilityRefused as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=413 if "too large" in str(exc) else 422, detail=str(exc)) from exc

    @facade.post("/api/voice/v1/speak", response_model=ToolResult)
    def client_speak(request: SpeakRequest, credential: dict[str, Any] = Depends(_client)) -> dict[str, Any]:  # noqa: B008
        return {"result": _call(credential, "speak", request.model_dump())}

    @facade.post("/api/voice/v1/transcribe", response_model=ToolResult)
    def client_transcribe(request: TranscribeRequest, credential: dict[str, Any] = Depends(_client)) -> dict[str, Any]:  # noqa: B008
        return {"result": _call(credential, "transcribe", request.model_dump())}

    @facade.get("/api/voice/v1/voices", response_model=ToolResult)
    def client_voices(credential: dict[str, Any] = Depends(_client)) -> dict[str, Any]:  # noqa: B008
        return {"result": _call(credential, "list_voices", {})}

    @facade.post("/api/voice/v1/design", response_model=ToolResult)
    def client_design(request: DesignRequest, credential: dict[str, Any] = Depends(_client)) -> dict[str, Any]:  # noqa: B008
        return {"result": _call(credential, "design_voice", request.model_dump())}

    @facade.post("/api/voice/v1/isolate", response_model=ToolResult)
    def client_isolate(request: IsolateRequest, credential: dict[str, Any] = Depends(_client)) -> dict[str, Any]:  # noqa: B008
        return {"result": _call(credential, "isolate", request.model_dump())}

    @facade.get("/api/voice/v1/jobs/{job_id}", response_model=ToolResult)
    def client_job(job_id: str, credential: dict[str, Any] = Depends(_client)) -> dict[str, Any]:  # noqa: B008
        return {"result": _call(credential, "job_status", {"job_id": job_id})}

    @facade.post("/mcp/voice", response_model=None, responses={
        200: {"description": "A JSON-RPC 2.0 response, or an array of them for a batch",
              "content": {"application/json": {"schema": {"type": "object"}}}},
        202: {"description": "Only notifications were sent: no body"},
    })
    def mcp_voice(body: dict[str, Any] | list[dict[str, Any]],
                  credential: dict[str, Any] = Depends(_client)) -> Any:  # noqa: B008
        """MCP over streamable HTTP (JSON responses): initialize, tools/list, tools/call, ping."""
        from fastapi.responses import JSONResponse

        messages = body if isinstance(body, list) else [body]
        answers = [answer for message in messages if isinstance(message, dict)
                   if (answer := handle_mcp(credential, message)) is not None]
        if not answers:
            return Response(status_code=202)
        return JSONResponse(answers if isinstance(body, list) else answers[0])

    router.include_router(facade)

    # Push-to-talk dictation (session route): the batch engine, so any supported language works.
    @router.post("/api/voice/dictate", response_model=Dictation)
    def dictate(file: UploadFile = File(...), language: str = Form("")) -> dict[str, Any]:  # noqa: B008
        from .transcription import TranscriptionRequestError, transcribe_timed_audio

        audio = file.file.read(_MAX_DICTATION_BYTES + 1)
        if not audio:
            raise HTTPException(status_code=422, detail="dictation_empty")
        if len(audio) > _MAX_DICTATION_BYTES:
            raise HTTPException(status_code=413, detail="dictation_too_long")
        try:
            document = transcribe_timed_audio(audio, file.filename or "dictation.webm", language=language.strip()[:16],
                                              diarize=False)
        except TranscriptionRequestError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return {"text": document.text, "language": document.language, "duration": document.duration}

    @router.post("/api/voice/dictate/warm", response_model=DictationWarm)
    def dictate_warm() -> dict[str, Any]:
        """Load the batch engine ahead of a dictation (the composer opened); it unloads again when idle."""
        from app.providers.service import get_stt_provider

        provider = get_stt_provider()
        warm = getattr(provider, "warm_timed", None)
        if warm is None:
            return {"ready": False, "detail": "the speech-to-text provider has no batch engine"}
        return warm()


__all__ = ["handle_mcp", "register_automation_routes"]
