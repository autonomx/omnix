from __future__ import annotations

from typing import Any, Mapping

VERSION = "recent_memory_v1"


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def recent_memory(session: Mapping[str, Any] | None) -> dict[str, Any]:
    runtime = _dict(_dict(session).get("runtime_state"))
    memory = _dict(runtime.get("recent_memory"))
    turns = _list(memory.get("turns"))[-12:]
    dialogue = _list(memory.get("dialogue"))[-20:]
    return {"version": VERSION, "turns": turns, "dialogue": dialogue}


from app.rpg.session.recent_memory_write import add_recent_memory
__all__ = ["add_recent_memory", "recent_memory"]
