"""Canonical contracts for shared image generation jobs."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


ImageJobErrorCode = Literal[
    "image_generation_disabled",
    "image_provider_unavailable",
    "image_invalid_request",
    "image_generation_failed",
    "image_output_missing",
    "image_asset_store_failed",
]


class ImageGenerateInput(BaseModel):
    """Validated payload accepted by the shared ``image.generate`` executor."""

    prompt: str = Field(min_length=1, max_length=8_000)
    negative_prompt: str = Field(default="", max_length=8_000)
    provider_id: str = ""
    width: int = Field(default=768, ge=128, le=4_096)
    height: int = Field(default=768, ge=128, le=4_096)
    style: str = Field(default="", max_length=200)
    seed: int | None = Field(default=None, ge=0)
    steps: int | None = Field(default=None, ge=1, le=200)
    guidance_scale: float | None = Field(default=None, ge=0, le=100)
    unload_after_generation: bool = False
    no_cache: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("prompt", "negative_prompt", "provider_id", "style", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> str:
        return str(value or "").strip()

    @field_validator("width", "height")
    @classmethod
    def validate_dimension_step(cls, value: int) -> int:
        if value % 64:
            raise ValueError("image dimensions must be multiples of 64")
        return value

    def provider_key(self) -> str:
        return normalize_image_provider_id(self.provider_id)

    def provider_payload(self) -> dict[str, Any]:
        """Map the shared contract to the existing image service payload."""

        return {
            "prompt": self.prompt,
            "negative_prompt": self.negative_prompt,
            "provider": self.provider_key(),
            "width": self.width,
            "height": self.height,
            "style": self.style,
            "seed": self.seed,
            "steps": self.steps,
            "guidance_scale": self.guidance_scale,
            "unload_after_generation": self.unload_after_generation,
            "no_cache": self.no_cache,
            "metadata": dict(self.metadata),
        }


class ImageOutputRef(BaseModel):
    """Small metadata-only reference emitted by a completed image job."""

    type: Literal["image"] = "image"
    asset_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    mime_type: str = Field(min_length=1)
    width: int = Field(ge=1)
    height: int = Field(ge=1)
    provider_id: str = ""
    seed: int | None = None


def normalize_image_provider_id(provider_id: str | None) -> str:
    """Convert a facade image provider ID into the image-service registry key."""

    normalized = str(provider_id or "").strip()
    if not normalized:
        return ""
    if ":" not in normalized:
        return normalized
    family, key = normalized.split(":", 1)
    if family != "image":
        raise ValueError(f"provider is not a standalone image provider: {normalized}")
    if not key.strip():
        raise ValueError("image provider key is empty")
    return key.strip()


def image_title_from_prompt(prompt: str, *, fallback: str = "Generated image", limit: int = 80) -> str:
    compact = " ".join(str(prompt or "").split())
    if not compact:
        return fallback
    if len(compact) <= limit:
        return compact
    return compact[: max(1, limit - 1)].rstrip() + "…"
