"""Frontend payload adapter for canonical RPG sessions.

The creator/start flow now persists a canonical session immediately.
The frontend still expects a stable bootstrap payload:
``session_id``, ``opening``, ``world``, ``player``, ``npcs``, ``memory``,
``worldEvents``.
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Response version constants — bump when the contract changes
# ---------------------------------------------------------------------------

ADVENTURE_START_RESPONSE_VERSION = 1


# ---------------------------------------------------------------------------
# Safety helpers — guard against malformed/partial internal output
# ---------------------------------------------------------------------------


def _safe_list(value: Any) -> list[Any]:
    """Return *value* if it is already a list, otherwise ``[]``."""
    if isinstance(value, list):
        return value
    return []


def _safe_dict(value: Any) -> dict[str, Any]:
    """Return *value* if it is already a dict, otherwise ``{}``."""
    if isinstance(value, dict):
        return value
    return {}


def adapt_session_to_frontend(session: dict[str, Any]) -> dict[str, Any]:
    """Convert canonical persisted session to frontend shape.

    Parameters
    ----------
    session:
        The dict returned by the canonical session store.
        Expected keys: ``manifest``, ``runtime_state``, ``simulation_state``.

    Returns
    -------
    dict
        Frontend-friendly payload derived from canonical persisted session state.
    """
    session = _safe_dict(session)
    manifest = _safe_dict(session.get("manifest"))
    runtime_state = _safe_dict(session.get("runtime_state"))
    simulation_state = _safe_dict(session.get("simulation_state"))

    response = {
        "response_version": ADVENTURE_START_RESPONSE_VERSION,
        "success": True,
        "session_id": _safe_dict(session.get("manifest")).get("id"),
        "title": _safe_dict(session.get("manifest")).get("title"),
        "opening": runtime_state.get("opening") or "",
        "world": _safe_dict(runtime_state.get("world")),
        "player": _safe_dict(simulation_state.get("player_state")),
        "npcs": _safe_list(runtime_state.get("npcs")),
        "memory": _safe_list(_safe_dict(simulation_state.get("memory_state")).get("short_term")),
        "worldEvents": _safe_list(simulation_state.get("events"))[-8:],
        "world_events": _safe_list(simulation_state.get("events"))[-8:],
        "scene": _safe_dict(runtime_state.get("current_scene")),
        "voice_assignments": _safe_dict(runtime_state.get("voice_assignments")),
        "creator": {"setup_id": manifest.get("id")},
    }
    return response