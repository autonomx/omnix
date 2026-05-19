from tests.rpg.autoplay.parallel_pipeline import build_combined_background_context_packet
from tests.rpg.autoplay_llm_campaign import (
    _apply_npc_line_current_action_relevance_gate,
    _build_npc_response_architecture_for_row,
    _build_npc_response_architecture_persistence_summary,
    _slim_transcript_row,
)


def _runtime_state_with_bran_profile():
    return {
        "npc_evolution": {
            "loaded_profiles": {
                "bran": {
                    "profile": {
                        "name": "Bran",
                        "role": "innkeeper",
                        "arc_stage": "guarded_ally",
                        "axes": {"trust": 2, "caution": 4},
                        "memories": [
                            {"summary": "Bran remembers the player asking about trouble on the road."}
                        ],
                        "future_hooks": [
                            {"summary": "Bran may warn the player if road pressure rises."}
                        ],
                    }
                }
            }
        }
    }


def test_npc_response_architecture_prioritizes_current_purchase_over_stale_memory():
    row = {
        "turn_index": 13,
        "player_action": "I buy two rations from Bran.",
        "canonical_turn_action": "I buy two rations from Bran.",
        "validated_presentation_category": "economy",
        "runtime_state": _runtime_state_with_bran_profile(),
        "npc": {
            "speaker": "Bran",
            "line": "Ask plainly. Are you looking for the traveler, the road, or the person who frightened them?",
        },
        "npc_speaker": "Bran",
        "npc_line": "Ask plainly. Are you looking for the traveler, the road, or the person who frightened them?",
        "current_action_response": {
            "required_focus": ["purchase_acknowledgement", "item_quantity_or_availability"],
            "npc_line_addresses_current_action": False,
        },
    }

    repaired = _apply_npc_line_current_action_relevance_gate(row)

    assert repaired["npc_line_repaired"] is True
    assert repaired["npc_line"] == "Two rations. That should keep you moving if the road turns bad."
    architecture = repaired["npc_response_architecture"]
    assert architecture["current_action_first"] is True
    assert "purchase_acknowledgement" in architecture["required_focus"]
    assert architecture["target_npc"]["profile_available"] is True
    assert architecture["target_npc"]["file_backed_memory_available"] is True


def test_combined_background_context_packet_contains_npc_response_architecture():
    packet = build_combined_background_context_packet(
        player_action="I buy two rations from Bran.",
        simulation_state={
            "present_npcs": [{"id": "bran", "name": "Bran", "role": "innkeeper"}],
            "npcs": {"bran": {"name": "Bran", "role": "innkeeper"}},
            "player": {"inventory": {"items": []}, "currency": {"gold": 5}},
        },
        runtime_state=_runtime_state_with_bran_profile(),
        turn_contract={
            "resolved_action": "purchase",
            "service_result": {"purchase": True},
        },
        semantic_action_record={"kind": "buy"},
    )

    architecture = packet["npc_response_architecture"]
    assert architecture["current_action_first"] is True
    assert architecture["target_npc"]["name"] == "Bran"
    assert architecture["target_npc"]["profile_available"] is True
    assert "purchase_acknowledgement" in architecture["required_focus"]
    assert "do_not_answer_stale_investigation_topic_unless_current_action_asks" in architecture["forbidden"]


def test_n1169_1_persists_architecture_into_slim_transcript_rows():
    row = {
        "turn_index": 13,
        "player_action": "I buy two rations from Bran.",
        "canonical_turn_action": "I buy two rations from Bran.",
        "validated_presentation_category": "economy",
        "runtime_state": _runtime_state_with_bran_profile(),
        "npc": {"speaker": "Bran", "line": "Two rations. That should keep you moving if the road turns bad."},
        "npc_speaker": "Bran",
        "npc_line": "Two rations. That should keep you moving if the road turns bad.",
    }

    repaired = _apply_npc_line_current_action_relevance_gate(row)
    slim = _slim_transcript_row(repaired)

    assert slim["npc_response_architecture"]["current_action_first"] is True
    assert "purchase_acknowledgement" in slim["current_action_response"]["required_focus"]
    assert slim["current_action_response"]["npc_line_addresses_current_action"] is True
    assert slim["npc_line_addresses_current_action"] is True


def test_n1169_1_architecture_persistence_summary_counts_transaction_rows():
    good_row = _apply_npc_line_current_action_relevance_gate(
        {
            "turn_index": 1,
            "player_action": "I buy two rations from Bran.",
            "canonical_turn_action": "I buy two rations from Bran.",
            "validated_presentation_category": "economy",
            "runtime_state": _runtime_state_with_bran_profile(),
            "npc": {"speaker": "Bran", "line": "Two rations. That should keep you moving if the road turns bad."},
            "npc_speaker": "Bran",
            "npc_line": "Two rations. That should keep you moving if the road turns bad.",
        }
    )

    summary = _build_npc_response_architecture_persistence_summary([good_row])

    assert summary["ok"] is True
    assert summary["architecture_row_count"] == 1
    assert summary["current_action_response_row_count"] == 1
    assert summary["transaction_focus_row_count"] == 1
    assert summary["transaction_addressed_row_count"] == 1
