"""Cheap import-time classifier for ambiguous document structure regions."""
from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from app.providers import ChatMessage
from app.shared import get_provider, load_settings


DOCUMENT_STRUCTURE_CLASSIFIER_VERSION = "document-structure-classifier-v1"
_REQUEST_TIMEOUT_SECONDS = 60.0

_SYSTEM = (
    "You classify ambiguous regions of books for audiobook document structure. "
    "This is NOT speaker attribution and NOT literary analysis. Use the supplied "
    "neighboring boundaries, source format, and exact block text. Choose only from "
    "allowed_roles and UNKNOWN is always valid when evidence is insufficient. "
    "Do not rewrite, summarize, or remove source text. Return exactly one JSON object "
    "with key blocks. Each block item must contain exactly block_id, content_role, "
    "confidence. confidence is 0..1. Return no markdown or explanation."
)


def local_structure_classifier() -> tuple[
    Callable[[dict[str, Any]], str], dict[str, Any]
] | None:
    """Use the configured provider at low reasoning effort only for uncertain regions."""
    try:
        provider = get_provider()
    except Exception:
        return None
    if provider is None:
        return None
    provider_id = str(
        getattr(provider, "provider_name", "")
        or load_settings().get("provider", "configured")
    )
    config = getattr(provider, "config", None)
    configured_model = str(getattr(config, "model", "") or "") or None
    details: dict[str, Any] = {
        "mode": "ambiguous_document_region_classifier",
        "provider_id": provider_id,
        "model": configured_model,
        "version": DOCUMENT_STRUCTURE_CLASSIFIER_VERSION,
        "reasoning_effort": "low",
    }

    def classify(context: dict[str, Any]) -> str:
        response = provider.chat_completion(
            messages=[
                ChatMessage(role="system", content=_SYSTEM),
                ChatMessage(
                    role="user",
                    content=json.dumps(context, ensure_ascii=False, sort_keys=True),
                ),
            ],
            stream=False,
            reasoning_effort="low",
            request_timeout_seconds=_REQUEST_TIMEOUT_SECONDS,
        )
        details["model"] = getattr(response, "model", None) or configured_model
        content = getattr(response, "content", "")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("document structure classifier returned an empty response")
        return content

    return classify, details
