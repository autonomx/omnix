"""Phase 12.10 — Base image provider interface."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class ImageGenerationResult:
    """Result from an image generation operation."""
    ok: bool
    status: str
    image_bytes: bytes | None = None
    mime_type: str = "image/png"
    error: str = ""
    revised_prompt: str = ""
    moderation_status: str = "approved"
    moderation_reason: str = ""


class BaseImageProvider:
    """Abstract base for image generation providers."""
    provider_name = "base"

    def generate(
        self,
        *,
        prompt: str,
        seed: Optional[int],
        style: str,
        model: str,
        kind: str,
        target_id: str,
    ) -> ImageGenerationResult:
        """Generate an image and return the result."""
        raise NotImplementedError