from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict

from app.rpg.quests.journal import build_quest_journal_summary, ensure_journal_state
from app.rpg.quests.rumors import build_rumor_summary, ensure_rumor_state
from app.rpg.quests.state import normalize_quest_state

SOURCE = "deterministic_quest_persistence"
VERSION = 1


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _normalize_quest_giver_state(value: Any) -> Dict[str, Any]:
    value = _safe_dict(value)
    givers = {}
    for giver_id, giver in _safe_dict(value.get("givers")).items():
        offers = {}
        for quest_id, offer in _safe_dict(_safe_dict(giver).get("offers")).items():
            offer = _safe_dict(offer)
            offers[str(quest_id)] = {
                "quest_id": str(offer.get("quest_id") or quest_id),
                "giver_id": str(offer.get("giver_id") or giver_id),
                "status": str(offer.get("status") or "offered"),
                "offered_turn": offer.get("offered_turn"),
                "accepted_turn": offer.get("accepted_turn"),
                "source": str(offer.get("source") or "deterministic_quest_giver_state"),
            }
        givers[str(giver_id)] = {
            "giver_id": str(giver_id),
            "offers": offers,
            "source": str(_safe_dict(giver).get("source") or "deterministic_quest_giver_state"),
        }
    return {"version": 1, "givers": givers, "source": "deterministic_quest_giver_state"}


def _normalize_reward_state(value: Any) -> Dict[str, Any]:
    value = _safe_dict(value)
    return {
        "source": str(value.get("source") or "deterministic_quest_reward_rules"),
        "log": [dict(row) for row in value.get("log", []) if isinstance(row, dict)],
    }


def build_quest_persistence_snapshot(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    quest_state = normalize_quest_state(_safe_dict(simulation_state).get("quest_state"))
    quest_giver_state = _normalize_quest_giver_state(_safe_dict(simulation_state).get("quest_giver_state"))
    journal_state = deepcopy(ensure_journal_state({"journal_state": _safe_dict(simulation_state).get("journal_state")}))
    rumor_state = deepcopy(ensure_rumor_state({"rumor_state": _safe_dict(simulation_state).get("rumor_state")}))
    reward_state = _normalize_reward_state(_safe_dict(simulation_state).get("reward_state"))
    return {
        "version": VERSION,
        "source": SOURCE,
        "quest_state": quest_state,
        "quest_giver_state": quest_giver_state,
        "journal_state": journal_state,
        "rumor_state": rumor_state,
        "reward_state": reward_state,
        "summary": {
            "quest_count": len(quest_state.get("quests", {})),
            "journal_entry_count": build_quest_journal_summary({"journal_state": journal_state}).get("entry_count", 0),
            "rumor_count": build_rumor_summary({"rumor_state": rumor_state}).get("rumor_count", 0),
            "reward_log_count": len(reward_state.get("log", [])),
        },
    }


def restore_quest_persistence_snapshot(simulation_state: Dict[str, Any], snapshot: Dict[str, Any]) -> Dict[str, Any]:
    snapshot = _safe_dict(snapshot)
    if snapshot.get("source") != SOURCE:
        return {"ok": False, "reason": "invalid_snapshot_source", "source": SOURCE}
    if int(snapshot.get("version") or 0) != VERSION:
        return {"ok": False, "reason": "unsupported_snapshot_version", "source": SOURCE}

    simulation_state["quest_state"] = normalize_quest_state(snapshot.get("quest_state"))
    simulation_state["quest_giver_state"] = _normalize_quest_giver_state(snapshot.get("quest_giver_state"))
    simulation_state["journal_state"] = ensure_journal_state({"journal_state": snapshot.get("journal_state")})
    simulation_state["rumor_state"] = ensure_rumor_state({"rumor_state": snapshot.get("rumor_state")})
    simulation_state["reward_state"] = _normalize_reward_state(snapshot.get("reward_state"))
    return {
        "ok": True,
        "reason": "quest_persistence_snapshot_restored",
        "snapshot": build_quest_persistence_snapshot(simulation_state),
        "source": SOURCE,
    }


def assert_quest_persistence_roundtrip(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    snapshot = build_quest_persistence_snapshot(simulation_state)
    restored: Dict[str, Any] = {}
    result = restore_quest_persistence_snapshot(restored, snapshot)
    restored_snapshot = result.get("snapshot", {}) if result.get("ok") else {}
    return {
        "ok": bool(result.get("ok")) and snapshot == restored_snapshot,
        "reason": "quest_persistence_roundtrip_matched" if snapshot == restored_snapshot else "quest_persistence_roundtrip_mismatch",
        "snapshot": snapshot,
        "restored_snapshot": restored_snapshot,
        "source": SOURCE,
    }
