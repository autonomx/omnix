"""Contracts for web research and desktop context enrichment."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.research import ResearchMode, normalize_research_mode

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
    web_research_mode: ResearchMode = "disabled"
    legacy_web_search_mode: str | None = Field(default=None, exclude=True)
    internal_research_identity: str | None = Field(default=None, exclude=True)
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

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_research_fields(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        payload = dict(value)
        legacy = payload.get("web_search_mode")
        selected = payload.get("web_research_mode")
        if selected is None:
            selected = legacy
        payload["web_research_mode"] = normalize_research_mode(selected)
        payload["legacy_web_search_mode"] = str(legacy) if legacy is not None else None
        payload.pop("internal_research_identity", None)
        return payload

    @property
    def web_search_mode(self) -> str:
        """Compatibility accessor removed after the legacy request window."""

        return self.legacy_web_search_mode or self.web_research_mode


class AssistantContextBuildResult(BaseModel):
    items: list[AssistantContextItem] = Field(default_factory=list)
    diagnostics: dict[str, Any] = Field(default_factory=dict)
