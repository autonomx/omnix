import inspect


def _realistic_saved_artifacts(count=100):
    turns = []
    for index in range(count):
        turns.append(
            {
                "turn_index": index + 1,
                "action_text": f"saved artifact travel step {index % 7}",
                "location_id": f"location:{index % 5}",
                "quest_events": [{"quest_id": "quest:old_mill"}] if index % 25 == 0 else [],
                "currency_delta": {"silver": -1} if index % 20 == 0 else {},
                "journal_updates": ["new clue"] if index % 30 == 0 else [],
                "combat_event": {"encounter_id": "encounter:road"} if index == 40 else None,
            }
        )
    return {
        "transcript": {
            "rows": turns,
            "text": "\n".join(row["action_text"] for row in turns),
        },
        "report": {
            "html": "<html><body><h1>Campaign Report</h1></body></html>",
        },
        "checkpoint": {
            "final_checkpoint_digest": "digest:phase7:real-artifact",
            "loaded_checkpoint_digest": "digest:phase7:real-artifact",
        },
        "artifact_source": "test_phase7_real_autoplay_certification_artifact",
    }


def test_ci_phase7_real_autoplay_artifact_normalizes_saved_report_outputs():
    from app.rpg.session import build_real_autoplay_certification_artifact

    normalized = build_real_autoplay_certification_artifact(_realistic_saved_artifacts())

    assert normalized["artifact_source"] == "test_phase7_real_autoplay_certification_artifact"
    assert len(normalized["turns"]) == 100
    assert normalized["report_bytes"] > 0
    assert normalized["transcript_debug_bytes"] > 0
    assert normalized["final_checkpoint_digest"] == "digest:phase7:real-artifact"
    assert normalized["loaded_checkpoint_digest"] == "digest:phase7:real-artifact"


def test_ci_phase7_real_autoplay_artifact_builds_saved_certification_payload():
    from app.rpg.session import build_saved_100_turn_certification_payload

    payload = build_saved_100_turn_certification_payload(_realistic_saved_artifacts())
    result = payload["certification_result"]

    assert payload["source"] == "deterministic_phase7_real_autoplay_certification_artifact_gate"
    assert payload["ok"] is True
    assert payload["reason"] == "phase7_real_autoplay_certification_artifact_ready"
    assert result["source"] == "deterministic_phase7_full_100_turn_certification_gate"
    assert result["certification_status"] == "final_100_turn_certification_passed"
    assert result["actual_turns"] == 100
    assert result["blockers"] == []
    assert payload["certification_contract"]["source"] == "deterministic_phase7_full_100_turn_certification_gate"


def test_ci_phase7_real_autoplay_artifact_blocks_bad_saved_artifact():
    from app.rpg.session import build_saved_100_turn_certification_payload

    saved = _realistic_saved_artifacts(99)
    saved["checkpoint"]["loaded_checkpoint_digest"] = "digest:phase7:loaded-drift"
    payload = build_saved_100_turn_certification_payload(saved)
    blocker_kinds = {row["kind"] for row in payload["certification_result"]["blockers"]}

    assert payload["ok"] is False
    assert payload["reason"] == "phase7_real_autoplay_certification_artifact_blocked"
    assert "artifact_turn_count_not_exact" in blocker_kinds
    assert "final_vs_loaded_checkpoint_digest_mismatch" in blocker_kinds


def test_ci_phase7_real_autoplay_artifact_renders_safe_idempotent_report_section():
    from app.rpg.session import (
        append_saved_100_turn_certification_to_campaign_report_html,
        build_saved_100_turn_certification_payload,
        render_saved_100_turn_certification_report_html,
    )

    payload = build_saved_100_turn_certification_payload(_realistic_saved_artifacts())
    section = render_saved_100_turn_certification_report_html(payload)
    appended = append_saved_100_turn_certification_to_campaign_report_html(
        "<html><body><h1>Campaign Report</h1></body></html>",
        payload,
    )
    appended_again = append_saved_100_turn_certification_to_campaign_report_html(appended, payload)

    assert "<!-- rpg-phase7-real-autoplay-certification -->" in section
    assert "Phase 7.7 Real Autoplay Certification" in section
    assert "final_100_turn_certification_passed" in section
    assert appended.count("<!-- rpg-phase7-real-autoplay-certification -->") == 1
    assert appended_again == appended


def test_ci_phase7_real_autoplay_artifact_exports_and_provider_free_source():
    from app.rpg import session
    from app.rpg.session import autoplay_certification_artifact

    readiness = session.assert_phase7_real_autoplay_certification_artifact_ready()
    source = inspect.getsource(autoplay_certification_artifact).lower()

    assert readiness["ok"] is True
    assert readiness["reason"] == "phase7_real_autoplay_certification_artifact_gate_ready"
    assert readiness["blockers"] == []
    assert session.build_real_autoplay_certification_artifact
    assert session.build_saved_100_turn_certification_payload
    assert session.render_saved_100_turn_certification_report_html
    assert session.append_saved_100_turn_certification_to_campaign_report_html
    assert session.assert_phase7_real_autoplay_certification_artifact_ready
    assert "openai" not in source
    assert "requests." not in source
    assert "httpx" not in source
    assert "subprocess" not in source
