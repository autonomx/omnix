from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

RECENT_MEMORY_VERSION = "recent_memory_v1"


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def recent_memory(session: Mapping[str, Any] | None) -> dict[str, Any]:
    runtime = _dict(_dict(session).get("runtime_state"))
    memory = _dict(runtime.get("recent_memory"))
    return {
        "version": RECENT_MEMORY_VERSION,
        "turns": _list(memory.get("turns"))[-12:],
        "dialogue": _list(memory.get("dialogue"))[-20:],
    }


def add_recent_memory(
    session: Mapping[str, Any] | None,
    *,
    player_input: str,
    npc_id: str = "",
    npc_line: str = "",
) -> dict[str, Any]:
    updated = deepcopy(_dict(session))
    runtime = _dict(updated.get("runtime_state"))
    memory = recent_memory(updated)
    entry = {"player_input": player_input[:500], "npc_id": npc_id, "npc_line": npc_line[:500]}
    memory["turns"] = [*memory["turns"], entry][-12:]
    if npc_id or npc_line:
        memory["dialogue"] = [*memory["dialogue"], entry][-20:]
    runtime["recent_memory"] = memory
    updated["runtime_state"] = runtime
    return updated
