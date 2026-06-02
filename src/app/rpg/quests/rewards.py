from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any, Dict, List

from app.rpg.economy.currency import add_currency, get_player_currency, normalize_currency, set_player_currency
from app.rpg.items.inventory_state import add_inventory_items, normalize_inventory_state

SOURCE = "deterministic_quest_reward_rules"


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _existing_quest(simulation_state: Dict[str, Any], quest_id: str) -> Dict[str, Any]:
    quest_state = _safe_dict(_safe_dict(simulation_state).get("quest_state"))
    quests = _safe_dict(quest_state.get("quests"))
    return _safe_dict(quests.get(_safe_str(quest_id)))


def stable_reward_id(quest_id: str, rewards: List[Dict[str, Any]]) -> str:
    payload = json.dumps(
        {"quest_id": quest_id, "rewards": rewards},
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    )
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]
    return f"reward:{digest}"


def normalize_reward_rules(rewards: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    normalized = []
    for reward in _safe_list(rewards):
        reward = _safe_dict(reward)
        reward_type = _safe_str(reward.get("type"))
        if reward_type == "currency":
            normalized.append({"type": "currency", "currency": normalize_currency(reward.get("currency")), "source": SOURCE})
        elif reward_type == "item":
            item_id = _safe_str(reward.get("item_id"))
            if item_id:
                normalized.append({"type": "item", "item_id": item_id, "qty": max(1, _safe_int(reward.get("qty"), 1)), "source": SOURCE})
        elif reward_type == "relationship":
            npc_id = _safe_str(reward.get("npc_id"))
            if npc_id:
                normalized.append({"type": "relationship", "npc_id": npc_id, "trust": _safe_int(reward.get("trust"), 0), "source": SOURCE})
    return normalized


def build_reward_payload(
    simulation_state: Dict[str, Any],
    quest_id: str,
    rewards: List[Dict[str, Any]],
) -> Dict[str, Any]:
    quest = _existing_quest(simulation_state, quest_id)
    if not quest:
        return _reject("quest_missing", quest_id=quest_id, reward_id="")
    normalized_rewards = normalize_reward_rules(rewards)
    reward_id = stable_reward_id(quest_id, normalized_rewards)
    payload = {
        "ok": True,
        "reason": "reward_payload_built",
        "quest_id": quest_id,
        "reward_id": reward_id,
        "rewards": normalized_rewards,
        "auto_granted": False,
        "already_claimed": bool(quest.get("reward_claimed")),
        "source": SOURCE,
    }
    if not any(_safe_dict(row).get("reward_id") == reward_id for row in _safe_list(quest.setdefault("rewards", []))):
        quest["rewards"].append(deepcopy(payload))
    return payload


def claim_quest_rewards(
    simulation_state: Dict[str, Any],
    *,
    quest_id: str,
    turn_index: int = 0,
) -> Dict[str, Any]:
    quest = _existing_quest(simulation_state, quest_id)
    if not quest:
        return _reject("quest_missing", quest_id=quest_id, reward_id="")
    if quest.get("status") != "completed":
        return _reject("quest_not_completed", quest_id=quest_id, reward_id="")
    rewards = normalize_reward_rules(_safe_list(quest.get("rewards")))
    if not rewards:
        rewards = normalize_reward_rules(_safe_list(_safe_dict(quest.get("metadata")).get("rewards")))
    if not rewards:
        return _reject("rewards_missing", quest_id=quest_id, reward_id="")
    reward_id = stable_reward_id(quest_id, rewards)
    if quest.get("reward_claimed"):
        return {
            "ok": True,
            "reason": "already_claimed",
            "quest_id": quest_id,
            "reward_id": _safe_str(quest.get("reward_id")) or reward_id,
            "effects": [],
            "quest": deepcopy(quest),
            "source": SOURCE,
        }

    effects = _apply_reward_effects(simulation_state, quest_id=quest_id, rewards=rewards, turn_index=turn_index)
    quest["reward_claimed"] = True
    quest["reward_id"] = reward_id
    quest["reward_claimed_turn"] = int(turn_index or 0)
    quest["reward_source"] = SOURCE
    quest["reward_log"] = list(_safe_list(quest.get("reward_log"))) + [
        {"reward_id": reward_id, "effects": deepcopy(effects), "turn_index": int(turn_index or 0), "source": SOURCE}
    ]
    return {
        "ok": True,
        "reason": "rewards_claimed",
        "quest_id": quest_id,
        "reward_id": reward_id,
        "effects": effects,
        "quest": deepcopy(quest),
        "source": SOURCE,
    }


def mark_reward_claimed(
    simulation_state: Dict[str, Any],
    quest_id: str,
    reward_id: str = "",
) -> Dict[str, Any]:
    result = claim_quest_rewards(simulation_state, quest_id=quest_id)
    if reward_id and result.get("ok") and result.get("reward_id") != reward_id:
        result["requested_reward_id"] = reward_id
    return result


def _apply_reward_effects(
    simulation_state: Dict[str, Any], *, quest_id: str, rewards: List[Dict[str, Any]], turn_index: int) -> List[Dict[str, Any]]:
    effects = []
    player_state = _safe_dict(simulation_state.get("player_state"))
    if not player_state:
        player_state = {}
        simulation_state["player_state"] = player_state

    for reward in rewards:
        reward_type = _safe_str(reward.get("type"))
        if reward_type == "currency":
            before = get_player_currency(simulation_state)
            delta = normalize_currency(reward.get("currency"))
            after = add_currency(before, delta)
            set_player_currency(simulation_state, after)
            player_state = _safe_dict(simulation_state.get("player_state"))
            effects.append({"type": "currency", "currency": delta, "before": before, "after": after, "source": SOURCE})
        elif reward_type == "item":
            item = {"item_id": _safe_str(reward.get("item_id")), "qty": max(1, _safe_int(reward.get("qty"), 1))}
            inventory_state = normalize_inventory_state(_safe_dict(simulation_state.get("player_state", {}).get("inventory_state")))
            inventory_state = add_inventory_items(inventory_state, [item])
            simulation_state.setdefault("player_state", {})["inventory_state"] = inventory_state
            player_state = _safe_dict(simulation_state.get("player_state"))
            effects.append({"type": "item", "item_id": item["item_id"], "qty": item["qty"], "source": SOURCE})
        elif reward_type == "relationship":
            npc_id = _safe_str(reward.get("npc_id"))
            trust_delta = _safe_int(reward.get("trust"), 0)
            relationships = _safe_dict(player_state.get("relationships"))
            current = _safe_dict(relationships.get(npc_id))
            before_trust = _safe_int(current.get("trust"), 0)
            current["trust"] = before_trust + trust_delta
            current["source"] = SOURCE
            relationships[npc_id] = current
            player_state["relationships"] = relationships
            simulation_state["player_state"] = player_state
            effects.append({"type": "relationship", "npc_id": npc_id, "trust": trust_delta, "before": before_trust, "after": current["trust"], "source": SOURCE})

    reward_state = _safe_dict(simulation_state.get("reward_state"))
    reward_state["source"] = SOURCE
    reward_state["log"] = list(_safe_list(reward_state.get("log"))) + [
        {"quest_id": quest_id, "turn_index": int(turn_index or 0), "effects": deepcopy(effects), "source": SOURCE}
    ]
    simulation_state["reward_state"] = reward_state
    return effects


def _reject(reason: str, *, quest_id: str, reward_id: str) -> Dict[str, Any]:
    return {"ok": False, "reason": reason, "quest_id": quest_id, "reward_id": reward_id, "source": SOURCE}
