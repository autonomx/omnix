from __future__ import annotations

import json
from typing import Any, Dict

from app.rpg.campaign_journal.journal import build_player_story_recap


STORY_AUTHORING_SYSTEM_PROMPT = """You are an RPG campaign story authoring assistant.

You must output only valid JSON.
You are not the simulation.
You do not grant rewards.
You do not decide outcomes.
You only propose a story_proposal_v1 object.

Rules:
- Use only the provided campaign recap as context.
- Mark uncertain information as rumor.
- Do not reveal hidden or secret lore.
- Do not invent confirmed facts that contradict the recap.
- Do not mutate player inventory, currency, XP, health, or quest rewards.
- Keep arcs, events, effects, and escalation rules bounded.
- All IDs must be stable strings.
"""


def build_story_authoring_prompt(
    simulation_state: Dict[str, Any],
    *,
    authoring_goal: str,
    turn_index: int = 0,
    max_items: int = 10,
) -> Dict[str, Any]:
    recap = build_player_story_recap(
        simulation_state,
        turn_index=turn_index,
        max_items=max_items,
    )
    user_payload = {
        "task": "Create one story_proposal_v1 JSON object.",
        "authoring_goal": str(authoring_goal or "Create a small grounded story pack."),
        "required_schema": {
            "proposal_version": "story_proposal_v1",
            "proposal_type": "story_pack",
            "proposal_id": "stable_unique_id",
            "title": "short title",
            "lore_entries": [],
            "story_arcs": [],
            "story_events": [],
            "escalation_rules": [],
        },
        "campaign_recap": recap,
        "hard_constraints": [
            "Return JSON only.",
            "Do not include markdown.",
            "Do not include commentary.",
            "Do not reveal secret lore.",
            "Rumors must remain rumors.",
            "No direct rewards, currency, XP, loot, or inventory changes.",
            "Use only supported story event effects.",
        ],
    }
    return {
        "system": STORY_AUTHORING_SYSTEM_PROMPT,
        "user": json.dumps(user_payload, sort_keys=True, ensure_ascii=False),
        "recap": recap,
    }


def build_story_repair_prompt(
    *,
    invalid_proposal: Any,
    validation: Dict[str, Any],
    authoring_goal: str,
) -> Dict[str, str]:
    payload = {
        "task": "Repair the invalid story_proposal_v1 JSON object.",
        "authoring_goal": str(authoring_goal or ""),
        "invalid_proposal": invalid_proposal,
        "validation_errors": validation.get("errors") or [],
        "hard_constraints": [
            "Return JSON only.",
            "Do not include markdown.",
            "Preserve the user's authoring goal.",
            "Fix only validation errors.",
            "Do not reveal secret lore.",
            "Do not add unsupported effects.",
        ],
    }
    return {
        "system": STORY_AUTHORING_SYSTEM_PROMPT,
        "user": json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str),
    }