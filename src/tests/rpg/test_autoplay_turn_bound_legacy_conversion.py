from tests.rpg.autoplay_llm_campaign import (
    _attach_legacy_background_timing_events_turn_bound,
    _build_background_presentation_attachment_summary,
    _build_turn_presentation_identity,
)


def test_legacy_background_timing_event_converts_to_turn_bound_attachment():
    session_id = "s1"

    id_1 = _build_turn_presentation_identity(
        session_id=session_id,
        turn_index=1,
        canonical_turn_action="I ask Bran about the witness.",
        turn_contract={"ok": True, "kind": "dialogue"},
    )
    id_2 = _build_turn_presentation_identity(
        session_id=session_id,
        turn_index=2,
        canonical_turn_action="I buy two rations from Bran.",
        turn_contract={"ok": True, "kind": "buy"},
    )

    transcript = [
        {
            "turn_index": 1,
            "player_action": "I ask Bran about the witness.",
            "canonical_turn_action": "I ask Bran about the witness.",
            "turn_presentation_identity": id_1,
            "turn_id": id_1["turn_id"],
            "presentation_status": "pending",
        },
        {
            "turn_index": 2,
            "player_action": "I buy two rations from Bran.",
            "canonical_turn_action": "I buy two rations from Bran.",
            "turn_presentation_identity": id_2,
            "turn_id": id_2["turn_id"],
            "presentation_status": "pending",
        },
    ]

    summary = {
        "session_id": session_id,
        "background_result_timing_summary": {
            "jobs_attached_total": 1,
            "attachment_events": [
                {
                    "source_turn": 1,
                    "attach_turn": 2,
                    "lag_turns": 1,
                    "phase": "pre_turn",
                    "job_id": "job:1",
                    "result": {
                        "turn_index": 1,
                        "narration": "Bran lowers his voice as the witness is mentioned.",
                        "npc": {
                            "speaker": "Bran",
                            "line": "Ask plainly. Are you looking for the traveler, the road, or the person who frightened them?",
                        },
                    },
                }
            ],
        },
        "background_jobs": {"combined_background_llm_jobs": 1},
        "deferred_narration_trace_summary": {"ok_jobs": 1},
    }

    orphans = []

    events = _attach_legacy_background_timing_events_turn_bound(
        transcript=transcript,
        summary=summary,
        session_id=session_id,
        orphaned_results=orphans,
    )

    assert len(events) == 1
    assert events[0]["attached"] is True
    assert events[0]["turn_bound_verified"] is True
    assert events[0]["legacy_observed_only"] is False
    assert events[0]["row_index"] == 0

    assert transcript[0]["presentation_status"] in {"attached", "attached_repaired"}
    assert "witness" in transcript[0]["narration"].lower()
    assert transcript[1]["presentation_status"] == "pending"
    assert transcript[1].get("npc", {}) == {}
    assert orphans == []


def test_background_attachment_summary_requires_turn_bound_verified_events():
    summary = {
        "background_result_timing_summary": {"jobs_attached_total": 1},
        "background_jobs": {"combined_background_llm_jobs": 1},
        "deferred_narration_trace_summary": {"ok_jobs": 1},
        "background_presentation_attachment_events": [
            {
                "attached": True,
                "reason": "attached_to_matching_turn",
                "turn_bound_verified": True,
                "legacy_observed_only": False,
                "converted_from_legacy_timing_event": True,
            }
        ],
        "orphaned_background_presentation_results": [],
    }

    attachment = _build_background_presentation_attachment_summary(
        summary,
        [{"turn_index": 1, "presentation_status": "attached"}],
    )

    assert attachment["expected_attachment_count"] == 1
    assert attachment["event_count"] == 1
    assert attachment["turn_bound_verified_count"] == 1
    assert attachment["legacy_observed_count"] == 0
    assert attachment["turn_bound_attachment_verified"] is True
