"""RPG-owned boundary to the process provider service.

Deterministic RPG packages may depend on this adapter, but not on live provider
implementations directly. Tests can replace these functions without importing
provider packages inside deterministic modules.
"""
from __future__ import annotations

from typing import Any


def chat_completion(*, messages: list[dict[str, Any]], stream: bool = False, **kwargs: Any) -> Any:
    from app.providers.service import chat_completion as provider_chat_completion

    return provider_chat_completion(messages=messages, stream=stream, **kwargs)


def get_provider() -> Any:
    from app.providers.service import get_provider as resolve_provider
    from app.apps.rpg.narration.ai.llm_gateway_adapter import adapt_base_provider

    return adapt_base_provider(resolve_provider())
