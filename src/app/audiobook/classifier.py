"""Bounded local LLM classification over immutable source span IDs."""
from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from app.providers import ChatMessage
from app.shared import get_provider, load_settings


_SYSTEM = (
    "You are the semantic story analyst for an audiobook production system. "
    "Your primary job is to understand the story as a coherent narrative and "
    "identify who actually speaks each marked dialogue passage. Read the entire "
    "story_text before assigning speakers. Use explicit speech tags, pronoun "
    "resolution, scene participation, addressee relationships, conversational "
    "turn-taking, character goals, and later context that clarifies earlier "
    "lines. Do not mechanically alternate speakers and do not treat a nearby "
    "character name as proof that the adjacent quote belongs to that character. "
    "Each self-closing <DIALOGUE .../> marker immediately precedes one immutable dialogue span; target=true "
    "means that span must be returned, while target=false is context only. "
    "When returning spans, copy each requested span_id verbatim from the supplied "
    "span_ids/spans fields; never invent, shorten, truncate, or alter an ID. "
    "For task analyze_story_dialogue_full_context, independently infer the "
    "characters and every requested target speaker from the narrative. "
    "For verification tasks, including verify_story_dialogue_full_context and "
    "verify_story_dialogue_full_context_escalated, treat proposed_assignments as "
    "fallible hypotheses: re-read the complete story_text, actively look for "
    "speaker swaps or discourse errors, and correct them even when the first "
    "pass claimed high confidence. Verification is semantic review, not rubber-"
    "stamping. prior_dialogue_assignments are continuity context, not immutable "
    "truth. "
    "For every full-context story task, return exactly one JSON object with keys "
    "characters and spans. characters is an array of objects with required name "
    "and aliases plus optional role, traits, estimated_age, and gender_presentation. "
    "Only include newly discovered or materially updated characters and keep optional "
    "metadata concise. On verification/repair tasks, return characters as an empty "
    "array unless the correction genuinely discovers or changes an identity. aliases "
    "and traits are arrays of strings; other character metadata values are strings. "
    "Speaker attribution is the critical output. spans must contain exactly "
    "one object for every requested span_id and no context-only dialogue. Each span "
    "object must contain exactly span_id, speaker, confidence, ambiguity. confidence "
    "is a number from 0 to 1 after considering the narrative. ambiguity must be null "
    "whenever you have resolved the speaker to one identity, including when that "
    "resolution required pronouns, aliases, turn-taking, or later context. Do not put "
    "explanations such as 'pronoun-resolved to X' in ambiguity. Use a non-null ambiguity "
    "only when at least two speaker identities remain genuinely plausible or the identity "
    "is genuinely unresolved. Treat pronoun-only attribution, three-or-more-speaker "
    "turns, aliases/nicknames, interrupted dialogue, scene boundaries, and genuinely "
    "plausible alternate speakers as ambiguity worth reporting. Do not return role, "
    "delivery, emotion, tone, source "
    "text, or other metadata in full-context span rows. The source detector already "
    "proves these targets are dialogue. Repair tasks must return only the requested "
    "missing/invalid IDs and must not revise accepted_assignments. "
    "For known speakers, prefer the supplied speaker id or exact canonical name. "
    "Newly discovered people should be listed in characters and may be used by "
    "name as speakers. Use aliases only when the story supports them. "
    "Legacy single-span tasks may return span_id, speaker, role, delivery and "
    "optional confidence. Never return source prose, markdown, explanation, "
    "chain-of-thought, or extra keys."
)

# Classification is a bounded background operation. Without an explicit
# request timeout, a provider's default (often five minutes) can make a user
# cancellation appear stuck while the worker waits inside one model call.
_CLASSIFIER_REQUEST_TIMEOUT_SECONDS = 180.0


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
    extra_params = getattr(provider_config, "extra_params", {}) or {}
    reasoning_effort = str(
        getattr(provider, "reasoning_effort", "")
        or extra_params.get("reasoning_effort")
        or ""
    ).strip()
    details: dict[str, Any] = {
        "mode": "configured_llm_classifier", "provider_id": provider_id,
        "model": configured_model, "version": "audiobook-classifier-v8",
        "reasoning_effort": reasoning_effort or None,
    }
    def classify(context: dict[str, Any]) -> str:
        messages = [ChatMessage(role="system", content=_SYSTEM),
                    ChatMessage(role="user", content=json.dumps(
                        context, ensure_ascii=False, sort_keys=True))]
        request_kwargs: dict[str, Any] = {
            "messages": messages,
            "stream": False,
            "request_timeout_seconds": _CLASSIFIER_REQUEST_TIMEOUT_SECONDS,
        }
        if reasoning_effort:
            request_kwargs["reasoning_effort"] = reasoning_effort
        try:
            response = provider.chat_completion(**request_kwargs)
        except Exception:
            raise
        details["model"] = getattr(response, "model", None) or configured_model
        content = getattr(response, "content", "")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("classifier returned an empty response")
        return content

    return classify, details
