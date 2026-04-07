"""Phase 12.10 / 12.12 — Visual provider registry."""
from __future__ import annotations

import os

from .base import BaseImageProvider
from .comfy_provider import ComfyImageProvider
from .mock_provider import MockImageProvider
from .openai_provider import OpenAIImageProvider


def get_image_provider() -> BaseImageProvider:
    """Return the configured image provider."""
    provider = os.getenv("RPG_IMAGE_PROVIDER", "mock").strip().lower()
    if provider == "comfy":
        return ComfyImageProvider()
    if provider == "openai":
        return OpenAIImageProvider()
    return MockImageProvider()
