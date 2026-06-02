def _turns(count=100, *, repeated=False):
    rows = []
    for index in range(count):
        rows.append(
            {
                "turn_index": index + 1,
                "action_text": "wait" if repeated else f"diagnostic step {index % 7}",
                "location_id": "location:rusty_flagon" if repeated else f"location:{index % 5}",
                "destination_id": f"location:{(index + 1) % 5}" if not repeated and index % 3 == 0 else "",
                "quest_events": [{"quest_id": "quest:old_mill"}] if not repeated and index % 25 == 0 else [],
                "currency_delta": {"silver": -1} if not repeated and index % 20 == 0 else {},
                "journal_updates": ["new clue"] if not repeated and index % 30 == 0 else [],
                "combat_event": {"encounter_id": "encounter:road"} if not repeated and index == 40 else None,
            }
        )
    return rows


def test_ci_phase7_saved_certification_report_diagnostics_payload_contains_source_backed_summary():
    from app.rpg.session.autoplay_certification_artifact import build_saved_100_turn_certification_payload

    payload = build_saved_100_turn_certification_payload(
        {
            "turns": _turns(),
            "report_bytes": 250_000,
            "transcript_debug_bytes": 500_000,
            "checkpoint": {
                "final": {"digest": "digest:checkpoint"},
                "loaded": {"digest": "digest:checkpoint"},
            },
            "state": {
                "final": {"digest": "digest:state"},
                "loaded": {"digest": "digest:state"},
            },
        }
    )
    diagnostics = payload["report_diagnostics"]

    assert payload["ok"] is True
    assert diagnostics["source"] == "deterministic_phase7_saved_certification_report_diagnostics_gate"
    assert diagnostics["progress_counts"]["travel"] > 0
    assert diagnostics["progress_counts"]["quest"] > 0
    assert diagnostics["budget_summary"]["report_bytes"] == 250_000
    assert {row["kind"] for row in diagnostics["digest_checks"]} == {
        "final_vs_loaded_checkpoint_digest",
        "final_vs_loaded_state_digest",
    }


def test_ci_phase7_saved_certification_report_diagnostics_html_exposes_sections_and_escapes_values():
    from app.rpg.session.autoplay_certification_artifact import render_saved_100_turn_certification_report_html
    from app.rpg.session.turn_certification import build_full_100_turn_certification_result

    result = build_full_100_turn_certification_result(
        {
            "turns": _turns(repeated=True),
            "report_bytes": 6_000_000,
            "final_checkpoint_digest": "<final>",
            "loaded_checkpoint_digest": "<loaded>",
            "state_diff_source": "diagnostics_test_source",
        }
    )
    payload = {
        "certification_result": result,
        "report_diagnostics": {"source": "deterministic_phase7_saved_certification_report_diagnostics_gate"},
    }
    html = render_saved_100_turn_certification_report_html(payload)

    assert "Phase 7 Saved Certification Diagnostics" in html
    assert "Readiness Diagnostics" in html
    assert "Progress Counts" in html
    assert "Loop Summary" in html
    assert "Budget Summary" in html
    assert "State and Checkpoint Diagnostics" in html
    assert "Certification Blockers" in html
    assert "Certification Warnings" in html
    assert "report_growth_budget_exceeded" in html
    assert "repeated_action_loop_risk" in html
    assert "final_vs_loaded_checkpoint_digest_mismatch" in html
    assert "&lt;final&gt;" not in html
    assert "<final>" not in html


def test_ci_phase7_saved_certification_report_diagnostics_append_is_idempotent():
    from app.rpg.session.autoplay_certification_artifact import (
        append_saved_100_turn_certification_to_campaign_report_html,
        build_saved_100_turn_certification_payload,
    )

    payload = build_saved_100_turn_certification_payload({"turns": _turns()})
    first = append_saved_100_turn_certification_to_campaign_report_html("<html><body>Report</body></html>", payload)
    second = append_saved_100_turn_certification_to_campaign_report_html(first, payload)

    assert first == second
    assert first.count("<!-- rpg-phase7-real-autoplay-certification -->") == 1
    assert "</body>" in first


def test_ci_phase7_saved_certification_report_diagnostics_ready_helper_includes_sections():
    from app.rpg.session import assert_phase7_real_autoplay_certification_artifact_ready

    readiness = assert_phase7_real_autoplay_certification_artifact_ready()

    assert readiness["ok"] is True
    rendered_payload = readiness["payload"]
    assert rendered_payload["report_diagnostics"]["source"] == "deterministic_phase7_saved_certification_report_diagnostics_gate"
