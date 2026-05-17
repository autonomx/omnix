from tests.rpg.autoplay_llm_campaign import (
    _attach_background_presentation_result_turn_bound,
    _build_turn_presentation_identity,
)


def test_late_background_result_attaches_to_matching_old_turn_not_latest():
    transcript = []

    id_13 = _build_turn_presentation_identity(
        session_id="s1",
        turn_index=13,
        canonical_turn_action="I ask Bran about the witness.",
        turn_contract={"ok": True, "kind": "dialogue"},
    )
    id_14 = _build_turn_presentation_identity(
        session_id="s1",
        turn_index=14,
        canonical_turn_action="I buy two rations from Bran.",
        turn_contract={"ok": True, "kind": "buy"},
    )

    transcript.append(
        {
            "turn_index": 13,
            "player_action": "I ask Bran about the witness.",
            "canonical_turn_action": "I ask Bran about the witness.",
            "turn_presentation_identity": id_13,
            "turn_id": id_13["turn_id"],
            "presentation_status": "pending",
        }
    )
    transcript.append(
        {
            "turn_index": 14,
            "player_action": "I buy two rations from Bran.",
            "canonical_turn_action": "I buy two rations from Bran.",
            "turn_presentation_identity": id_14,
            "turn_id": id_14["turn_id"],
            "presentation_status": "pending",
        }
    )

    orphaned = []

    result_for_13 = {
        "turn_presentation_identity": id_13,
        "narration": "Bran lowers his voice as the witness is mentioned.",
        "npc": {
            "speaker": "Bran",
            "line": "Ask plainly. Are you looking for the traveler, the road, or the person who frightened them?",
        },
    }

    event = _attach_background_presentation_result_turn_bound(
        transcript=transcript,
        result=result_for_13,
        orphaned_results=orphaned,
    )

    assert event["attached"] is True
    assert event["row_index"] == 0
    assert transcript[0]["presentation_status"] in {"attached", "attached_repaired"}
    assert "traveler" in transcript[0].get("npc", {}).get("line", "")
    assert transcript[1]["presentation_status"] == "pending"
    assert transcript[1].get("npc", {}) == {}
    assert orphaned == []


def test_background_result_with_wrong_action_hash_is_orphaned():
    id_row = _build_turn_presentation_identity(
        session_id="s1",
        turn_index=14,
        canonical_turn_action="I buy two rations from Bran.",
        turn_contract={"ok": True, "kind": "buy"},
    )
    id_payload_wrong = _build_turn_presentation_identity(
        session_id="s1",
        turn_index=14,
        canonical_turn_action="I ask Bran about the witness.",
        turn_contract={"ok": True, "kind": "dialogue"},
    )

    transcript = [
        {
            "turn_index": 14,
            "player_action": "I buy two rations from Bran.",
            "canonical_turn_action": "I buy two rations from Bran.",
            "turn_presentation_identity": id_row,
            "turn_id": id_row["turn_id"],
            "presentation_status": "pending",
        }
    ]

    orphaned = []

    event = _attach_background_presentation_result_turn_bound(
        transcript=transcript,
        result={
            "turn_presentation_identity": id_payload_wrong,
            "narration": "Bran asks about the witness.",
            "npc": {"speaker": "Bran", "line": "Are you looking for the traveler?"},
        },
        orphaned_results=orphaned,
    )

    assert event["attached"] is False
    assert event["reason"] == "identity_mismatch"
    assert transcript[0]["presentation_status"] == "pending"
    assert orphaned
