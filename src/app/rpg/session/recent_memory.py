from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping


VERSION = "recent_memory_v1"


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def recent_memory(session: Mapping[str, Any] | None) -> dict[str, Any]:
    memory = _dict(_dict(_dict(session).get("runtime_state")).get("recent_memory"))
    return {
        "version": VERSION,
        "turns": _list(memory.get("turns"))[-12:],
        "dialogue": _list(memory.get("dialogue"))[-20:],
    }


def add_recent_memory(session: Mapping[str, Any] | None, **values: str) -> dict[str, Any]:
    updated = deepcopy(_dict(session))
    memory = recent_memory(updated)
    entry = {key: values.get(key, "")[:500] for key in ("player_input", "npc_line")}
    entry["npc_id"] = values.get("npc_id", "")
    memory["turns"] = [*memory["turns"], entry][-12:]
    if entry["npc_id"] or entry["npc_line"]:
        memory["dialogue"] = [*memory["dialogue"], entry][-20:]
    updated["runtime_state"] = {**_dict(updated.get("runtime_state")), "recent_memory": memory}
    return updated