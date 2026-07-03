"""Runtime routes for assistant tool configuration."""
from __future__ import annotations

from fastapi import FastAPI

from .config_store import AssistantToolsConfigPayload, load_assistant_tools_config, save_assistant_tools_config

_ASSISTANT_TOOL_ROUTE_NAMES = {
    "assistant_tools_config",
    "save_assistant_tools_config_endpoint",
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
