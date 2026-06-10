from app.rpg.interactive_cli_response_quality import (
    apply_interactive_response_quality_cleanup,
    apply_response_quality_to_matrix_result,
)
from tests.rpg.interactive_cli_survival_repair import apply_survival_visible_response_repair


class _Scenario:
    scenario_id = "shop_sell_attempt"
    commands = (
        "Bran, can I sell you one ration?",
        "How much copper would you give me for a ration?",
        "I sell one ration to Bran.",
    )


def _survival_turn_summary():
    return {
        "raw_result": {
            "narration": "Generic provider narration.",
            "turn_contract": {
                "survival_action": {
                    "applied": True,
                    "need": "hunger",
                    "before": {"hunger": 80, "thirst": 82, "fatigue": 78},
                    "after": {"hunger": 45, "thirst": 82, "fatigue": 78},
                    "inventory_consumed": [{"item_id": "ration", "name": "ration"}],
                }
            },
            "survival_action": {
                "applied": True,
                "need": "hunger",
                "before": {"hunger": 80, "thirst": 82, "fatigue": 78},
                "after": {"hunger": 45, "thirst": 82, "fatigue": 78},
                "inventory_consumed": [{"item_id": "ration", "name": "ration"}],
            },
        },
        "raw_narration": "Generic provider narration.",
        "extracted": {},
    }


def _sell_turn_summary(*, target_npc="survival state", narration=None, line=None, player_input="I sell one ration to Bran."):
    raw_narration = narration or "The practical request lands against the unease of the room, making ordinary business feel less ordinary."
    npc_line = line if line is not None else "Bran watches you over the rim of a cup. Ask plainly."
    diagnostics = {
        "final_classification": {
            "action_type": "economy",
            "target_npc": target_npc,
            "requested_terms": ["sell", "ration", "Bran"],
        }
    }
    return {
        "player_input": player_input,
        "raw_result": {
            "narration": raw_narration,
            "npc": {"speaker": "Bran", "line": npc_line},
            "interactive_cli_intent_diagnostics": diagnostics,
        },
        "raw_narration": raw_narration,
        "raw_npc": {"speaker": "Bran", "line": npc_line},
        "narration_preview": raw_narration,
        "interactive_cli_intent_diagnostics": diagnostics,
        "extracted": {},
    }


def _final_classification(turn):
    return turn["interactive_cli_intent_diagnostics"]["final_classification"]


def test_phase13_53_sell_ration_is_not_repaired_as_eating_ration():
    repaired = apply_survival_visible_response_repair(_survival_turn_summary(), player_input="I sell one ration to Bran.")

    assert repaired["raw_narration"] == "Generic provider narration."
    assert "interactive_cli_survival_repair" not in repaired
    assert "You eat a ration" not in repaired["raw_result"]["narration"]


def test_phase13_53_direct_eat_ration_still_gets_survival_repair():
    repaired = apply_survival_visible_response_repair(_survival_turn_summary(), player_input="I eat a ration.")

    assert repaired["interactive_cli_survival_repair"]["applied"] is True
    assert "You eat a ration" in repaired["raw_narration"]


def test_phase13_53_sell_ration_gets_bran_trade_fallback():
    repaired = apply_interactive_response_quality_cleanup(
        _sell_turn_summary(),
        player_input="I sell one ration to Bran.",
    )

    assert repaired["interactive_cli_response_quality"]["cleanup_source"] == "sell_request_specificity"
    assert repaired["raw_npc"]["speaker"] == "Bran"
    assert "can't buy that ration" in repaired["raw_npc"]["line"]
    assert "selling provisions is not set up" in repaired["raw_npc"]["line"]
    assert "eat a ration" not in repaired["raw_narration"].lower()
    assert _final_classification(repaired)["target_npc"] == "Bran"
    assert repaired["raw_result"]["interactive_cli_intent_diagnostics"]["final_classification"]["target_npc"] == "Bran"
    assert "ration" in _final_classification(repaired)["requested_terms"]


def test_phase13_53_sell_ration_value_question_gets_bran_trade_fallback():
    repaired = apply_interactive_response_quality_cleanup(
        _sell_turn_summary(target_npc="", narration="Result: Bran refuses. Reason: unreasonable demand.", line="", player_input="How much copper would you give me for a ration?"),
        player_input="How much copper would you give me for a ration?",
    )

    assert repaired["interactive_cli_response_quality"]["cleanup_source"] == "sell_request_specificity"
    assert repaired["raw_npc"]["speaker"] == "Bran"
    assert "ration" in repaired["raw_npc"]["line"]
    assert "not set up" in repaired["raw_npc"]["line"]
    assert repaired["narration_preview"] == "Bran treats the request as a trade question, not a survival action."
    assert _final_classification(repaired)["target_npc"] == "Bran"


def test_phase13_53_sell_ration_specific_bran_output_with_missing_target_is_stabilized():
    summary = _sell_turn_summary(
        target_npc="",
        narration="Bran considers the ration as a trade question.",
        line="I can't buy that ration from you yet; selling provisions is not set up.",
    )

    repaired = apply_interactive_response_quality_cleanup(summary, player_input="I sell one ration to Bran.")

    assert repaired["interactive_cli_response_quality"]["cleanup_source"] == "sell_request_target_stability"
    assert repaired["raw_npc"]["line"] == "I can't buy that ration from you yet; selling provisions is not set up in the current trade state."
    assert _final_classification(repaired)["target_npc"] == "Bran"


def test_phase13_53_sell_ration_specific_bran_output_is_preserved():
    summary = _sell_turn_summary(
        target_npc="Bran",
        narration="Bran considers the ration as a trade question.",
        line="I can't buy that ration from you yet; selling provisions is not set up.",
    )

    repaired = apply_interactive_response_quality_cleanup(summary, player_input="I sell one ration to Bran.")

    assert "interactive_cli_response_quality" not in repaired
    assert repaired["raw_npc"]["line"] == "I can't buy that ration from you yet; selling provisions is not set up."


def test_phase13_53_matrix_cleanup_uses_scenario_command_fallback_and_updates_metadata():
    result = {
        "results": [
            {
                "scenario": _Scenario(),
                "result": {
                    "turns": [
                        _sell_turn_summary(player_input=""),
                        _sell_turn_summary(
                            target_npc="",
                            narration="Result: Bran refuses. Reason: unreasonable demand.",
                            line="",
                            player_input="",
                        ),
                    ]
                },
            }
        ]
    }

    cleanup = apply_response_quality_to_matrix_result(result)

    assert cleanup["changed_turns"] == 2
    turns = result["results"][0]["result"]["turns"]
    assert turns[0]["interactive_cli_intent_diagnostics"]["final_classification"]["target_npc"] == "Bran"
    assert turns[1]["raw_npc"]["speaker"] == "Bran"
    assert turns[1]["interactive_cli_intent_diagnostics"]["final_classification"]["target_npc"] == "Bran"
    assert "sell" in turns[1]["interactive_cli_intent_diagnostics"]["final_classification"]["requested_terms"]
