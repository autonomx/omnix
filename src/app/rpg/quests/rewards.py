from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List

from app.rpg.quests.state import get_quest


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def stable_reward_id(quest_id: str, rewards: List[Dict[str, Any]]) -> str:
    payload = json.dumps(
        {"quest_id": quest_id, "rewards": rewards},
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    )
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]
    return f"reward:{digest}"


def build_reward_payload(
    simulation_state: Dict[str, Any],
    quest_id: str,
    rewards: List[Dict[str, Any]],
) -> Dict[str, Any]:
    quest = get_quest(simulation_state, quest_id)
    if not quest:
        return {
            "ok": False,
            "reason": "quest_missing",
            "quest_id": quest_id,
            "reward_id": "",
            "rewards": [],
            "auto_granted": False,
        }
    normalized_rewards = [
        dict(row)
        for row in _safe_list(rewards)
        if isinstance(row, dict)
    ]
    reward_id = stable_reward_id(quest_id, normalized_rewards)
    payload = {
        "ok": True,
        "reason": "reward_payload_built",
        "quest_id": quest_id,
        "reward_id": reward_id,
        "rewards": normalized_rewards,
        "auto_granted": False,
        "already_claimed": bool(quest.get("reward_claimed")),
    }
    if not any(row.get("reward_id") == reward_id for row in quest.setdefault("rewards", [])):
        quest["rewards"].append(payload)
    return payload


def mark_reward_claimed(
    simulation_state: Dict[str, Any],
    quest_id: str,
    reward_id: str,
) -> Dict[str, Any]:
    quest = get_quest(simulation_state, quest_id)
    if not quest:
        return {"ok": False, "reason": "quest_missing", "quest_id": quest_id}
    if quest.get("reward_claimed"):
        return {
            "ok": True,
            "reason": "already_claimed",
            "quest_id": quest_id,
            "reward_id": reward_id,
        }
    quest["reward_claimed"] = True
    return {
        "ok": True,
        "reason": "claimed",
        "quest_id": quest_id,
        "reward_id": reward_id,
    }