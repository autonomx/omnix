from tests.rpg.autoplay_llm_campaign import (
    _fallback_npc_line_for_current_action,
    _slim_transcript_row,
    _sync_current_action_response_from_npc_response_architecture,
)


def _ration_row(session_id: str):
    return {
        "turn_index": 13,
        "session_id": session_id,
        "player_action": "I buy two rations from Bran.",
        "canonical_turn_action": "I buy two rations from Bran.",
        "validated_presentation_category": "economy",
        "npc": {"speaker": "Bran", "line": "stale"},
        "npc_speaker": "Bran",
        "npc_line": "stale",
    }


def test_n11610_bounded_persona_response_variation_is_seeded_and_fact_locked():
    row_a = _ration_row("variation-session-a")
    row_a_repeat = _ration_row("variation-session-a")
    row_b = _ration_row("variation-session-b")

    line_a = _fallback_npc_line_for_current_action(row_a)
    line_a_repeat = _fallback_npc_line_for_current_action(row_a_repeat)
    line_b = _fallback_npc_line_for_current_action(row_b)

    assert line_a == line_a_repeat
    assert "ration" in line_a.lower()
    assert "two" in line_a.lower() or "2" in line_a.lower()
    assert "ration" in line_b.lower()
    assert "two" in line_b.lower() or "2" in line_b.lower()
    assert row_a["npc_response_variation"]["bounded"] is True
    assert row_a["npc_response_variation"]["facts_locked"] is True
    assert row_a["npc_response_variation"]["variant_family"] == "economy.purchase.rations"
    assert row_a["npc_response_variation"]["facts"] == {
        "item": "rations",
        "quantity": 2,
        "transaction": "purchase",
    }
    assert row_a["npc_response_variant_id"]
    assert row_b["npc_response_variant_id"]


def test_n11610_bounded_persona_response_variation_survives_slim_transcript():
    row = _ration_row("variation-persist-session")
    line = _fallback_npc_line_for_current_action(row)
    row["npc"] = {"speaker": "Bran", "line": line}
    row["npc_line"] = line

    slim = _slim_transcript_row(row)

    assert slim["npc_response_variant_id"] == row["npc_response_variant_id"]
    assert slim["npc_response_variation"]["bounded"] is True
    assert slim["npc_response_variation"]["facts_locked"] is True


def test_n11610_1_static_fallback_line_gets_bounded_variation_at_artifact_sync():
    row = _ration_row("variation-static-existing-session")
    row["npc"] = {
        "speaker": "Bran",
        "line": "Two rations. That should keep you moving if the road turns bad.",
    }
    row["npc_line"] = "Two rations. That should keep you moving if the road turns bad."
    row["npc_response_architecture"] = {
        "format_version": "npc_response_architecture_v1",
        "current_action_first": True,
        "current_action": "I buy two rations from Bran.",
        "current_action_category": "economy",
        "required_focus": [
            "purchase_acknowledgement",
            "item_quantity_or_availability",
            "price_or_payment",
        ],
        "target_npc": {"speaker": "Bran"},
    }

    synced = _sync_current_action_response_from_npc_response_architecture(row)

    assert synced["npc_response_variation"]["bounded"] is True
    assert synced["npc_response_variation"]["facts_locked"] is True
    assert synced["npc_response_variation"]["variant_family"] == "economy.purchase.rations"
    assert synced["npc_response_variant_id"]
    assert synced["npc"]["line"] == synced["npc_line"]
    assert "ration" in synced["npc_line"].lower()
    assert "two" in synced["npc_line"].lower() or "2" in synced["npc_line"].lower()
    assert synced["npc_response_variation_applied_to_existing_static_fallback"] is True
