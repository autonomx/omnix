"""Parse and normalize LLM-generated world bootstrap content."""
from __future__ import annotations

import json
import re
import uuid
from typing import Any


# ---------------------------------------------------------------------------
# Bounds constants
# ---------------------------------------------------------------------------

MAX_CHARACTERS = 8
MAX_LOCATIONS = 8
MAX_FACTIONS = 6
MAX_LORE = 12
MAX_RUMORS = 12
MAX_DESCRIPTION_LEN = 300
MAX_NESTED_LIST_LEN = 8


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def _extract_json_from_text(raw_text: str) -> str:
    """Extract JSON content from raw LLM text, stripping markdown fences."""
    text = raw_text.strip()
    # Strip markdown code fences
    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1).strip()
    # If text doesn't start with {, try to find the first { ... } block
    if not text.startswith("{"):
        brace_match = re.search(r"\{.*\}", text, re.DOTALL)
        if brace_match:
            text = brace_match.group(0)
    return text


def _safe_str(val: Any, max_len: int = 0) -> str:
    """Coerce to string, optionally truncate."""
    if val is None:
        return ""
    s = str(val).strip()
    # Collapse whitespace
    s = " ".join(s.split())
    if max_len > 0 and len(s) > max_len:
        s = s[: max_len - 1] + "…"
    return s


def _safe_list(val: Any, max_items: int = 0) -> list:
    """Coerce to list, optionally cap length."""
    if not isinstance(val, list):
        return []
    result = list(val)
    if max_items > 0:
        result = result[:max_items]
    return result


def _safe_bool(val: Any, default: bool = False) -> bool:
    """Coerce to bool."""
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.lower() in ("true", "1", "yes")
    return default


def _ensure_id(entity: dict, prefix: str, id_field: str) -> dict:
    """Assign a deterministic ID if missing."""
    result = dict(entity)
    if not result.get(id_field):
        name = _safe_str(result.get("name", ""))
        if name:
            slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")[:20]
            result[id_field] = f"{prefix}_{slug}"
        else:
            result[id_field] = f"{prefix}_{uuid.uuid4().hex[:8]}"
    return result


def _normalize_name(name: str) -> str:
    """Normalize a name for deduplication: lowercase, strip, collapse spaces."""
    return " ".join(name.lower().strip().split())


def _dedupe_by_name(entities: list[dict]) -> list[dict]:
    """Remove entities with duplicate normalized names, keeping the first."""
    seen: set[str] = set()
    result: list[dict] = []
    for entity in entities:
        norm = _normalize_name(entity.get("name", ""))
        if not norm or norm in seen:
            continue
        seen.add(norm)
        result.append(entity)
    return result


def parse_world_bootstrap_response(raw_text: str) -> dict:
    """Parse LLM raw text response into structured dict.

    - Parse JSON safely
    - Strip invalid fields
    - Bound lengths
    - Normalize strings
    - Ensure IDs
    - Dedupe by normalized names
    - Reject malformed structures (downgrade to warnings, not crashes)
    """
    warnings: list[str] = []

    json_text = _extract_json_from_text(raw_text)
    try:
        payload = json.loads(json_text)
    except (json.JSONDecodeError, TypeError):
        warnings.append("Failed to parse LLM response as JSON")
        return {
            "characters": [],
            "locations": [],
            "factions": [],
            "lore_entries": [],
            "rumors": [],
            "opening_patch": None,
            "warnings": warnings,
        }

    if not isinstance(payload, dict):
        warnings.append("LLM response was not a JSON object")
        return {
            "characters": [],
            "locations": [],
            "factions": [],
            "lore_entries": [],
            "rumors": [],
            "opening_patch": None,
            "warnings": warnings,
        }

    # Parse characters/NPCs
    characters = _parse_characters(payload.get("characters", []), warnings)

    # Parse locations
    locations = _parse_locations(payload.get("locations", []), warnings)

    # Parse factions
    factions = _parse_factions(payload.get("factions", []), warnings)

    # Parse lore entries
    lore_entries = _parse_lore_entries(payload.get("lore_entries", []), warnings)

    # Parse rumors
    rumors = _parse_rumors(payload.get("rumors", []), warnings)

    # Parse opening patch
    opening_patch = _parse_opening_patch(payload.get("opening_patch"), warnings)

    return {
        "characters": characters,
        "locations": locations,
        "factions": factions,
        "lore_entries": lore_entries,
        "rumors": rumors,
        "opening_patch": opening_patch,
        "warnings": warnings,
    }


