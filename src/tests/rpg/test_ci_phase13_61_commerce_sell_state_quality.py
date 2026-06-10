from __future__ import annotations

from types import SimpleNamespace

from app.rpg.interactive_cli_commerce_response_quality import (
    COMMERCE_RESPONSE_QUALITY_PATCH,
    apply_commerce_sell_state_to_matrix_result,
)
from app.rpg.interactive_cli_commerce_state import (
    COMMERCE_STATE_VERSION,
    apply_sell_attempt,
    default_commerce_state,
    describe_sell_attempt,
    is_sell_request,
    normalize_commerce_state,
)
from tests.rpg import interactive_feature_matrix as feature_matrix
from tests.rpg import interactive_feature_matrix_zip as feature_zip
from tests.rpg import interactive_intent_matrix as matrix


def _turn(player_input: str, narration: str = "The moment responds without producing a major new consequence.") -> dict:
    diagnostics = {
        "final_classification": {
            "action_type": "general",
            "target_npc": "",
            "requested_terms": [],
        }
    }
    raw = {
        "narration": narration,
        "npc": {"speaker": "", "line": ""},
        "interactive_cli_intent_diagnostics": diagnostics,
    }
    return {
        "player_input": player_input,
        "raw_narration": narration,
        "narration": narration,
        "narration_preview": narration,
        "raw_result": raw,
        "result": raw,
        "interactive_cli_intent_diagnostics": diagnostics,
        "extracted": {"narration": narration},
        "summary": {"provider_called": True},
    }


def test_commerce_state_records_unsupported_sell_without_mutation() -> None:
    state = default_commerce_state()

    assert state["version"] == COMMERCE_STATE_VERSION
    assert state["merchant_name"] == "Bran"
    assert state["buyback_supported"] is False
    assert is_sell_request("How much copper would you give me for a ration?")

    next_state = apply_sell_attempt(state, player_input="I sell one ration to Bran.", turn_index=3)
    normalized = normalize_commerce_state(next_state)
    narration, line = describe_sell_attempt(normalized)

    assert normalized["attempted_sells"][-1]["item"] == "ration"
    assert normalized["attempted_sells"][-1]["outcome"] == "unsupported_buyback_refusal"
    assert normalized["attempted_sells"][-1]["inventory_mutated"] is False
    assert normalized["currency_delta_copper"] == 0
    assert "trade/sell attempt" in narration
    assert "sell/buyback is not supported" in line


def test_commerce_sell_cleanup_rewrites_probe_turns_with_state() -> None:
    scenario = SimpleNamespace(
        scenario_id="shop_sell_attempt",
        commands=(
            "Bran, can I sell you one ration?",
            "How much copper would you give me for a ration?",
            "I sell one ration to Bran.",
        ),
    )
    result = {
        "results": [
            {
                "scenario": scenario,
                "result": {
                    "summary": {"completed_turns": 3, "error_count": 0},
                    "turns": [_turn(command) for command in scenario.commands],
                },
            }
        ]
    }

    cleanup = apply_commerce_sell_state_to_matrix_result(result)

    turns = result["results"][0]["result"]["turns"]
    assert cleanup["changed_turns"] == 3
    assert cleanup["patch"] == COMMERCE_RESPONSE_QUALITY_PATCH
    assert all(turn["interactive_cli_commerce_state"]["merchant_name"] == "Bran" for turn in turns)
    assert len(turns[2]["interactive_cli_commerce_state"]["attempted_sells"]) == 3
    assert turns[2]["interactive_cli_commerce_state"]["inventory_mutated"] is False
    assert turns[2]["interactive_cli_commerce_state"]["currency_delta_copper"] == 0
    assert "sell/buyback is not supported" in turns[2]["npc_line"]
    final = turns[2]["interactive_cli_intent_diagnostics"]["final_classification"]
    assert final["action_type"] == "economy"
    assert final["service_kind"] == "trade"
    assert final["target_npc"] == "Bran"
    assert "sell" in final["requested_terms"]
    assert "ration" in final["requested_terms"]


def test_commerce_cleanup_revalidates_shop_sell_to_hard_pass() -> None:
    scenario = feature_matrix._select_feature_scenarios(["shop_sell_attempt"])[0]
    scenario_result = {
        "summary": {"completed_turns": 3, "error_count": 0},
        "turns": [_turn(command) for command in scenario.commands],
    }
    result = {
        "summary": {"scenario_count": 1},
        "results": [
            {
                "scenario": scenario,
                "result": scenario_result,
                "validation": matrix.validate_matrix_run(scenario, scenario_result),
            }
        ],
    }

    cleanup = apply_commerce_sell_state_to_matrix_result(result)
    result["summary"]["commerce_response_quality_cleanup"] = cleanup
    revalidated = feature_zip._revalidate_after_cleanup(result)

    assert cleanup["changed_turns"] == 3
    assert revalidated["summary"]["failed"] == []
    assert revalidated["summary"]["feature_gap_count"] == 0
    assert revalidated["summary"]["passed"] == 1
