from __future__ import annotations

from typing import Any, Dict, List


class NPCPromptBuilder:
    def build_decision_prompt(
        self,
        npc_context: Dict[str, Any],
        belief_summary: Dict[str, Dict[str, float]],
        memory_summary: List[Dict[str, Any]],
        goals: List[Dict[str, Any]],
        simulation_state: Dict[str, Any],
    ) -> str:
        npc_name = str(npc_context.get("name") or npc_context.get("npc_id") or "Unknown NPC")
        return (
            f"NPC: {npc_name}\n"
            f"Beliefs: {belief_summary}\n"
            f"Memory: {memory_summary}\n"
            f"Goals: {goals}\n"
            f"Context keys: {sorted((simulation_state or {}).keys())}\n"
        )