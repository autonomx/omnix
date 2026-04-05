"""Phase 4 — Scene / Encounter Generator

Transforms simulation incidents + threads + hotspots into playable
scenes, encounters, and narrative hooks that are player-facing.

Scene types supported:
    - conflict: Crisis escalation and high-tension confrontations
    - encounter: Flashpoint events at volatile locations
    - political: Faction instability and power shifts
    - investigation: Mystery threads requiring exploration
    - negotiation: Diplomatic challenges between factions
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Scene type constants
# ---------------------------------------------------------------------------

SCENE_TYPE_CONFLICT = "conflict"
SCENE_TYPE_ENCOUNTER = "encounter"
SCENE_TYPE_POLITICAL = "political"
SCENE_TYPE_INVESTIGATION = "investigation"
SCENE_TYPE_NEGOTIATION = "negotiation"

VALID_SCENE_TYPES = frozenset({
    SCENE_TYPE_CONFLICT,
    SCENE_TYPE_ENCOUNTER,
    SCENE_TYPE_POLITICAL,
    SCENE_TYPE_INVESTIGATION,
    SCENE_TYPE_NEGOTIATION,
})

# Maximum number of scenes returned to avoid overwhelming the UI
_MAX_SCENES = 20

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _safe_list(v: Any) -> list[Any]:
    """Return *v* if it is already a list, otherwise ``[]``."""
    return v if isinstance(v, list) else []


def _safe_str(v: Any, default: str = "") -> str:
    """Return *v* as a string, falling back to *default*."""
    if v is None:
        return default
    return str(v)


def _build_scene_id(source_id: str, suffix: str) -> str:
    """Build a stable scene id from source and suffix.

    Parameters
    ----------
    source_id :
        The originating entity id (location, faction, thread, etc.)
    suffix :
        A short descriptor like ``"crisis"``, ``"flashpoint"``, etc.

    Returns
    -------
    str
        A scene id like ``"scene_thread_alpha_crisis"``.
    """
    return f"scene_{source_id}_{suffix}"


# ---------------------------------------------------------------------------
# Incident → Scene mappers
# ---------------------------------------------------------------------------


def _map_thread_crisis(inc: dict[str, Any]) -> dict[str, Any]:
    """Map a thread crisis incident to a playable conflict scene."""
    source = _safe_str(inc.get("source_id"), "unknown")
    summary = _safe_str(inc.get("summary"), "A crisis has escalated beyond containment.")
    pressure = inc.get("pressure", 0)

    stakes_parts = []
    if isinstance(pressure, (int, float)):
        if pressure >= 5:
            stakes_parts.append("Critical escalation imminent")
        elif pressure >= 3:
            stakes_parts.append("High tension conflict")
        else:
            stakes_parts.append("Moderate conflict")
    else:
        stakes_parts.append("High tension conflict")

    return {
        "scene_id": _build_scene_id(source, "crisis"),
        "type": SCENE_TYPE_CONFLICT,
        "title": f"Crisis Escalation: {source}",
        "summary": summary,
        "actors": [source],
        "stakes": ", ".join(stakes_parts),
        "severity": inc.get("severity", "neutral"),
        "source_incident_id": inc.get("incident_id") or inc.get("id"),
    }


def _map_location_flashpoint(inc: dict[str, Any]) -> dict[str, Any]:
    """Map a location flashpoint incident to an encounter scene."""
    source = _safe_str(inc.get("source_id"), "unknown")
    summary = _safe_str(inc.get("summary"), "A volatile situation threatens this location.")
    heat = inc.get("heat", 0)

    stakes_parts = []
    if isinstance(heat, (int, float)):
        if heat >= 5:
            stakes_parts.append("Environment at boiling point")
        elif heat >= 3:
            stakes_parts.append("Volatile environment")
        else:
            stakes_parts.append("Rising tensions")
    else:
        stakes_parts.append("Volatile environment")

    return {
        "scene_id": _build_scene_id(source, "flashpoint"),
        "type": SCENE_TYPE_ENCOUNTER,
        "title": f"Flashpoint at {source}",
        "summary": summary,
        "actors": [source],
        "stakes": ", ".join(stakes_parts),
        "severity": inc.get("severity", "neutral"),
        "source_incident_id": inc.get("incident_id") or inc.get("id"),
    }


def _map_faction_instability(inc: dict[str, Any]) -> dict[str, Any]:
    """Map a faction instability incident to a political scene."""
    source = _safe_str(inc.get("source_id"), "unknown")
    summary = _safe_str(inc.get("summary"), "Power dynamics within the faction are shifting.")
    pressure = inc.get("pressure", 0)

    stakes_parts = []
    if isinstance(pressure, (int, float)):
        if pressure >= 5:
            stakes_parts.append("Imminent power shift")
        elif pressure >= 3:
            stakes_parts.append("Power shift")
        else:
            stakes_parts.append("Factional tension")
    else:
        stakes_parts.append("Power shift")

    return {
        "scene_id": _build_scene_id(source, "instability"),
        "type": SCENE_TYPE_POLITICAL,
        "title": f"Faction Instability: {source}",
        "summary": summary,
        "actors": [source],
        "stakes": ", ".join(stakes_parts),
        "severity": inc.get("severity", "neutral"),
        "source_incident_id": inc.get("incident_id") or inc.get("id"),
    }


def _map_thread_investigation(inc: dict[str, Any]) -> dict[str, Any]:
    """Map a mysterious thread to an investigation scene."""
    source = _safe_str(inc.get("source_id"), "unknown")
    summary = _safe_str(inc.get("summary"), "Unexplained events warrant investigation.")

    return {
        "scene_id": _build_scene_id(source, "investigation"),
        "type": SCENE_TYPE_INVESTIGATION,
        "title": f"Unexplained Events: {source}",
        "summary": summary,
        "actors": [source],
        "stakes": "Hidden truths await discovery",
        "severity": inc.get("severity", "neutral"),
        "source_incident_id": inc.get("incident_id") or inc.get("id"),
    }


def _map_thread_negotiation(inc: dict[str, Any]) -> dict[str, Any]:
    """Map a diplomatic thread to a negotiation scene."""
    source = _safe_str(inc.get("source_id"), "unknown")
    summary = _safe_str(inc.get("summary"), "Diplomatic skills are needed to resolve tensions.")

    return {
        "scene_id": _build_scene_id(source, "negotiation"),
        "type": SCENE_TYPE_NEGOTIATION,
        "title": f"Diplomatic Challenge: {source}",
        "summary": summary,
        "actors": [source],
        "stakes": "Peace hangs in the balance",
        "severity": inc.get("severity", "neutral"),
        "source_incident_id": inc.get("incident_id") or inc.get("id"),
    }


# ---------------------------------------------------------------------------
# Incident type → mapper dispatch
# ---------------------------------------------------------------------------

_INCIDENT_MAPPERS: dict[str, Any] = {
    "thread_crisis": _map_thread_crisis,
    "location_flashpoint": _map_location_flashpoint,
    "faction_instability": _map_faction_instability,
    "thread_mystery": _map_thread_investigation,
    "thread_diplomatic": _map_thread_negotiation,
}

# Fallback mapping for partial matches
_INCIDENT_TYPE_KEYWORDS: dict[str, str] = {
    "crisis": _map_thread_crisis,
    "flashpoint": _map_location_flashpoint,
    "instability": _map_faction_instability,
    "mystery": _map_thread_investigation,
    "negotiation": _map_thread_negotiation,
    "diplomatic": _map_thread_negotiation,
    "investigation": _map_thread_investigation,
}


def _resolve_mapper(inc_type: str) -> Any:
    """Resolve the appropriate mapper for an incident type.

    Falls back to keyword matching if exact type not found.
    """
    if inc_type in _INCIDENT_MAPPERS:
        return _INCIDENT_MAPPERS[inc_type]

    lower = inc_type.lower()
    for keyword, mapper in _INCIDENT_TYPE_KEYWORDS.items():
        if keyword in lower:
            return mapper

    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _thread_to_scene(thread: dict[str, Any]) -> dict[str, Any]:
    """Generate a scene from a high-pressure thread."""
    tid = _safe_str(thread.get("id"), "unknown_thread")
    pressure = thread.get("pressure", 0)
    return {
        "scene_id": _build_scene_id(tid, "pressure"),
        "type": SCENE_TYPE_CONFLICT,
        "title": f"Rising Tension: {tid}",
        "summary": f"Pressure at {pressure}. {thread.get('summary', '')}",
        "actors": [tid],
        "stakes": "Escalation likely",
        "severity": "moderate" if pressure >= 5 else "low",
        "source_incident_id": None,
    }


def _location_to_scene(location: dict[str, Any]) -> dict[str, Any]:
    """Generate a scene from a hotspot location."""
    lid = _safe_str(location.get("location_id"), "unknown_loc")
    heat = location.get("heat", 0)
    return {
        "scene_id": _build_scene_id(lid, "hotspot"),
        "type": SCENE_TYPE_ENCOUNTER,
        "title": f"Hotspot: {location.get('name', lid)}",
        "summary": f"Heat level {heat}. {location.get('description', '')}",
        "actors": [lid],
        "stakes": "Volatile environment",
        "severity": "moderate" if heat >= 5 else "low",
        "source_incident_id": None,
    }


def generate_scenes_from_incidents(
    incidents: list[dict[str, Any]],
    *,
    max_scenes: int = _MAX_SCENES,
) -> list[dict[str, Any]]:
    """Transform a list of simulation incidents into playable scenes.

    Parameters
    ----------
    incidents :
        List of incident dicts from the world simulation engine.
        Each incident should have at minimum a ``type`` and
        ``source_id`` key.
    max_scenes :
        Maximum number of scenes to return. Defaults to ``20``.

    Returns
    -------
    list[dict[str, Any]]
        A list of scene dicts ready for frontend display.  Each scene
        has keys: ``scene_id``, ``type``, ``title``, ``summary``,
        ``actors``, ``stakes``, ``severity``, and
        ``source_incident_id``.
    """
    scenes: list[dict[str, Any]] = []

    for inc in _safe_list(incidents):
        inc_type = _safe_str(inc.get("type"))
        mapper = _resolve_mapper(inc_type)

        if mapper is not None:
            try:
                scene = mapper(inc)
                scenes.append(scene)
            except Exception:
                # Skip incidents that fail to map — they will be logged
                # by the caller if needed.
                continue

    return scenes[:max_scenes]


def generate_extra_scenes(
    state: dict[str, Any],
    *,
    max_scenes: int = _MAX_SCENES,
    already: int = 0,
) -> list[dict[str, Any]]:
    """Generate scenes from non-incident sources (threads, hotspots, factions).

    Only kicks in when incident-based scenes are insufficient to fill
    the cap.

    Parameters
    ----------
    state :
        Simulation after-state dict (may contain ``threads``, ``hotspots``,
        ``factions``).
    max_scenes :
        Overall maximum scenes allowed.
    already :
        Number of scenes already generated from incidents.

    Returns
    -------
    list[dict[str, Any]]
        Additional scene dicts.
    """
    extra: list[dict[str, Any]] = []
    remaining = max_scenes - already
    if remaining <= 0:
        return extra

    # From threads with pressure >= 3
    threads = _safe_list(state.get("threads"))
    for t in threads:
        if len(extra) >= remaining:
            break
        if t.get("pressure", 0) >= 3:
            extra.append(_thread_to_scene(t))

    # From hotspots
    if len(extra) < remaining:
        hotspots = _safe_list(state.get("hotspots"))
        for h in hotspots:
            if len(extra) >= remaining:
                break
            extra.append(_location_to_scene(h))

    return extra


def generate_scenes_from_simulation(
    state: dict[str, Any],
    *,
    max_scenes: int = _MAX_SCENES,
) -> list[dict[str, Any]]:
    """High-level entry point: extract incidents from simulation state
    and generate playable scenes.

    Parameters
    ----------
    state :
        The simulation after-state dict returned by
        ``step_simulation_state()``.  Expected to contain the
        incidents list under keys like ``incidents``, or
        ``simulation_state.incidents``.  May also contain threads,
        hotspots, factions as secondary scene sources.
    max_scenes :
        Maximum number of scenes to return.

    Returns
    -------
    list[dict[str, Any]]
        Generated scenes.
    """
    # Try top-level incidents first
    incidents = _safe_list(state.get("incidents"))

    # Fall back to nested simulation_state
    if not incidents:
        sim_state = state.get("simulation_state")
        if isinstance(sim_state, dict):
            incidents = _safe_list(sim_state.get("incidents"))

    scenes = generate_scenes_from_incidents(incidents, max_scenes=max_scenes)

    # Also pull from non-incident sources (threads, hotspots)
    extra = generate_extra_scenes(state, max_scenes=max_scenes, already=len(scenes))
    scenes.extend(extra)

    return scenes[:max_scenes]


def get_scene_type_info(scene_type: str) -> dict[str, str]:
    """Return human-readable metadata for a scene type."""
    info = {
        SCENE_TYPE_CONFLICT: {
            "label": "Conflict",
            "icon": "\u2694\uFE0F",
            "description": "High-tension confrontations requiring combat or diplomacy.",
        },
        SCENE_TYPE_ENCOUNTER: {
            "label": "Encounter",
            "icon": "\uD83D\uDD25",
            "description": "Volatile environmental events and chance meetings.",
        },
        SCENE_TYPE_POLITICAL: {
            "label": "Political",
            "icon": "\uD83D\uDC51",
            "description": "Faction intrigue and power struggles.",
        },
        SCENE_TYPE_INVESTIGATION: {
            "label": "Investigation",
            "icon": "\uD83D\uDD0D",
            "description": "Mysteries and unexplained events to uncover.",
        },
        SCENE_TYPE_NEGOTIATION: {
            "label": "Negotiation",
            "icon": "\uD83E\uDD1D",
            "description": "Diplomatic challenges requiring persuasion.",
        },
    }
    return info.get(scene_type, {
        "label": scene_type,
        "icon": "\uD83C\uDFAD",
        "description": f"Custom scene type: {scene_type}",
    })