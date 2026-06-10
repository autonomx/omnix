from app.rpg.interactive_cli_response_quality import apply_interactive_response_quality_cleanup
from tests.rpg.interactive_cli_survival_repair import apply_survival_visible_response_repair


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


def _sell_turn_summary(*, target_npc="survival state", narration=None, line=None):
    raw_narration = narration or "The practical request lands against the unease of the room, making ordinary business feel less ordinary."
    npc_line = line if line is not None else "Bran watches you over the rim of a cup. Ask plainly."
    return {
        "raw_result": {
            "narration": raw_narration,
            "npc": {"speaker": "Bran", "line": npc_line},
        },
        "raw_narration": raw_narration,
        "raw_npc": {"speaker": "Bran", "line": npc_line},
        "narration_preview": raw_narration,
        "interactive_cli_intent_diagnostics": {
            "final_classification": {
                "action_type": "economy",
                "target_npc": target_npc,
                "requested_terms": ["sell", "ration", "Bran"],
            }
        },
        "extracted": {},
    }


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


def test_phase13_53_sell_ration_value_question_gets_bran_trade_fallback():
    repaired = apply_interactive_response_quality_cleanup(
        _sell_turn_summary(target_npc="", narration="Result: Bran refuses. Reason: unreasonable demand.", line=""),
        player_input="How much copper would you give me for a ration?",
    )

    assert repaired["interactive_cli_response_quality"]["cleanup_source"] == "sell_request_specificity"
    assert repaired["raw_npc"]["speaker"] == "Bran"
    assert "ration" in repaired["raw_npc"]["line"]
    assert "not set up" in repaired["raw_npc"]["line"]
    assert repaired["narration_preview"] == "Bran treats the request as a trade question, not a survival action."


def test_phase13_53_sell_ration_specific_bran_output_is_preserved():
    summary = _sell_turn_summary(
        target_npc="Bran",
        narration="Bran considers the ration as a trade question.",
        line="I can't buy that ration from you yet; selling provisions is not set up.",
    )

    repaired = apply_interactive_response_quality_cleanup(summary, player_input="I sell one ration to Bran.")

    assert "interactive_cli_response_quality" not in repaired
    assert repaired["raw_npc"]["line"] == "I can't buy that ration from you yet; selling provisions is not set up."
