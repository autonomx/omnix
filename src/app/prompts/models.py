"""Prompt/template models for shared rendering metadata."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


ProviderPayloadFormat = Literal["chat_messages", "completion_text", "image_prompt", "json_instruction"]


class PromptTemplate(BaseModel):
    id: str
    version: str
    module: str
    text: str
    variables: list[str] = Field(default_factory=list)
    provider_payload_format: ProviderPayloadFormat = "chat_messages"
    metadata: dict[str, Any] = Field(default_factory=dict)
    safety_metadata: dict[str, Any] = Field(default_factory=dict)
    grounding_metadata: dict[str, Any] = Field(default_factory=dict)


class PromptRenderRequest(BaseModel):
    template: PromptTemplate
    variables: dict[str, Any] = Field(default_factory=dict)


class RenderedPrompt(BaseModel):
    template_id: str
    version: str
    module: str
    rendered_text: str
    variables: dict[str, Any]
    provider_payload_format: ProviderPayloadFormat
    rendering_metadata: dict[str, Any] = Field(default_factory=dict)
    safety_metadata: dict[str, Any] = Field(default_factory=dict)
    grounding_metadata: dict[str, Any] = Field(default_factory=dict)
    replay_metadata: dict[str, Any] = Field(default_factory=dict)
