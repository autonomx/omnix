"""Bounded local LLM classification over immutable source span IDs."""
from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from app.providers import ChatMessage
from app.shared import get_provider, load_settings


_SYSTEM = (
    "Analyze audiobook story/dialogue spans without rewriting source prose. "
    "Attribute each quote to the character who actually speaks it. Give priority "
    "to a direct speech tag attached to that quote, then immediate same-scene "
    "action/context, then conversational turn-taking. Do not assign a line to a "
    "character merely because that character speaks nearby. When the request "
    "supplies direct_attribution_candidates, treat a single candidate as strong "
    "source evidence. For untagged back-and-forth dialogue, consider speaker "
    "alternation and lower confidence when attribution remains ambiguous. "
    "Obey the task field in the request. For batch story/dialogue analysis, "
    "return exactly one JSON object with keys characters and spans. characters "
    "is an array of objects with required name and aliases plus optional role, "
    "traits, estimated_age, and gender_presentation. aliases and traits are "
    "arrays of strings; the other character metadata values are strings. spans "
    "is an array containing exactly one object per requested "
    "span_id with exactly span_id, speaker, role, delivery, confidence. role "
    "must be narration, dialogue, heading, or other. confidence is a number "
    "from 0 to 1 representing confidence in the speaker/role attribution. For "
    "known speakers, prefer the supplied speaker id or exact canonical name. "
    "Newly discovered people should be listed in characters and may be used as "
    "speaker names. Use aliases only when the text supports them. For legacy "
    "single-span tasks, return span_id, speaker, role, delivery and optional "
    "confidence. Never return source prose, markdown, explanation, or extra keys."
)

# Classification is a bounded background operation. Without an explicit
# request timeout, a provider's default (often five minutes) can make a user
# cancellation appear stuck while the worker waits inside one model call.
_CLASSIFIER_REQUEST_TIMEOUT_SECONDS = 60.0


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
        "model": configured_model, "version": "audiobook-classifier-v4",
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
