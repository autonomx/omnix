from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List

from app.rpg.quests.journal import add_journal_entry
from app.rpg.quests.rewards import claim_quest_rewards

SOURCE = "deterministic_quest_return_flow"

RETURN_TERMS = {"return", "report", "reported", "complete", "completed", "done", "finished", "reward", "claim"}


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def _tokenize(text: str) -> set[str]:
    stripped = [chunk.strip(".,!?;:'\"()[]{}") for chunk in _safe_str(text).lower().split()]
    return {chunk for chunk in stripped if chunk}


def _existing_quest(simulation_state: Dict[str, Any], quest_id: str) -> Dict[str, Any]:
    quest_state = _safe_dict(_safe_dict(simulation_state).get("quest_state"))
    quests = _safe_dict(quest_state.get("quests"))
    return _safe_dict(quests.get(_safe_str(quest_id)))


def classify_quest_return(player_text: str) -> Dict[str, Any]:
    tokens = _tokenize(player_text)
    matched_terms = sorted(tokens.intersection(RETURN_TERMS))
    return {
        "ok": bool(matched_terms),
        "reason": "quest_return_detected" if matched_terms else "quest_return_not_detected",
        "matched_terms": matched_terms,
        "source": SOURCE,
    }


def report_completed_quest_to_giver(
    simulation_state: Dict[str, Any],
    *,
    quest_id: str,
    giver_id: str,
    player_text: str = "",
    turn_index: int = 0,
) -> Dict[str, Any]:
    classification = classify_quest_return(player_text) if player_text else {"ok": True, "reason": "quest_return_explicit", "matched_terms": [], "source": SOURCE}
    if not classification.get("ok"):
        return {"ok": False, "reason": "not_quest_return", "classification": classification, "source": SOURCE}
    quest = _existing_quest(simulation_state, quest_id)
    if not quest:
        return _reject("quest_missing", quest_id=quest_id, giver_id=giver_id)
    if quest.get("status") != "completed":
        return _reject("quest_not_completed", quest_id=quest_id, giver_id=giver_id)
    if _safe_str(quest.get("giver_id")) and _safe_str(quest.get("giver_id")) != giver_id:
        return _reject("wrong_giver", quest_id=quest_id, giver_id=giver_id)

    prior_reported = bool(quest.get("reported_to_giver"))
    reward_result = claim_quest_rewards(simulation_state, quest_id=quest_id, turn_index=turn_index)
    quest = _existing_quest(simulation_state, quest_id)
    quest["reported_to_giver"] = True
    quest["reported_to_giver_id"] = giver_id
    quest["reported_turn"] = int(turn_index or 0)
    quest["report_source"] = SOURCE
    report_entry = {
        "quest_id": quest_id,
        "giver_id": giver_id,
        "turn_index": int(turn_index or 0),
        "prior_reported": prior_reported,
        "reward_reason": reward_result.get("reason"),
        "source": SOURCE,
    }
    quest["report_log"] = list(_safe_list(quest.get("report_log"))) + [deepcopy(report_entry)]
    journal_result = add_journal_entry(
        simulation_state,
        quest_id=quest_id,
        event_type="quest_reported_to_giver",
        what_happened=f"Reported quest result to {giver_id}.",
        what_i_learned="The quest result has been formally reported.",
        next_objective="Ask about the next lead or prepare for travel.",
        turn_index=turn_index,
        tags=["quest", "report", "return"],
    )
    return {
        "ok": True,
        "reason": "quest_reported_to_giver" if not prior_reported else "quest_already_reported_to_giver",
        "quest_id": quest_id,
        "giver_id": giver_id,
        "classification": classification,
        "reward_result": reward_result,
        "journal_result": journal_result,
        "report_entry": report_entry,
        "quest": deepcopy(quest),
        "source": SOURCE,
    }


def build_quest_return_narration_contract(report_result: Dict[str, Any]) -> Dict[str, Any]:
    result = _safe_dict(report_result)
    allowed_claims = []
    if result.get("ok"):
        allowed_claims.append(f"Quest reported: {_safe_str(result.get('quest_id'))} to {_safe_str(result.get('giver_id'))}")
        reward_result = _safe_dict(result.get("reward_result"))
        if reward_result.get("reason") == "rewards_claimed":
            allowed_claims.append(f"Rewards claimed: {_safe_str(reward_result.get('reward_id'))}")
        elif reward_result.get("reason") == "already_claimed":
            allowed_claims.append("Rewards were already claimed.")
    return {
        "source": SOURCE,
        "allowed_return_claims": allowed_claims,
        "forbidden_return_claims": [
            "Do not claim unearned rewards.",
            "Do not report an incomplete quest as complete.",
            "Do not invent a different quest giver or quest outcome.",
        ],
    }


def _reject(reason: str, *, quest_id: str, giver_id: str) -> Dict[str, Any]:
    return {"ok": False, "reason": reason, "quest_id": quest_id, "giver_id": giver_id, "source": SOURCE}
