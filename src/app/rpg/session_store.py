"""Compatibility accessors for RPG route modules that expect session_store.

The older API routes imported ``app.rpg.session_store.get_session`` while the
lightweight launcher pipeline currently keeps sessions in ``pipeline._game_store``.
Keep this module intentionally small so importing authoring routes does not fail.
"""

from __future__ import annotations

from typing import Any, Dict


_object_session_cache: Dict[str, Dict[str, Any]] = {}


def _session_id_for(session: Any, fallback: str) -> str:
    return str(getattr(session, "session_id", None) or fallback)


def _simulation_state_for_object(session: Any, session_id: str) -> Dict[str, Any]:
    world = getattr(session, "world", None)
    player = getattr(session, "player", None)
    return {
        "session_id": session_id,
        "world": world,
        "player": player,
        "npcs": list(getattr(session, "npcs", []) or []),
        "story_arcs": list(getattr(session, "story_arcs", []) or []),
        "recent_events": list(getattr(session, "recent_events", []) or []),
        "narrative_state": dict(getattr(session, "narrative_state", {}) or {}),
    }


def get_session(session_id: str) -> Dict[str, Any] | None:
    """Return a route-compatible session dictionary for ``session_id``.

    Dict-backed sessions are returned directly. Object-backed ``GameSession``
    values are wrapped in a stable dictionary containing ``simulation_state`` so
    legacy authoring routes can operate without blocking app startup.
    """
    from app.rpg import pipeline

    session = getattr(pipeline, "_game_store", {}).get(session_id)
    if session is None:
        session = pipeline.load_game(session_id)
    if session is None:
        return None
    if isinstance(session, dict):
        session.setdefault("simulation_state", {})
        return session

    resolved_id = _session_id_for(session, session_id)
    wrapped = _object_session_cache.setdefault(
        resolved_id,
        {
            "session_id": resolved_id,
            "raw_session": session,
            "simulation_state": _simulation_state_for_object(session, resolved_id),
        },
    )
    wrapped["raw_session"] = session
    wrapped.setdefault("simulation_state", _simulation_state_for_object(session, resolved_id))
    return wrapped


def set_session(session_id: str, session: Dict[str, Any]) -> Dict[str, Any]:
    """Store a dict-backed session for compatibility routes."""
    from app.rpg import pipeline

    session.setdefault("simulation_state", {})
    getattr(pipeline, "_game_store", {})[session_id] = session
    return session


__all__ = ["get_session", "set_session"]
