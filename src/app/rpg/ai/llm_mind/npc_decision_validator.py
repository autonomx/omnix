from __future__ import annotations

from typing import Any, Dict


_ALLOWED_INTENTS = {
    "observe",
    "support",
    "confront",
    "avoid",
    "investigate",
    "negotiate",
    "stabilize",
    "retaliate",
    "wait",
}

_ALLOWED_ACTION_TYPES = {
    "observe",
    "support",
    "confront",
    "avoid",
    "investigate",
    "negotiate",
    "stabilize",
    "retaliate",
    "wait",
}


class NPCDecisionValidator:
    def validate(self, data: Dict[str, Any]) -> Dict[str, Any]:
        data = dict(data or {})

        intent = str(data.get("intent") or "wait")
        action_type = str(data.get("action_type") or "wait")

        if intent not in _ALLOWED_INTENTS:
            intent = "wait"
        if action_type not in _ALLOWED_ACTION_TYPES:
            action_type = "wait"

        data["intent"] = intent
        data["action_type"] = action_type

        data["npc_id"] = str(data.get("npc_id") or "")
        data["tick"] = int(data.get("tick", 0) or 0)
        data["target_id"] = str(data.get("target_id") or "")
        data["target_kind"] = str(data.get("target_kind") or "")
        data["location_id"] = str(data.get("location_id") or "")
        data["reason"] = str(data.get("reason") or "")
        data["dialogue_hint"] = str(data.get("dialogue_hint") or "")
        data["urgency"] = float(data.get("urgency", 0.0) or 0.0)
        return data
