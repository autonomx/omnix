from __future__ import annotations

from typing import Any, Mapping

from app.rpg.session.recent_memory import _dict, recent_memory


def add_recent_memory(
    session: Mapping[str, Any] | None,
    **values: str,
) -> dict[str, Any]:
    updated = _dict(session)
    memory = recent_memory(updated)
    entry = {
        "player_input": values.get("player_input", "")[:500],
        "npc_id": values.get("npc_id", ""),
        "npc_line": values.get("npc_line", "")[:500],
    }
    memory["turns"] = [*memory["turns"], entry][-12:]
    if entry["npc_id"] or entry["npc_line"]:
        memory["dialogue"] = [*memory["dialogue"], entry][-20:]
    runtime = _dict(updated.get("runtime_state"))
    runtime["recent_memory"] = memory
    updated["runtime_state"] = runtime
    return updated
