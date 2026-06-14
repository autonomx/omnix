from __future__ import annotations

from typing import Any, Mapping

from app.rpg.session.turn_memory_common import d, first


def memory_npc(result: Mapping[str, Any] | None) -> dict[str, str]:
    result_dict = d(result)
    nested_result = d(result_dict.get("result"))
    candidates = (d(result_dict.get("npc")), d(nested_result.get("npc")))
    for candidate in candidates:
        speaker = first(candidate.get("speaker"), candidate.get("name"))
        npc_id = first(candidate.get("id"), candidate.get("npc_id"))
        if speaker or npc_id:
            return {
                "id": npc_id or f"npc:{speaker.lower()}",
                "speaker": speaker,
                "line": first(candidate.get("line"), candidate.get("text")),
            }
    return {"id": "", "speaker": "", "line": ""}
