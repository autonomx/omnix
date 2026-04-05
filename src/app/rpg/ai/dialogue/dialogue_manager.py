from __future__ import annotations

from typing import Any, Dict, List

from .dialogue_prompt_builder import build_dialogue_prompt
from .dialogue_response_parser import parse_dialogue_response
from app.rpg.player import ensure_player_state


_MAX_HISTORY = 40


def _safe_dict(v: Any) -> Dict[str, Any]:
    return dict(v) if isinstance(v, dict) else {}


def _safe_list(v: Any) -> List[Any]:
    return list(v) if isinstance(v, list) else []


def _safe_str(v: Any) -> str:
    return "" if v is None else str(v)


class DialogueManager:
    def __init__(self, llm_client=None):
        self.llm_client = llm_client

    def _ensure_dialogue_state(self, simulation_state: Dict[str, Any]) -> Dict[str, Any]:
        simulation_state = ensure_player_state(simulation_state)
        player_state = simulation_state["player_state"]
        dialogue_state = player_state.setdefault("dialogue_state", {})
        dialogue_state.setdefault("active", False)
        dialogue_state.setdefault("npc_id", "")
        dialogue_state.setdefault("scene_id", "")
        dialogue_state.setdefault("turn_index", 0)
        dialogue_state.setdefault("history", [])
        dialogue_state.setdefault("suggested_replies", [])
        return simulation_state

    def start_dialogue(self, simulation_state: Dict[str, Any], npc_id: str, scene_id: str = "") -> Dict[str, Any]:
        simulation_state = self._ensure_dialogue_state(simulation_state)
        dialogue_state = simulation_state["player_state"]["dialogue_state"]
        dialogue_state["active"] = True
        dialogue_state["npc_id"] = _safe_str(npc_id)
        dialogue_state["scene_id"] = _safe_str(scene_id)
        dialogue_state["turn_index"] = 0
        dialogue_state["history"] = []
        dialogue_state["suggested_replies"] = []
        simulation_state["player_state"]["current_mode"] = "dialogue"
        simulation_state["player_state"]["active_npc_id"] = _safe_str(npc_id)
        return simulation_state

    def end_dialogue(self, simulation_state: Dict[str, Any]) -> Dict[str, Any]:
        simulation_state = self._ensure_dialogue_state(simulation_state)
        dialogue_state = simulation_state["player_state"]["dialogue_state"]
        dialogue_state["active"] = False
        dialogue_state["npc_id"] = ""
        dialogue_state["scene_id"] = ""
        dialogue_state["suggested_replies"] = []
        simulation_state["player_state"]["current_mode"] = "scene"
        simulation_state["player_state"]["active_npc_id"] = ""
        return simulation_state

    def _fallback_reply(self, npc: Dict[str, Any], player_message: str) -> Dict[str, Any]:
        npc_name = _safe_str(npc.get("name")) or "The NPC"
        msg = _safe_str(player_message).lower()

        if "help" in msg:
            reply = f"{npc_name} nods cautiously. \"I may be able to help, if your intentions are true.\""
            replies = ["What do you know?", "Can I trust you?", "What do you need?"]
        elif "who" in msg or "what" in msg:
            reply = f"{npc_name} considers your question before answering carefully."
            replies = ["Tell me more.", "Why does that matter?", "Who else knows?"]
        else:
            reply = f"{npc_name} listens in silence, then answers in a measured tone."
            replies = ["Go on.", "Why?", "What happens next?"]

        return {
            "reply_text": reply,
            "tone": "measured",
            "intent": "respond",
            "suggested_replies": replies[:4],
        }

    def send_message(
        self,
        simulation_state: Dict[str, Any],
        npc: Dict[str, Any],
        scene: Dict[str, Any],
        npc_mind: Dict[str, Any],
        player_message: str,
    ) -> Dict[str, Any]:
        simulation_state = self._ensure_dialogue_state(simulation_state)
        dialogue_state = simulation_state["player_state"]["dialogue_state"]

        turn_index = int(dialogue_state.get("turn_index", 0) or 0)
        history = _safe_list(dialogue_state.get("history"))

        history.append({
            "speaker": "player",
            "npc_id": _safe_str(dialogue_state.get("npc_id")),
            "text": _safe_str(player_message),
            "turn_index": turn_index,
        })

        parsed = None
        if self.llm_client:
            prompt = build_dialogue_prompt(
                npc=npc,
                scene=scene,
                player_state=simulation_state["player_state"],
                npc_mind=npc_mind,
                player_message=player_message,
            )
            try:
                raw = self.llm_client.generate_json(prompt)
                parsed = parse_dialogue_response(raw)
            except Exception:
                parsed = None

        if not parsed:
            parsed = self._fallback_reply(npc, player_message)

        history.append({
            "speaker": "npc",
            "npc_id": _safe_str(dialogue_state.get("npc_id")),
            "text": _safe_str(parsed.get("reply_text")),
            "turn_index": turn_index,
        })

        dialogue_state["history"] = history[-_MAX_HISTORY:]
        dialogue_state["turn_index"] = turn_index + 1
        dialogue_state["suggested_replies"] = list(parsed.get("suggested_replies") or [])[:4]

        return {
            "simulation_state": simulation_state,
            "reply": parsed,
            "dialogue_state": dict(dialogue_state),
        }