def _parse_characters(raw: Any, warnings: list[str]) -> list[dict]:
    """Parse and validate character entries."""
    if not isinstance(raw, list):
        return []
    result: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            warnings.append("Skipped non-dict character entry")
            continue
        name = _safe_str(item.get("name"), MAX_DESCRIPTION_LEN)
        if not name:
            warnings.append("Skipped character with no name")
            continue
        char = {
            "npc_id": _safe_str(item.get("npc_id")),
            "name": name,
            "role": _safe_str(item.get("role"), 100) or "unknown",
            "description": _safe_str(item.get("description"), MAX_DESCRIPTION_LEN),
            "goals": [_safe_str(g, 160) for g in _safe_list(item.get("goals"), MAX_NESTED_LIST_LEN) if _safe_str(g)],
            "faction_id": _safe_str(item.get("faction_id")) or None,
            "location_id": _safe_str(item.get("location_id")) or None,
            "must_survive": _safe_bool(item.get("must_survive")),
            "metadata": {},
        }
        char = _ensure_id(char, "npc", "npc_id")
        result.append(char)
    return _dedupe_by_name(result)


def _parse_locations(raw: Any, warnings: list[str]) -> list[dict]:
    """Parse and validate location entries."""
    if not isinstance(raw, list):
        return []
    result: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            warnings.append("Skipped non-dict location entry")
            continue
        name = _safe_str(item.get("name"), MAX_DESCRIPTION_LEN)
        if not name:
            warnings.append("Skipped location with no name")
            continue
        loc = {
            "location_id": _safe_str(item.get("location_id")),
            "name": name,
            "description": _safe_str(item.get("description"), MAX_DESCRIPTION_LEN),
            "tags": [_safe_str(t, 50) for t in _safe_list(item.get("tags"), MAX_NESTED_LIST_LEN) if _safe_str(t)],
            "metadata": {},
        }
        loc = _ensure_id(loc, "loc", "location_id")
        result.append(loc)
    return _dedupe_by_name(result)


def _parse_factions(raw: Any, warnings: list[str]) -> list[dict]:
    """Parse and validate faction entries."""
    if not isinstance(raw, list):
        return []
    result: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            warnings.append("Skipped non-dict faction entry")
            continue
        name = _safe_str(item.get("name"), MAX_DESCRIPTION_LEN)
        if not name:
            warnings.append("Skipped faction with no name")
            continue
        raw_rels = item.get("relationships", {})
        relationships: dict[str, str] = {}
        if isinstance(raw_rels, dict):
            for k, v in raw_rels.items():
                relationships[_safe_str(k)] = _safe_str(v, 50)
        faction = {
            "faction_id": _safe_str(item.get("faction_id")),
            "name": name,
            "description": _safe_str(item.get("description"), MAX_DESCRIPTION_LEN),
            "goals": [_safe_str(g, 160) for g in _safe_list(item.get("goals"), MAX_NESTED_LIST_LEN) if _safe_str(g)],
            "relationships": relationships,
            "metadata": {},
        }
        faction = _ensure_id(faction, "faction", "faction_id")
        result.append(faction)
    return _dedupe_by_name(result)


def _parse_lore_entries(raw: Any, warnings: list[str]) -> list[dict]:
    """Parse and validate lore entries."""
    if not isinstance(raw, list):
        return []
    result: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            warnings.append("Skipped non-dict lore entry")
            continue
        title = _safe_str(item.get("title"), 160)
        content = _safe_str(item.get("content"), MAX_DESCRIPTION_LEN)
        if not title and not content:
            continue
        result.append({
            "title": title or "Untitled Lore",
            "content": content,
            "category": _safe_str(item.get("category"), 50) or "general",
        })
    return _dedupe_by_name(result)


_VALID_RELIABILITY = frozenset({"true", "false", "partial", "unknown"})


def _parse_rumors(raw: Any, warnings: list[str]) -> list[dict]:
    """Parse and validate rumors."""
    if not isinstance(raw, list):
        return []
    result: list[dict] = []
    seen_texts: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            warnings.append("Skipped non-dict rumor entry")
            continue
        text = _safe_str(item.get("text"), MAX_DESCRIPTION_LEN)
        if not text:
            continue
        norm_text = _normalize_name(text)
        if norm_text in seen_texts:
            continue
        seen_texts.add(norm_text)
        reliability = _safe_str(item.get("reliability")).lower()
        if reliability not in _VALID_RELIABILITY:
            reliability = "unknown"
        result.append({
            "text": text,
            "reliability": reliability,
        })
    return result


def _parse_opening_patch(raw: Any, warnings: list[str]) -> dict | None:
    """Parse and validate opening patch."""
    if raw is None or not isinstance(raw, dict):
        return None
    valid_tensions = {"low", "medium", "high"}
    tension = _safe_str(raw.get("tension_level")).lower()
    if tension not in valid_tensions:
        tension = "medium"
    return {
        "scene_frame": _safe_str(raw.get("scene_frame"), MAX_DESCRIPTION_LEN),
        "immediate_problem": _safe_str(raw.get("immediate_problem"), MAX_DESCRIPTION_LEN),
        "tension_level": tension,
        "time_of_day": _safe_str(raw.get("time_of_day"), 50) or "evening",
        "weather": _safe_str(raw.get("weather"), 50) or "clear",
    }


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------


