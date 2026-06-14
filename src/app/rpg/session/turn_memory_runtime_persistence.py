from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from app.rpg.session.turn_memory_common import d, s


def extract_call_context(args: tuple[Any, ...], kwargs: dict[str, Any]) -> dict[str, Any]:
    session_id = kwargs.get("session_id") if "session_id" in kwargs else (args[0] if len(args) >= 1 else "")
    player_input = kwargs.get("player_input") if "player_input" in kwargs else (args[1] if len(args) >= 2 else "")
    return {
        "session_id": s(session_id),
        "player_input": s(player_input),
        "session_override": deepcopy(d(kwargs.get("session_override"))),
    }


def load_persisted_session(session_id: str) -> dict[str, Any]:
    if not session_id:
        return {}
    try:
        from app.rpg.session import runtime as canonical_runtime

        return d(canonical_runtime.load_runtime_session(session_id))
    except Exception:
        return {}


def save_persisted_session(session: Mapping[str, Any], *, session_id: str) -> bool:
    if not session_id or not isinstance(session, Mapping):
        return False
    try:
        from app.rpg.session import runtime as canonical_runtime

        session_to_save = deepcopy(d(session))
        manifest = d(session_to_save.get("manifest"))
        manifest.setdefault("session_id", session_id)
        manifest.setdefault("id", session_id)
        session_to_save["manifest"] = manifest
        canonical_runtime.save_runtime_session(session_to_save)
        return True
    except Exception:
        return False


def select_memory_session(result: Mapping[str, Any], context: Mapping[str, Any]) -> tuple[dict[str, Any], bool]:
    session_id = s(context.get("session_id"))
    persisted = load_persisted_session(session_id)
    if persisted:
        return persisted, True
    result_session = d(d(result).get("session"))
    if result_session:
        return result_session, False
    override = d(context.get("session_override"))
    if override:
        return override, False
    return {}, False
