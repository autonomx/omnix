"""Bounded local LLM classification over immutable source span IDs."""
from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from app.providers import ChatMessage
from app.shared import get_provider, load_settings


_SYSTEM = (
    "Classify audiobook source spans. Return one JSON object with exactly the "
    "keys span_id, speaker, role, delivery. Each value must be a string. "
    "role must be narration, dialogue, heading, or other. speaker is a known "
    "canonical name or a proposed name. Never return or rewrite source prose. "
    "Do not add markdown, explanation, confidence, or extra keys."
)

# Classification is a bounded background operation. Without an explicit
# request timeout, a provider's default (often five minutes) can make a user
# cancellation appear stuck while the worker waits inside one model call.
_CLASSIFIER_REQUEST_TIMEOUT_SECONDS = 45.0


def local_classifier() -> tuple[Callable[[dict[str, Any]], str], dict[str, Any]] | None:
    """Build a classifier from the configured Omnix chat provider.

    The function name is retained for compatibility with existing worker hooks,
    but audiobook analysis must follow the same provider and model selected for
    the rest of the application. If that provider cannot be constructed, the
    initial deterministic pass may use the review queue; a forced reclassification
    is rejected by the worker so it cannot silently overwrite results.
    """
    try:
        provider = get_provider()
    except Exception:
        return None
    if provider is None:
        return None
    provider_id = str(getattr(provider, "provider_name", "") or
                      load_settings().get("provider", "configured"))
    provider_config = getattr(provider, "config", None)
    configured_model = str(getattr(provider_config, "model", "") or "") or None
    details: dict[str, Any] = {
        "mode": "configured_llm_classifier", "provider_id": provider_id,
        "model": configured_model, "version": "audiobook-classifier-v2",
    }
    def classify(context: dict[str, Any]) -> str:
        messages = [ChatMessage(role="system", content=_SYSTEM),
                    ChatMessage(role="user", content=json.dumps(
                        context, ensure_ascii=False, sort_keys=True))]
        try:
            response = provider.chat_completion(
                messages=messages,
                stream=False,
                request_timeout_seconds=_CLASSIFIER_REQUEST_TIMEOUT_SECONDS,
            )
        except Exception:
            raise
        details["model"] = getattr(response, "model", None) or configured_model
        content = getattr(response, "content", "")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("classifier returned an empty response")
        return content

    return classify, details
