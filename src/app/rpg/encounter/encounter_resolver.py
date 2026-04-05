"""Phase 8.2 — Encounter Resolver (dict-based).

Handles encounter turn progression, player action application, NPC turns,
and encounter resolution. Operates on plain dicts for serialization.

Bounds:
- log max 100 entries
- participants max 12
- available_actions max 12
"""

from __future__ import annotations

from typing import Any, Dict, List

from .encounter_actions import build_player_actions

_MAX_LOG = 100


def _safe_list(v: Any) -> List[Any]:
    return list(v) if isinstance(v, list) else []


def _safe_dict(v: Any) -> Dict[str, Any]:
    return dict(v) if isinstance(v, dict) else {}


def _safe_str(v: Any) -> str:
    return "" if v is None else str(v)


class EncounterResolver:
    """Resolves encounter actions and turn progression on dict state."""

    def start(self, encounter_state: Dict[str, Any]) -> Dict[str, Any]:
        """Activate encounter and populate available actions."""
        encounter_state = dict(encounter_state or {})
        participants = _safe_list(encounter_state.get("participants"))

        encounter_state["active"] = True
        encounter_state["status"] = "active"
        encounter_state["round"] = int(encounter_state.get("round", 1) or 1)

        if participants:
            encounter_state["turn_index"] = 0
            encounter_state["active_actor_id"] = _safe_str(participants[0].get("actor_id"))
        else:
            encounter_state["turn_index"] = 0
            encounter_state["active_actor_id"] = ""

        encounter_state["available_actions"] = build_player_actions(encounter_state)
        return encounter_state

    def _advance_turn(self, encounter_state: Dict[str, Any]) -> Dict[str, Any]:
        """Advance to the next participant's turn deterministically."""
        participants = _safe_list(encounter_state.get("participants"))
        if not participants:
            encounter_state["active_actor_id"] = ""
            return encounter_state

        turn_index = int(encounter_state.get("turn_index", 0) or 0) + 1
        if turn_index >= len(participants):
            turn_index = 0
            encounter_state["round"] = int(encounter_state.get("round", 1) or 1) + 1

        encounter_state["turn_index"] = turn_index
        encounter_state["active_actor_id"] = _safe_str(participants[turn_index].get("actor_id"))
        encounter_state["available_actions"] = build_player_actions(encounter_state)
        return encounter_state

    def apply_player_action(
        self, encounter_state: Dict[str, Any], action_type: str, target_id: str = ""
    ) -> Dict[str, Any]:
        """Apply a player action and advance turn."""
        encounter_state = dict(encounter_state or {})
        action_type = _safe_str(action_type)
        target_id = _safe_str(target_id)

        active_actor_id = _safe_str(encounter_state.get("active_actor_id"))
        if not active_actor_id:
            return encounter_state

        participants = _safe_list(encounter_state.get("participants"))
        log = _safe_list(encounter_state.get("log"))

        text = f"{active_actor_id or 'player'} uses {action_type}"
        if target_id:
            text += f" on {target_id}"

        log.append({
            "round": int(encounter_state.get("round", 1) or 1),
            "text": text,
            "type": "player_action",
            "log_type": action_type,
            "target_id": target_id,
        })

        # Apply combat damage
        if action_type == "attack" and target_id:
            for p in participants:
                pd = _safe_dict(p)
                if _safe_str(pd.get("actor_id")) == target_id:
                    p["hp"] = max(0, int(pd.get("hp", 0) or 0) - 2)

        # Apply social stress
        elif action_type in {"persuade", "pressure", "threaten"} and target_id:
            for p in participants:
                pd = _safe_dict(p)
                if _safe_str(pd.get("actor_id")) == target_id:
                    p["stress"] = min(10, int(pd.get("stress", 0) or 0) + 1)

        encounter_state["participants"] = participants
        encounter_state["log"] = log[-_MAX_LOG:]
        return self._advance_turn(encounter_state)

    def apply_npc_turn(self, encounter_state: Dict[str, Any]) -> Dict[str, Any]:
        """Apply an NPC action for the current active actor and advance."""
        encounter_state = dict(encounter_state or {})
        participants = _safe_list(encounter_state.get("participants"))
        log = _safe_list(encounter_state.get("log"))
        active_actor_id = _safe_str(encounter_state.get("active_actor_id"))

        actor = None
        for p in participants:
            pd = _safe_dict(p)
            if _safe_str(pd.get("actor_id")) == active_actor_id:
                actor = pd
                break

        if actor:
            log.append({
                "round": int(encounter_state.get("round", 1) or 1),
                "text": f"{_safe_str(actor.get('name')) or active_actor_id} takes a measured action.",
                "type": "npc_action",
                "log_type": "npc_turn",
                "target_id": "",
            })

        encounter_state["log"] = log[-_MAX_LOG:]
        return self._advance_turn(encounter_state)

    def resolve_if_finished(self, encounter_state: Dict[str, Any]) -> Dict[str, Any]:
        """Check if encounter is resolved (no enemies alive) and update status."""
        encounter_state = dict(encounter_state or {})
        participants = _safe_list(encounter_state.get("participants"))
        enemies_alive = [
            p for p in participants
            if _safe_str(_safe_dict(p).get("side")) == "enemy" and int(_safe_dict(p).get("hp", 0) or 0) > 0
        ]

        if not enemies_alive and participants:
            encounter_state["active"] = False
            encounter_state["status"] = "resolved"
            log = _safe_list(encounter_state.get("log"))
            log.append({
                "round": int(encounter_state.get("round", 1) or 1),
                "text": "Encounter resolved.",
                "type": "system",
            })
            encounter_state["log"] = log[-_MAX_LOG:]

        return encounter_state