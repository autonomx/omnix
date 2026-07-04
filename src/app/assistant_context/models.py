"""Contracts for web and desktop context enrichment."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

WebSearchMode = Literal["automatic", "manual", "disabled"]
DesktopCaptureMode = Literal["single", "temporal"]


class AssistantContextItem(BaseModel):
    source_id: Literal["web_search", "desktop_vision"]
    title: str
    content: str
    url: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AssistantContextChatRequest(BaseModel):
    content: str = Field(min_length=1)
    provider_id: str | None = None
    model_id: str | None = None
    agent_mode: bool = False
    dry_run: bool = False
    web_search_mode: WebSearchMode = "disabled"
    web_search_requested: bool = False
    web_search_max_results: int = Field(default=5, ge=1, le=8)
    desktop_image_data_url: str | None = None
    desktop_current_image_data_url: str | None = None
    desktop_history_image_data_url: str | None = None
    desktop_combined_image_data_url: str | None = None
    desktop_history_timestamps: list[float] = Field(default_factory=list, max_length=8)
    desktop_capture_mode: DesktopCaptureMode = "single"
    desktop_question: str | None = None
    vision_model_id: str | None = None


class AssistantContextBuildResult(BaseModel):
    items: list[AssistantContextItem] = Field(default_factory=list)
    diagnostics: dict[str, Any] = Field(default_factory=dict)
