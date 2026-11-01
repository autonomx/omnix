"""Read-only RPG inventory item details with persisted presentation-only LLM prose."""
from __future__ import annotations

from typing import Any

from app.persistence.database import default_database
from app.security.tenant_context import current_tenant
from app.apps.rpg.foundation.safe_values import safe_dict as _safe_dict, safe_list as _safe_list


GENERIC_GENRES = {"", "deterministic_rpg_campaign", "rpg_campaign", "default"}


def _text(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text or fallback


def _session_genre(state: dict[str, Any], requested_genre: str | None) -> str:
    metadata = _safe_dict(state.get("metadata"))
    identity = _safe_dict(state.get("character_identity"))
    raw_genre = _text(
        requested_genre
        or metadata.get("genre")
        or identity.get("genre")
        or metadata.get("campaign_template"),
        "setting_defined_rpg",
    )
    if raw_genre.casefold() not in GENERIC_GENRES:
        return raw_genre

    clues = " ".join(
        [
            _text(state.get("location") or state.get("current_location")),
            _text(metadata.get("origin")),
            " ".join(_text(item) for item in _safe_list(metadata.get("starter_gear"))),
        ]
    ).casefold()
    if any(token in clues for token in ("tavern", "cloak", "dagger", "silver", "village", "torch")):
        return "classic_fantasy"
    if any(token in clues for token in ("starship", "space", "laser", "cyber", "station")):
        return "science_fiction"
    if any(token in clues for token in ("noir", "detective", "city", "firearm")):
        return "modern_mystery"
    return "setting_defined_rpg"


def _setting_context(state: dict[str, Any], genre: str) -> dict[str, Any]:
    metadata = _safe_dict(state.get("metadata"))
    identity = _safe_dict(state.get("character_identity"))
    world = _safe_dict(state.get("world"))
    environment = _safe_dict(world.get("environment"))
    genesis = _safe_dict(state.get("genesis_snapshot"))
    story_options = _safe_dict(genesis.get("story_options"))
    return {
        "genre": genre,
        "campaign_template": _text(metadata.get("campaign_template")),
        "tone": _text(metadata.get("tone") or identity.get("tone")),
        "location": _text(state.get("location") or state.get("current_location")),
        "origin": _text(metadata.get("origin") or identity.get("origin")),
        "character_background": _text(identity.get("background")),
        "power_source": _text(identity.get("power_source") or metadata.get("power_source")),
        "opening_hook": _text(metadata.get("opening_hook") or story_options.get("opening_hook")),
        "climate_profile": _text(environment.get("climate_profile_id")),
        "starter_gear": [_text(item) for item in _safe_list(metadata.get("starter_gear"))[:8] if _text(item)],
    }


def _description_database_context() -> tuple[Any, Any]:
    database = default_database()
    context = current_tenant()
    return database, context