def normalize_generated_world_package(payload: dict) -> dict:
    """Normalize and bound a generated world package.

    - Characters max 8
    - Locations max 8
    - Factions max 6
    - Lore max 12
    - Rumors max 12
    - Assign deterministic IDs if missing
    - Ensure required fields
    - Trim descriptions (max 300 chars)
    - Cap nested lists
    """
    warnings = list(payload.get("warnings", []))

    characters = _safe_list(payload.get("characters"))[:MAX_CHARACTERS]
    locations = _safe_list(payload.get("locations"))[:MAX_LOCATIONS]
    factions = _safe_list(payload.get("factions"))[:MAX_FACTIONS]
    lore_entries = _safe_list(payload.get("lore_entries"))[:MAX_LORE]
    rumors = _safe_list(payload.get("rumors"))[:MAX_RUMORS]
    opening_patch = payload.get("opening_patch")

    # Ensure IDs and required fields on each entity
    characters = [_ensure_character_fields(c) for c in characters if isinstance(c, dict)]
    locations = [_ensure_location_fields(loc) for loc in locations if isinstance(loc, dict)]
    factions = [_ensure_faction_fields(f) for f in factions if isinstance(f, dict)]
    lore_entries = [_ensure_lore_fields(e) for e in lore_entries if isinstance(e, dict)]
    rumors = [_ensure_rumor_fields(r) for r in rumors if isinstance(r, dict)]

    # Deduplicate
    characters = _dedupe_by_name(characters)[:MAX_CHARACTERS]
    locations = _dedupe_by_name(locations)[:MAX_LOCATIONS]
    factions = _dedupe_by_name(factions)[:MAX_FACTIONS]
    lore_entries = _dedupe_by_name(lore_entries)[:MAX_LORE]

    # Validate opening_patch
    if opening_patch is not None and not isinstance(opening_patch, dict):
        opening_patch = None

    return {
        "characters": characters,
        "locations": locations,
        "factions": factions,
        "lore_entries": lore_entries,
        "rumors": rumors,
        "opening_patch": opening_patch,
        "warnings": warnings,
    }


def _ensure_character_fields(char: dict) -> dict:
    """Ensure a character dict has all required fields."""
    result = _ensure_id(dict(char), "npc", "npc_id")
    result["name"] = _safe_str(result.get("name"), MAX_DESCRIPTION_LEN) or "Unnamed NPC"
    result["role"] = _safe_str(result.get("role"), 100) or "unknown"
    result["description"] = _safe_str(result.get("description"), MAX_DESCRIPTION_LEN)
    result["goals"] = [_safe_str(g, 160) for g in _safe_list(result.get("goals"), MAX_NESTED_LIST_LEN) if _safe_str(g)]
    result.setdefault("faction_id", None)
    result.setdefault("location_id", None)
    result["must_survive"] = _safe_bool(result.get("must_survive"))
    result.setdefault("metadata", {})
    return result


def _ensure_location_fields(loc: dict) -> dict:
    """Ensure a location dict has all required fields."""
    result = _ensure_id(dict(loc), "loc", "location_id")
    result["name"] = _safe_str(result.get("name"), MAX_DESCRIPTION_LEN) or "Unnamed Location"
    result["description"] = _safe_str(result.get("description"), MAX_DESCRIPTION_LEN)
    result["tags"] = [_safe_str(t, 50) for t in _safe_list(result.get("tags"), MAX_NESTED_LIST_LEN) if _safe_str(t)]
    result.setdefault("metadata", {})
    return result


def _ensure_faction_fields(faction: dict) -> dict:
    """Ensure a faction dict has all required fields."""
    result = _ensure_id(dict(faction), "faction", "faction_id")
    result["name"] = _safe_str(result.get("name"), MAX_DESCRIPTION_LEN) or "Unnamed Faction"
    result["description"] = _safe_str(result.get("description"), MAX_DESCRIPTION_LEN)
    result["goals"] = [_safe_str(g, 160) for g in _safe_list(result.get("goals"), MAX_NESTED_LIST_LEN) if _safe_str(g)]
    raw_rels = result.get("relationships", {})
    if not isinstance(raw_rels, dict):
        raw_rels = {}
    result["relationships"] = {_safe_str(k): _safe_str(v, 50) for k, v in raw_rels.items()}
    result.setdefault("metadata", {})
    return result


def _ensure_lore_fields(entry: dict) -> dict:
    """Ensure a lore entry dict has all required fields."""
    return {
        "title": _safe_str(entry.get("title"), 160) or "Untitled Lore",
        "content": _safe_str(entry.get("content"), MAX_DESCRIPTION_LEN),
        "category": _safe_str(entry.get("category"), 50) or "general",
        "name": _safe_str(entry.get("title"), 160) or "Untitled Lore",
    }


def _ensure_rumor_fields(rumor: dict) -> dict:
    """Ensure a rumor dict has all required fields."""
    reliability = _safe_str(rumor.get("reliability")).lower()
    if reliability not in _VALID_RELIABILITY:
        reliability = "unknown"
    return {
        "text": _safe_str(rumor.get("text"), MAX_DESCRIPTION_LEN),
        "reliability": reliability,
    }
