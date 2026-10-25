from __future__ import annotations

# RPG session runtime responsibility module.
from app.apps.rpg.session.state_normalization import _safe_dict as _safe_dict, _safe_str as _safe_str
import json as json
import hashlib as hashlib
from typing import (
    Any as Any, Dict as Dict, List as List,
)


def _find_npc_target_by_name(simulation_state: dict[str, Any], text: str) -> str:
    simulation_state = _safe_dict(simulation_state)
    npc_index = _safe_dict(simulation_state.get("npc_index"))
    text_lc = _safe_str(text).strip().lower()
    if not text_lc:
        return ""

    candidates: list[tuple[str, str]] = []
    for npc_id, raw in sorted(npc_index.items()):
        npc = _safe_dict(raw)
        name = _safe_str(npc.get("name")).strip().lower()
        role = _safe_str(npc.get("role")).strip().lower()
        title = _safe_str(npc.get("title")).strip().lower()
        stable_id = _safe_str(npc.get("id") or npc_id)
        if stable_id and name:
            candidates.append((stable_id, name))
        if stable_id and role:
            candidates.append((stable_id, role))
        if stable_id and title:
            candidates.append((stable_id, title))

    candidates.sort(key=lambda item: (-len(item[1]), item[1], item[0]))
    for npc_id, npc_name in candidates:
        if npc_name in text_lc:
            return npc_id
    return ""


__all__ = ["_find_npc_target_by_name"]
