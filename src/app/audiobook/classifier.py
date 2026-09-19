"""Bounded local LLM classification over immutable source span IDs."""
from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from app.providers import ChatMessage
from app.shared import get_provider


_SYSTEM = (
    "Classify audiobook source spans. Return one JSON object with exactly the "
    "keys span_id, speaker, role, delivery. Each value must be a string. "
    "role must be narration, dialogue, heading, or other. speaker is a known "
    "canonical name or a proposed name. Never return or rewrite source prose. "
    "Do not add markdown, explanation, confidence, or extra keys."
)


def local_classifier() -> tuple[Callable[[dict[str, Any]], str], dict[str, Any]] | None:
    """Use only the local LM Studio provider; absent runtime falls back to review."""
    try:
        provider = get_provider("lmstudio")
    except Exception:
        return None
    if provider is None:
        return None
    details: dict[str, Any] = {"mode": "local_llm_classifier", "provider_id": "lmstudio",
                               "model": None, "version": "audiobook-classifier-v1"}
    unavailable = False

    def classify(context: dict[str, Any]) -> str:
        nonlocal unavailable
        if unavailable:
            raise RuntimeError("local classifier unavailable")
        messages = [ChatMessage(role="system", content=_SYSTEM),
                    ChatMessage(role="user", content=json.dumps(
                        context, ensure_ascii=False, sort_keys=True))]
        try:
            response = provider.chat_completion(messages=messages, stream=False)
        except Exception:
            unavailable = True
            raise
        details["model"] = getattr(response, "model", None)
        content = getattr(response, "content", "")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("classifier returned an empty response")
        return content

    return classify, details
