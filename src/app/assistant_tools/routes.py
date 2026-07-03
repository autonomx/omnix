"""Runtime routes for assistant tool configuration and review."""
from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

from .capability_dashboard import AssistantCapabilityDashboard, build_assistant_capability_dashboard
from .config_store import AssistantToolsConfigPayload, load_assistant_tools_config, save_assistant_tools_config
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

    @app.post("/api/hermes/assistant/tools/review", response_model=HermesAssistantToolReviewPayload, tags=["hermes-assistant-tools"])
    async def hermes_assistant_tool_review_endpoint(request: HermesAssistantToolRequestEnvelope) -> HermesAssistantToolReviewPayload:
        return hermes_assistant_tool_review_payload(request.user_request, request.request)

    @app.post("/api/hermes/assistant/tools/execute", response_model=HermesAssistantToolExecutePayload, tags=["hermes-assistant-tools"])
    async def hermes_assistant_tool_execute_endpoint(request: HermesAssistantToolRequestEnvelope) -> HermesAssistantToolExecutePayload:
        return hermes_assistant_tool_execute_payload(request.user_request, request.request)
