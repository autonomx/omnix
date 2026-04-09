"""LLM-powered world bootstrap generator.

Generates a structured, bounded, reviewable world bootstrap proposal
from the creator inputs and opening context.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)


def _call_app_llm(llm_gateway: Any, prompt: str, setup: dict) -> str:
    """Call LLM using supported gateway interfaces."""
    if llm_gateway is None:
        raise RuntimeError("llm_gateway_missing")

    # Preferred unified gateway
    if hasattr(llm_gateway, "call"):
        resp = llm_gateway.call(prompt, context=setup)
        return resp if isinstance(resp, str) else str(resp or "")

    # Alternative interface
    if hasattr(llm_gateway, "generate_text"):
        resp = llm_gateway.generate_text(prompt, context=setup)
        return resp if isinstance(resp, str) else str(resp or "")

    # Legacy fallback
    if hasattr(llm_gateway, "generate"):
        resp = llm_gateway.generate(prompt, context=setup)
        return resp if isinstance(resp, str) else str(resp or "")

    raise RuntimeError("unsupported_llm_gateway_interface")


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------


def build_world_generation_prompt(setup: dict) -> dict:
    """Build a structured prompt for the LLM world generator.

    The prompt includes genre, setting, premise, player role/archetype/background,
    campaign objective, opening hook, starter conflict, core world laws, genre rules,
    desired content mix, current seed entities, opening context, forbidden content.

    Returns dict with ``system_prompt`` and ``user_prompt`` keys.
    """
    genre = setup.get("genre", "")
    setting = setup.get("setting", "")
    premise = setup.get("premise", "")
    title = setup.get("title", "")

    player_role = setup.get("player_role", "")
    player_archetype = setup.get("player_archetype", "")
    player_background = setup.get("player_background", "")
    campaign_objective = setup.get("campaign_objective", "")
    opening_hook = setup.get("opening_hook", "")
    starter_conflict = setup.get("starter_conflict", "")
    core_world_laws = setup.get("core_world_laws", [])
    genre_rules = setup.get("genre_rules", [])
    desired_content_mix = setup.get("desired_content_mix", {})
    forbidden_content = setup.get("forbidden_content", [])
    opening = setup.get("opening", {})

    existing_npcs = setup.get("npc_seeds", [])
    existing_locations = setup.get("locations", [])
    existing_factions = setup.get("factions", [])

    system_prompt = (
        "You are a creative world-builder for a tabletop RPG adventure.\n"
        "Your task is to generate rich, unique starter content that fits the "
        "creator's vision. Return ONLY valid JSON matching the schema below.\n"
        "Do NOT include markdown fences, commentary, or extra text.\n\n"
        "JSON schema:\n"
        "{\n"
        '  "characters": [{"npc_id": str, "name": str, "role": str, '
        '"description": str, "goals": [str], "faction_id": str|null, '
        '"location_id": str|null, "must_survive": bool}],\n'
        '  "locations": [{"location_id": str, "name": str, '
        '"description": str, "tags": [str]}],\n'
        '  "factions": [{"faction_id": str, "name": str, '
        '"description": str, "goals": [str], "relationships": {str: str}}],\n'
        '  "lore_entries": [{"title": str, "content": str, "category": str}],\n'
        '  "rumors": [{"text": str, "reliability": "true"|"false"|"partial"|"unknown"}],\n'
        '  "opening_patch": {"scene_frame": str, "immediate_problem": str, '
        '"tension_level": "low"|"medium"|"high", '
        '"time_of_day": str, "weather": str} | null\n'
        "}\n\n"
        "Constraints:\n"
        "- Characters: max 8, each with a unique name and clear role\n"
        "- Locations: max 8, each with descriptive tags\n"
        "- Factions: max 6, each with goals and inter-faction relationships\n"
        "- Lore entries: max 12, short (max 300 chars each)\n"
        "- Rumors: max 12, mix of true/false/partial/unknown\n"
        "- All descriptions max 300 characters\n"
        "- Content must respect forbidden themes\n"
        "- Entity IDs should use snake_case prefixes: npc_, loc_, faction_\n"
    )

    # Build the user prompt with all context
    user_parts: list[str] = []
    user_parts.append(f"Title: {title}")
    user_parts.append(f"Genre: {genre}")
    user_parts.append(f"Setting: {setting}")
    user_parts.append(f"Premise: {premise}")

    if player_role:
        user_parts.append(f"Player Role: {player_role}")
    if player_archetype:
        user_parts.append(f"Player Archetype: {player_archetype}")
    if player_background:
        user_parts.append(f"Player Background: {player_background}")
    if campaign_objective:
        user_parts.append(f"Campaign Objective: {campaign_objective}")
    if opening_hook:
        user_parts.append(f"Opening Hook: {opening_hook}")
    if starter_conflict:
        user_parts.append(f"Starter Conflict: {starter_conflict}")
    if core_world_laws:
        user_parts.append(f"Core World Laws: {'; '.join(core_world_laws)}")
    if genre_rules:
        user_parts.append(f"Genre Rules: {'; '.join(genre_rules)}")
    if desired_content_mix:
        mix_str = ", ".join(f"{k}: {v:.0%}" for k, v in desired_content_mix.items())
        user_parts.append(f"Desired Content Mix: {mix_str}")
    if forbidden_content:
        user_parts.append(f"Forbidden Content: {', '.join(forbidden_content)}")

    # Include existing seed entities for context
    if existing_npcs:
        names = [n.get("name", n.get("npc_id", "?")) for n in existing_npcs[:8]]
        user_parts.append(f"Existing NPCs (do not duplicate): {', '.join(names)}")
    if existing_locations:
        names = [loc.get("name", loc.get("location_id", "?")) for loc in existing_locations[:8]]
        user_parts.append(f"Existing Locations (do not duplicate): {', '.join(names)}")
    if existing_factions:
        names = [f.get("name", f.get("faction_id", "?")) for f in existing_factions[:6]]
        user_parts.append(f"Existing Factions (do not duplicate): {', '.join(names)}")

    if opening:
        opening_parts = []
        for k in ("scene_frame", "immediate_problem", "tension_level"):
            val = opening.get(k, "")
            if val:
                opening_parts.append(f"{k}: {val}")
        if opening_parts:
            user_parts.append(f"Opening Context: {'; '.join(opening_parts)}")

    user_parts.append(
        "\nGenerate a complete world bootstrap package as JSON. "
        "Make each character, location, and faction unique and interconnected. "
        "Ensure generated content supports the opening hook and campaign objective."
    )

    user_prompt = "\n".join(user_parts)

    return {
        "system_prompt": system_prompt,
        "user_prompt": user_prompt,
    }


# ---------------------------------------------------------------------------
# Main generation entry point
# ---------------------------------------------------------------------------


def generate_world_bootstrap_proposal(
    setup: dict,
    preferences: Optional[dict] = None,
    llm_gateway: Any = None,
) -> dict:
    """Generate a rich, unique starting package from builder inputs.

    If *llm_gateway* is provided and working, uses LLM.
    Otherwise falls back to deterministic fallback.

    Returns::

        {
            "status": "ready" | "error",
            "characters": [...],
            "locations": [...],
            "factions": [...],
            "lore_entries": [...],
            "rumors": [...],
            "opening_patch": {...} | null,
            "generation_notes": str,
            "warnings": [...],
            "provenance": {
                "used_llm": bool,
                "model": str,
                "generated_at": str,
            },
        }
    """
    from .llm_world_parser import normalize_generated_world_package, parse_world_bootstrap_response

    prefs = dict(preferences or {})
    generated_at = datetime.now(timezone.utc).isoformat()

    # Attempt LLM generation
    if llm_gateway is not None:
        try:
            prompts = build_world_generation_prompt(setup)

            # Build the full prompt for the gateway
            full_prompt = (
                f"{prompts['system_prompt']}\n\n"
                f"---\n\n"
                f"{prompts['user_prompt']}"
            )

            raw_response = _call_app_llm(llm_gateway, full_prompt, setup)

            if raw_response and raw_response.strip():
                parsed = parse_world_bootstrap_response(raw_response)
                normalized = normalize_generated_world_package(parsed)

                return {
                    "status": "ready",
                    **normalized,
                    "generation_notes": "Generated via LLM",
                    "warnings": normalized.get("warnings", []),
                    "provenance": {
                        "used_llm": True,
                        "model": _get_model_name(llm_gateway),
                        "generated_at": generated_at,
                    },
                }
        except Exception:
            logger.warning(
                "LLM world generation failed, falling back to deterministic",
                exc_info=True,
            )

    # Deterministic fallback
    result = fallback_world_bootstrap_proposal(setup, preferences=prefs)
    warnings = list(result.get("warnings", []))
    warnings.append("LLM generation unavailable or failed; fallback used")
    result["warnings"] = warnings
    result["provenance"] = {
        "used_llm": False,
        "model": "deterministic_fallback",
        "generated_at": generated_at,
    }
    return result


def _get_model_name(llm_gateway: Any) -> str:
    """Extract model name from gateway, with safe fallback."""
    try:
        if hasattr(llm_gateway, "provider"):
            provider = llm_gateway.provider
            if hasattr(provider, "model_name"):
                return str(provider.model_name)
            if hasattr(provider, "model"):
                return str(provider.model)
        return "unknown"
    except Exception:
        return "unknown"


# ---------------------------------------------------------------------------
# Deterministic fallback generator
# ---------------------------------------------------------------------------

# Genre-keyed fallback content tables
_FALLBACK_LORE: dict[str, list[dict]] = {
    "fantasy": [
        {"title": "The Age of Sundering", "content": "Long ago, the world was split by a cataclysm of wild magic. The scars still mark the land.", "category": "history"},
        {"title": "The Old Pact", "content": "An ancient agreement binds certain creatures to serve those who know the right words.", "category": "magic"},
        {"title": "The Fading Stars", "content": "Each year, fewer stars appear in the sky. The wise say this portends something terrible.", "category": "prophecy"},
    ],
    "cyberpunk": [
        {"title": "The Blackout of '47", "content": "A city-wide EMP wiped every digital record. Nobody knows who did it — or what was erased.", "category": "history"},
        {"title": "The Ghost Protocol", "content": "A legendary hack that supposedly lets you erase your identity from every database.", "category": "technology"},
        {"title": "The Corporate Accords", "content": "The megacorps agreed to divide the city into zones. The agreement is fraying.", "category": "politics"},
    ],
    "mystery": [
        {"title": "The Unsolved Case", "content": "Ten years ago, a prominent citizen vanished. The case was closed, but questions remain.", "category": "history"},
        {"title": "The Whispering Gallery", "content": "A secret room where the city's elite supposedly meet to make deals no one should know about.", "category": "location"},
        {"title": "The Red Ledger", "content": "A missing accounting book that could expose corruption at the highest levels.", "category": "artifact"},
    ],
    "political": [
        {"title": "The Succession Crisis", "content": "The old ruler died without a clear heir. Three claimants vie for the throne.", "category": "history"},
        {"title": "The Treaty of Thorns", "content": "A fragile peace agreement that benefits some and oppresses others.", "category": "politics"},
        {"title": "The Hidden Court", "content": "A shadow council that truly controls policy from behind the scenes.", "category": "politics"},
    ],
    "grimdark": [
        {"title": "The Long Winter", "content": "Five years of ash-choked skies have killed most crops. Starvation is everywhere.", "category": "history"},
        {"title": "The Plague Carriers", "content": "Certain wanderers spread a wasting sickness. Some say it was engineered.", "category": "threat"},
        {"title": "The Old Bunkers", "content": "Pre-catastrophe shelters dot the wasteland. Most are picked clean, but rumors persist.", "category": "location"},
    ],
}

_FALLBACK_RUMORS: dict[str, list[dict]] = {
    "fantasy": [
        {"text": "A dragon has been seen near the northern mountains.", "reliability": "partial"},
        {"text": "The old wizard in the tower has gone mad.", "reliability": "unknown"},
        {"text": "A merchant is selling enchanted goods at suspiciously low prices.", "reliability": "true"},
        {"text": "The king's advisor is secretly a changeling.", "reliability": "false"},
    ],
    "cyberpunk": [
        {"text": "SynTech is testing illegal bioware on homeless citizens.", "reliability": "partial"},
        {"text": "There's a back door into the city's security grid.", "reliability": "unknown"},
        {"text": "A rogue AI is hiding in the undercity network.", "reliability": "true"},
        {"text": "The mayor is a corporate puppet.", "reliability": "partial"},
    ],
    "mystery": [
        {"text": "The victim had a secret meeting the night before.", "reliability": "true"},
        {"text": "The butler did it.", "reliability": "false"},
        {"text": "There's a hidden passage in the old mansion.", "reliability": "unknown"},
        {"text": "The police are covering something up.", "reliability": "partial"},
    ],
    "political": [
        {"text": "The chancellor is negotiating a secret alliance.", "reliability": "true"},
        {"text": "A noble house is stockpiling weapons.", "reliability": "partial"},
        {"text": "The treasury is nearly empty.", "reliability": "unknown"},
        {"text": "Foreign spies have infiltrated the court.", "reliability": "partial"},
    ],
    "grimdark": [
        {"text": "A cache of pre-war medicine was found in the ruins.", "reliability": "unknown"},
        {"text": "The warlord's forces are moving south.", "reliability": "true"},
        {"text": "Clean water can be found beneath the old factory.", "reliability": "partial"},
        {"text": "A safe haven exists beyond the mountains.", "reliability": "false"},
    ],
}


def _match_genre_key(genre: str) -> str:
    """Map genre string to a fallback content key."""
    g = (genre or "").lower()
    for key in ("fantasy", "cyberpunk", "mystery", "political", "grimdark"):
        if key in g:
            return key
    # Handle aliases
    if "noir" in g:
        return "mystery"
    if "intrigue" in g:
        return "political"
    if "survival" in g:
        return "grimdark"
    return "fantasy"


def fallback_world_bootstrap_proposal(
    setup: dict, preferences: Optional[dict] = None
) -> dict:
    """Deterministic non-LLM fallback bootstrap generator.

    Generates a few starter NPCs, locations, at least one faction,
    opening patch, and lore snippets based on genre and setup.
    """
    from .defaults import (
        _generate_default_factions,
        _generate_default_locations,
        _generate_default_npcs,
        infer_default_starter_conflict,
        infer_opening_scene_frame,
    )

    genre = setup.get("genre", "")
    setting = setup.get("setting", "")
    genre_key = _match_genre_key(genre)

    # Generate characters (NPCs)
    existing_npc_ids = {n.get("npc_id") for n in setup.get("npc_seeds", [])}
    locations = setup.get("locations", []) or _generate_default_locations(genre, setting)
    fallback_npcs = _generate_default_npcs(genre, setting, locations)
    characters = [n for n in fallback_npcs if n.get("npc_id") not in existing_npc_ids][:8]

    # Generate locations
    existing_loc_ids = {loc.get("location_id") for loc in setup.get("locations", [])}
    fallback_locs = _generate_default_locations(genre, setting)
    gen_locations = [loc for loc in fallback_locs if loc.get("location_id") not in existing_loc_ids][:8]

    # Generate factions
    existing_faction_ids = {f.get("faction_id") for f in setup.get("factions", [])}
    fallback_factions = _generate_default_factions(genre, setting)
    gen_factions = [f for f in fallback_factions if f.get("faction_id") not in existing_faction_ids][:6]

    # Lore entries
    lore_entries = list(_FALLBACK_LORE.get(genre_key, _FALLBACK_LORE["fantasy"]))

    # Rumors
    rumors = list(_FALLBACK_RUMORS.get(genre_key, _FALLBACK_RUMORS["fantasy"]))

    # Opening patch — fill missing opening fields
    opening = setup.get("opening", {})
    opening_patch: dict[str, Any] | None = None
    if not opening.get("scene_frame") or not opening.get("immediate_problem"):
        opening_patch = {
            "scene_frame": opening.get("scene_frame") or infer_opening_scene_frame(setup),
            "immediate_problem": opening.get("immediate_problem") or infer_default_starter_conflict(setup),
            "tension_level": opening.get("tension_level", "medium"),
            "time_of_day": opening.get("time_of_day", "evening"),
            "weather": opening.get("weather", "clear"),
        }

    return {
        "status": "ready",
        "characters": characters,
        "locations": gen_locations,
        "factions": gen_factions,
        "lore_entries": lore_entries,
        "rumors": rumors,
        "opening_patch": opening_patch,
        "generation_notes": f"Deterministic fallback content for {genre_key} genre",
        "warnings": [],
    }
