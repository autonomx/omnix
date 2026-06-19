"""Safe item fiction pipeline helpers.

The pipeline prepares display-only generation requests and applies returned
proposal fields through the existing item description boundary. It does not call
an LLM directly; callers can pass the prompt packet to a presentation provider
and feed the result back into ``apply_item_fiction_pipeline_response``.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .item_descriptions import build_item_description_context, compile_item_description
from .item_system import AI_FICTION_ITEM_FIELDS, ENGINE_OWNED_ITEM_FIELDS, normalize_item_instance

ITEM_FICTION_PIPELINE_VERSION = "item_fiction_pipeline_v1"


def build_item_fiction_prompt_packet(item: dict[str, Any], *, genre: str = "classic_fantasy", tone: str = "grounded") -> dict[str, Any]:
    """Build a deterministic prompt packet for display-only item fiction."""

    normalized = normalize_item_instance(item)
    context = build_item_description_context(normalized, genre=genre)
    mechanics = context["mechanics_summary"]
    prompt_lines = [
        "Create display-only item fiction.",
        f"Genre: {genre}",
        f"Tone: {tone}",
        f"Item id: {mechanics['item_id']}",
        f"Item type: {mechanics['item_type']}",
        f"Rarity: {mechanics['rarity']}",
        f"Tags: {', '.join(mechanics.get('tags', [])) or 'none'}",
        "Do not change mechanics, quantities, values, damage, defense, effects, recipes, or requirements.",
        "Return only display fields: name, description, flavor_text, flavor_tags, icon, visual_prompt, maker, culture.",
    ]
    return {
        "version": ITEM_FICTION_PIPELINE_VERSION,
        "source": "engine_item_fiction_prompt",
        "item_id": mechanics["item_id"],
        "genre": genre,
        "tone": tone,
        "allowed_display_fields": sorted(AI_FICTION_ITEM_FIELDS),
        "locked_mechanic_fields": sorted(ENGINE_OWNED_ITEM_FIELDS),
        "context": context,
        "prompt": "\n".join(prompt_lines),
    }


def apply_item_fiction_pipeline_response(
    item: dict[str, Any],
    response: dict[str, Any] | None,
    *,
    genre: str = "classic_fantasy",
    tone: str = "grounded",
) -> dict[str, Any]:
    """Apply a provider response through the display-only description boundary."""

    normalized = normalize_item_instance(item)
    raw_response = response if isinstance(response, dict) else {}
    proposal = _extract_display_proposal(raw_response)
    compiled = compile_item_description(normalized, proposal, genre=genre)
    trace = {
        "event": "item_fiction_pipeline_applied",
        "source": "engine_item_fiction_pipeline_v1",
        "item_id": compiled["trace"]["item_id"],
        "ok": bool(compiled["ok"]),
        "genre": genre,
        "tone": tone,
        "accepted_fields": sorted(proposal),
        "ignored_fields": list(compiled["ignored_fields"]),
        "repairs": list(compiled["repairs"]),
        "mechanics_preserved": bool(compiled["trace"].get("mechanics_preserved")),
    }
    return {
        "ok": bool(compiled["ok"]),
        "item": compiled["item"],
        "proposal": proposal,
        "trace": trace,
        "context": compiled["context"],
        "ignored_fields": list(compiled["ignored_fields"]),
        "repairs": list(compiled["repairs"]),
        "validation": deepcopy(compiled["validation"]),
    }


def _extract_display_proposal(response: dict[str, Any]) -> dict[str, Any]:
    payload = response.get("item") if isinstance(response.get("item"), dict) else response
    proposal: dict[str, Any] = {}
    for field in sorted(AI_FICTION_ITEM_FIELDS):
        if field in payload:
            proposal[field] = deepcopy(payload[field])
    for field in sorted(ENGINE_OWNED_ITEM_FIELDS):
        if field in payload:
            proposal[field] = deepcopy(payload[field])
    return proposal
