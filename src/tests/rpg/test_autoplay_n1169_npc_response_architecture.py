from tests.rpg.autoplay.parallel_pipeline import build_combined_background_context_packet
from tests.rpg.autoplay_llm_campaign import (
    _apply_npc_line_current_action_relevance_gate,
    _build_npc_response_architecture_for_row,
    _build_npc_response_architecture_persistence_summary,
    _assert_npc_response_architecture_persisted,
    _build_final_transcript_artifact_rows,
    _slim_transcript_row,
    _sync_current_action_response_from_npc_response_architecture,
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


def test_n1169_2_syncs_current_action_response_from_architecture_focus():
    row = {
        "turn_index": 13,
        "player_action": "I buy two rations from Bran.",
        "canonical_turn_action": "I buy two rations from Bran.",
        "validated_presentation_category": "economy",
        "runtime_state": _runtime_state_with_bran_profile(),
        "npc": {"speaker": "Bran", "line": "Two rations. That should keep you moving if the road turns bad."},
        "npc_speaker": "Bran",
        "npc_line": "Two rations. That should keep you moving if the road turns bad.",
        "current_action_response": {
            "format_version": "current_action_response_v1",
            "required_focus": [],
            "npc_line_addresses_current_action": False,
        },
        "npc_response_architecture": {
            "format_version": "npc_response_architecture_v1",
            "current_action_first": True,
            "current_action": "I buy two rations from Bran.",
            "current_action_category": "economy",
            "required_focus": [
                "purchase_acknowledgement",
                "item_quantity_or_availability",
                "price_or_payment",
            ],
        },
    }

    synced = _sync_current_action_response_from_npc_response_architecture(row)

    response = synced["current_action_response"]
    assert "purchase_acknowledgement" in response["required_focus"]
    assert "item_quantity_or_availability" in response["required_focus"]
    assert response["npc_line_addresses_current_action"] is True
    assert response["architecture_focus_sync_applied"] is True
    assert synced["npc_line_addresses_current_action"] is True


def test_n1169_2_persistence_summary_fails_when_architecture_focus_not_synced():
    bad_row = {
        "turn_index": 13,
        "current_action_response": {"required_focus": []},
        "npc_response_architecture": {
            "current_action_first": True,
            "required_focus": ["purchase_acknowledgement"],
        },
    }

    summary = _build_npc_response_architecture_persistence_summary([bad_row])

    assert summary["ok"] is False
    assert summary["architecture_required_focus_row_count"] == 1
    assert summary["architecture_focus_missing_from_current_action_response_count"] == 1
    try:
        _assert_npc_response_architecture_persisted(
            {"npc_response_architecture_persistence_summary": summary}
        )
    except RuntimeError as exc:
        assert "focus_not_synced" in str(exc)
    else:
        raise AssertionError("expected architecture focus sync assertion failure")


def test_n1169_3_final_transcript_builder_forces_architecture_sync_after_meta_gate():
    rows = _build_final_transcript_artifact_rows(
        transcript=[
            {
                "turn_index": 13,
                "player_action": "I buy two rations from Bran.",
                "canonical_turn_action": "I buy two rations from Bran.",
                "validated_presentation_category": "economy",
                "runtime_state": _runtime_state_with_bran_profile(),
                "npc": {
                    "speaker": "Bran",
                    "line": "Two rations. That should keep you moving if the road turns bad.",
                },
                "npc_speaker": "Bran",
                "npc_line": "Two rations. That should keep you moving if the road turns bad.",
                "current_action_response": {
                    "format_version": "current_action_response_v1",
                    "required_focus": [],
                    "npc_line_addresses_current_action": False,
                },
            }
        ],
        transcript_artifacts={},
        summary={"turns_executed": 1},
        session_id="test-session",
    )

    row = rows[0]
    response = row["current_action_response"]
    assert row["npc_response_architecture"]["required_focus"]
    assert "purchase_acknowledgement" in response["required_focus"]
    assert response["npc_line_addresses_current_action"] is True
    assert row["npc_line_addresses_current_action"] is True


def test_n1169_3_summary_self_heals_rows_before_counting_focus_sync():
    bad_row = {
        "turn_index": 13,
        "player_action": "I buy two rations from Bran.",
        "canonical_turn_action": "I buy two rations from Bran.",
        "validated_presentation_category": "economy",
        "npc": {
            "speaker": "Bran",
            "line": "Two rations. That should keep you moving if the road turns bad.",
        },
        "npc_speaker": "Bran",
        "npc_line": "Two rations. That should keep you moving if the road turns bad.",
        "current_action_response": {
            "format_version": "current_action_response_v1",
            "required_focus": [],
            "npc_line_addresses_current_action": False,
        },
        "npc_response_architecture": {
            "format_version": "npc_response_architecture_v1",
            "current_action_first": True,
            "current_action": "I buy two rations from Bran.",
            "current_action_category": "economy",
            "required_focus": [
                "purchase_acknowledgement",
                "item_quantity_or_availability",
                "price_or_payment",
            ],
        },
    }

    summary = _build_npc_response_architecture_persistence_summary([bad_row])

    assert summary["ok"] is True
    assert summary["architecture_required_focus_row_count"] == 1
    assert summary["architecture_focus_missing_from_current_action_response_count"] == 0
    assert summary["current_action_response_architecture_sync_count"] == 1


def test_n1169_4_artifact_row_sync_helper_writes_required_focus_into_rows():
    stale_row = {
        "turn_index": 13,
        "player_action": "I buy two rations from Bran.",
        "canonical_turn_action": "I buy two rations from Bran.",
        "validated_presentation_category": "economy",
        "npc": {
            "speaker": "Bran",
            "line": "Two rations. That should keep you moving if the road turns bad.",
        },
        "npc_speaker": "Bran",
        "npc_line": "Two rations. That should keep you moving if the road turns bad.",
        "current_action_response": {
            "format_version": "current_action_response_v1",
            "required_focus": [],
            "npc_line_addresses_current_action": False,
        },
        "npc_response_architecture": {
            "format_version": "npc_response_architecture_v1",
            "current_action_first": True,
            "current_action": "I buy two rations from Bran.",
            "current_action_category": "economy",
            "required_focus": [
                "purchase_acknowledgement",
                "item_quantity_or_availability",
                "price_or_payment",
            ],
        },
    }

    synced_rows = _sync_current_action_response_artifact_rows([stale_row])
    synced = synced_rows[0]
    response = synced["current_action_response"]

    assert "purchase_acknowledgement" in response["required_focus"]
    assert "item_quantity_or_availability" in response["required_focus"]
    assert response["npc_line_addresses_current_action"] is True
    assert synced["npc_line_addresses_current_action"] is True
    _assert_current_action_response_artifact_rows_synced(
        synced_rows,
        artifact_name="unit-test",
    )


def test_n1169_4_artifact_row_assertion_catches_unsynced_json_rows():
    stale_row = {
        "turn_index": 13,
        "current_action_response": {"required_focus": []},
        "npc_response_architecture": {
            "required_focus": ["purchase_acknowledgement"],
        },
    }

    try:
        _assert_current_action_response_artifact_rows_synced(
            [stale_row],
            artifact_name="transcript.json",
        )
    except RuntimeError as exc:
        assert "current_action_response_artifact_focus_not_synced" in str(exc)
        assert "transcript.json" in str(exc)
    else:
        raise AssertionError("expected artifact sync assertion failure")
