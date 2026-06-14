"""Current-turn prompt guardrails for RPG narration.

The narrator prompt carries a lot of useful continuity.  This module makes the
latest player action/question more explicit so older conversation context cannot
win over the current turn.
"""
from __future__ import annotations

import json
from typing import Any, Dict

from app.rpg.ai import world_scene_narrator_prompts as _prompts
from app.rpg.presentation.current_turn_prompt_contract import (
    build_runtime_current_turn_prompt_contract,
)


def _safe_dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


_ORIGINAL_BUILD_SCENE_PROMPT = _prompts.build_scene_prompt


def build_scene_prompt(scene: Dict[str, Any], narration_context: Dict[str, Any], tone: str = "dramatic") -> str:
    prompt = _ORIGINAL_BUILD_SCENE_PROMPT(scene, narration_context, tone=tone)
    contract = build_runtime_current_turn_prompt_contract(
        scene=_safe_dict(scene),
        narration_context=_safe_dict(narration_context),
    )
    required_response = _safe_dict(contract.get("required_response"))
    current_question = _safe_str(required_response.get("question_text") or contract.get("current_question")).strip()
    followup_reference = _safe_dict(required_response.get("followup_reference"))
    player_action = _safe_str(contract.get("player_action")).strip()
    if not current_question:
        return prompt

    followup_lines = ""
    if followup_reference:
        target_name = _safe_str(followup_reference.get("target_name") or followup_reference.get("target_id")).strip()
        topic = _safe_str(followup_reference.get("topic")).strip()
        followup_lines = (
            f"- Treat latest current_question as a short follow-up"
            f"{' to ' + target_name if target_name else ''}"
            f"{' about: ' + json.dumps(topic, ensure_ascii=False) if topic else ''}.\n"
            "- Do NOT say the NPC is unsure which earlier topic the follow-up refers to when this reference is present.\n"
            "- If the follow-up asks why, answer the cause/reason first; if the NPC does not know, say so directly and give only a grounded lead or suspicion.\n"
            "- Do not answer a why question by merely restating the visible symptom.\n"
        )

    current_turn_block = f"""

CURRENT PLAYER TURN OVERRIDE:
- Latest player_action: {json.dumps(player_action, ensure_ascii=False)}
- Latest current_question: {json.dumps(current_question, ensure_ascii=False)}
- The NPC line MUST answer latest current_question before reacting to older conversation history.
{followup_lines}- If turn_contract.interpreted_action.target_name exists, that NPC is the respondent unless the latest player_action explicitly changes target.
- Do NOT answer an older question from Ongoing conversation threads, recent facts, profile memory, or prior NPC dialogue.
- Do NOT repeat the previous NPC answer unless the latest player_action explicitly asks the NPC to repeat it.
- If the current question asks about trouble, danger, rumors, problems, or recent events, answer that topic directly and naturally with bounded uncertainty instead of repeating the NPC's earlier well-being answer.
- Keep simulation truth: do not invent rewards, combat results, purchases, travel, or state changes.
"""
    return prompt + current_turn_block


_prompts.build_scene_prompt = build_scene_prompt

try:
    from app.rpg.ai import world_scene_narrator_runtime as _runtime

    _runtime.build_scene_prompt = build_scene_prompt
except Exception:
    pass

__all__ = ["build_scene_prompt"]
