from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from app.rpg.session.narrative_engine_bridge import canonicalize_resolved_turn_result


REPO_ROOT = Path(__file__).resolve().parents[4]


def _result(mode: str, effects: dict) -> dict:
    return {
        "ok": True,
        "turn_id": f"turn:{mode}:1",
        "tick": 1,
        "state_revision": 1,
        "resolved_result": {
            "ok": True,
            "response_mode": mode,
            "stateful": True,
            "mechanic_resolved": True,
            "allowed_claim_refs": [],
        },
        "canonical_effects": deepcopy(effects),
        "scene": {
            "location_name": "The Rusty Flagon",
            "summary": "The low hearth throws warm light across the crowded common room.",
        },
        "narration": "Legacy narration.",
    }


def test_transaction_is_presented_without_mutating_authoritative_effects() -> None:
    result = _result(
        "transaction",
        {
            "currency": {"silver": -5},
            "inventory": {"added": ["room_key"]},
            "service": {"room_paid": True},
        },
    )
    before = deepcopy(result["canonical_effects"])
    result = canonicalize_resolved_turn_result(
        result,
        session_id="campaign:modes",
        player_input="Pay Bran five silver for a room.",
    )
    canonical = result["canonical_narrative_response"]
    purposes = [block["purpose"] for block in canonical["blocks"]]
    assert purposes[:2] == ["resolved_action", "consequence"]
    assert result["canonical_effects"] == before
    assert canonical["validation"]["passed"] is True
    assert result["source"] == "narrative_engine_resolved_turn_v1"


def test_combat_uses_resolved_action_and_consequence_only() -> None:
    result = _result(
        "combat",
        {
            "combat": {
                "attacker": "player",
                "target": "bandit:1",
                "hit": True,
                "damage": 4,
                "defeated": False,
            }
        },
    )
    result = canonicalize_resolved_turn_result(
        result,
        session_id="campaign:modes",
        player_input="Strike the bandit.",
    )
    canonical = result["canonical_narrative_response"]
    assert canonical["metadata"]["mode"] == "combat"
    assert [block["purpose"] for block in canonical["blocks"]][:2] == [
        "resolved_action",
        "consequence",
    ]
    assert canonical["validation"]["passed"] is True
    assert result["canonical_effects"]["combat"]["damage"] == 4


def test_failure_does_not_turn_into_success_or_state_change() -> None:
    result = _result(
        "failure",
        {
            "service": {"room_paid": False, "reason": "insufficient_funds"},
            "currency": {"silver": 0},
        },
    )
    before = deepcopy(result["canonical_effects"])
    result = canonicalize_resolved_turn_result(
        result,
        session_id="campaign:modes",
        player_input="Rent the room without enough silver.",
    )
    canonical = result["canonical_narrative_response"]
    assert canonical["metadata"]["mode"] == "failure"
    assert result["canonical_effects"] == before
    assert canonical["validation"]["passed"] is True
    assert "room_paid\": false" in result["summary"].casefold()


def test_major_quest_result_uses_cinematic_profile() -> None:
    result = _result(
        "major_beat",
        {
            "quest": {"id": "bandit_trail", "completed": True},
            "reward": {"xp": 100},
        },
    )
    result["resolved_result"]["quest_completed"] = True
    result = canonicalize_resolved_turn_result(
        result,
        session_id="campaign:modes",
        player_input="Return with proof that the bandits are defeated.",
    )
    canonical = result["canonical_narrative_response"]
    assert canonical["metadata"]["profile"] == "cinematic"
    assert canonical["metadata"]["mode"] == "major_beat"
    assert canonical["validation"]["passed"] is True


def test_gateway_routes_all_modes_through_single_presenter_before_shadow() -> None:
    source = (REPO_ROOT / "src/app/gateway/rpg_turn_pipeline.py").read_text(encoding="utf-8")
    assert "present_authoritative_turn" in source
    assert source.index("present_authoritative_turn") < source.index("attach_shadow_report")
    assert 'rpg_pipeline_span("turn.narrative_present")' in source
    assert "canonicalize_resolved_turn_result" not in source
