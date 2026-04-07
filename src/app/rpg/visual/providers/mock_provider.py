"""Phase 12.10 — Mock image provider for deterministic local development."""
from __future__ import annotations

from pathlib import Path

from .base import BaseImageProvider, ImageGenerationResult


class MockImageProvider(BaseImageProvider):
    """Deterministic placeholder image provider for development/testing."""
    provider_name = "mock"

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
        """Generate a placeholder image from bundled assets."""
        candidate_paths = [
            Path("src/static/img/rpg_placeholder.png"),
            Path("src/static/img/placeholder.png"),
        ]
        for path in candidate_paths:
            if path.exists():
                return ImageGenerationResult(
                    ok=True,
                    status="complete",
                    image_bytes=path.read_bytes(),
                    mime_type="image/png",
                    revised_prompt=prompt,
                    moderation_status="approved",
                    moderation_reason="",
                )

        return ImageGenerationResult(
            ok=False,
            status="failed",
            error="mock_placeholder_not_found",
            moderation_status="approved",
            moderation_reason="",
        )