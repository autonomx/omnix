"""Phase 12.10 — OpenAI image provider stub."""
from __future__ import annotations

import os

from .base import BaseImageProvider, ImageGenerationResult


class OpenAIImageProvider(BaseImageProvider):
    """OpenAI image generation provider."""
    provider_name = "openai"

    def generate(
        self,
        *,
        prompt: str,
        seed: int | None,
        style: str,
        model: str,
        kind: str,
        target_id: str,
    ) -> ImageGenerationResult:
        """
        Generate an image via OpenAI.
        Expected behavior:
        - submit prompt/model/style
        - retrieve image bytes
        - return ImageGenerationResult
        """
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            return ImageGenerationResult(
                ok=False,
                status="failed",
                error="openai_api_key_missing",
                moderation_status="approved",
                moderation_reason="",
            )

        return ImageGenerationResult(
            ok=False,
            status="failed",
            error="openai_provider_not_implemented",
            moderation_status="approved",
            moderation_reason="",
        )