"""Runtime routes for assistant tool configuration and review."""
from __future__ import annotations

import asyncio
import os
from urllib.parse import urlencode

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from .capability_dashboard import AssistantCapabilityDashboard, build_assistant_capability_dashboard
from .config_store import AssistantToolsConfigPayload, load_assistant_tools_config, save_assistant_tools_config
from .connections import (
    AssistantToolOAuthClientPayload,
    AssistantToolConnectionStartPayload,
    assistant_tool_connection_start_payload,
    complete_github_connection,
    complete_google_connection,
    save_assistant_tool_oauth_client,
)
from .gate import review_assistant_tool_request
from .hermes_bridge import hermes_assistant_tool_execute_payload, hermes_assistant_tool_review_payload
from .hermes_payloads import HermesAssistantToolExecutePayload, HermesAssistantToolRequestEnvelope, HermesAssistantToolReviewPayload
from .intent import AssistantToolIntent, detect_assistant_tool_intent
from .ledger import AssistantToolLedgerPayload, load_assistant_tool_ledger
from .models import AssistantToolRequest, AssistantToolReviewDecision


class AssistantToolIntentRequest(BaseModel):
    message: str = ""


_ASSISTANT_TOOL_ROUTE_NAMES = {
    "assistant_tools_config",
    "save_assistant_tools_config_endpoint",
    "review_assistant_tool_endpoint",
    "assistant_tool_intent_endpoint",
    "assistant_tool_dashboard_endpoint",
    "assistant_tool_ledger_endpoint",
    "assistant_tool_connection_start_endpoint",
    "assistant_tool_oauth_client_endpoint",
    "assistant_tool_google_callback_endpoint",
    "assistant_tool_github_callback_endpoint",
    "hermes_assistant_tool_review_endpoint",
    "hermes_assistant_tool_execute_endpoint",
}


def _has_assistant_tool_config_routes(app: FastAPI) -> bool:
    return any(getattr(route, "name", "") in _ASSISTANT_TOOL_ROUTE_NAMES for route in app.routes)


def register_assistant_tool_routes(app: FastAPI) -> None:
    if _has_assistant_tool_config_routes(app):
        return

    @app.get("/api/assistant/tools/config", response_model=AssistantToolsConfigPayload, tags=["assistant-tools"])
    async def assistant_tools_config() -> AssistantToolsConfigPayload:
        return load_assistant_tools_config()

    @app.post("/api/assistant/tools/config", response_model=AssistantToolsConfigPayload, tags=["assistant-tools"])
    async def save_assistant_tools_config_endpoint(request: AssistantToolsConfigPayload) -> AssistantToolsConfigPayload:
        return save_assistant_tools_config(request)

    @app.post("/api/assistant/tools/review", response_model=AssistantToolReviewDecision, tags=["assistant-tools"])
    async def review_assistant_tool_endpoint(request: AssistantToolRequest) -> AssistantToolReviewDecision:
        return review_assistant_tool_request(request)

    @app.post("/api/assistant/tools/intent", response_model=AssistantToolIntent, tags=["assistant-tools"])
    async def assistant_tool_intent_endpoint(request: AssistantToolIntentRequest) -> AssistantToolIntent:
        return detect_assistant_tool_intent(request.message)

    @app.get("/api/assistant/tools/dashboard", response_model=AssistantCapabilityDashboard, tags=["assistant-tools"])
    async def assistant_tool_dashboard_endpoint() -> AssistantCapabilityDashboard:
        return build_assistant_capability_dashboard()

    @app.get("/api/assistant/tools/ledger", response_model=AssistantToolLedgerPayload, tags=["assistant-tools"])
    async def assistant_tool_ledger_endpoint(limit: int = 100) -> AssistantToolLedgerPayload:
        return load_assistant_tool_ledger(limit=limit)

    @app.get("/api/assistant/tools/connect/{tool_id}", response_model=AssistantToolConnectionStartPayload, tags=["assistant-tools"])
    async def assistant_tool_connection_start_endpoint(request: Request, tool_id: str) -> AssistantToolConnectionStartPayload:
        return assistant_tool_connection_start_payload(tool_id, str(request.base_url).rstrip("/"))

    @app.post("/api/assistant/tools/connect/{tool_id}/oauth-client", response_model=AssistantToolConnectionStartPayload, tags=["assistant-tools"])
    async def assistant_tool_oauth_client_endpoint(request: Request, tool_id: str, payload: AssistantToolOAuthClientPayload) -> AssistantToolConnectionStartPayload:
        return save_assistant_tool_oauth_client(tool_id, payload, str(request.base_url).rstrip("/"))

    @app.get("/api/assistant/tools/connect/google/callback", tags=["assistant-tools"])
    async def assistant_tool_google_callback_endpoint(request: Request, code: str = "", state: str = "gmail") -> RedirectResponse:
        return _assistant_tool_connection_redirect(complete_google_connection(code, state, str(request.base_url).rstrip("/")))

    @app.get("/api/assistant/tools/connect/github/callback", tags=["assistant-tools"])
    async def assistant_tool_github_callback_endpoint(request: Request, code: str = "", state: str = "github") -> RedirectResponse:
        return _assistant_tool_connection_redirect(complete_github_connection(code, state, str(request.base_url).rstrip("/")))

    @app.post("/api/hermes/assistant/tools/review", response_model=HermesAssistantToolReviewPayload, tags=["hermes-assistant-tools"])
    async def hermes_assistant_tool_review_endpoint(request: HermesAssistantToolRequestEnvelope) -> HermesAssistantToolReviewPayload:
        return hermes_assistant_tool_review_payload(request.user_request, request.request)

    @app.post("/api/hermes/assistant/tools/execute", response_model=HermesAssistantToolExecutePayload, tags=["hermes-assistant-tools"])
    async def hermes_assistant_tool_execute_endpoint(request: HermesAssistantToolRequestEnvelope) -> HermesAssistantToolExecutePayload:
        # Browser actions can navigate to the gateway itself. Keep the
        # synchronous adapter and ledger work off the event loop so that
        # browser.open cannot deadlock while waiting for this gateway to serve
        # the target page.
        return await asyncio.to_thread(
            hermes_assistant_tool_execute_payload,
            request.user_request,
            request.request,
        )


def _assistant_tool_connection_redirect(result) -> RedirectResponse:
    base_url = os.environ.get("OMNIX_ASSISTANT_TOOLS_CONNECT_RETURN_URL", "/chatbot").strip() or "/chatbot"
    params = {
        "assistant_tool": result.tool_id,
        "assistant_tool_connected": "1" if result.connected else "0",
        "assistant_tool_message": result.message,
    }
    separator = "&" if "?" in base_url else "?"
    return RedirectResponse(f"{base_url}{separator}{urlencode(params)}", status_code=303)
