import inspect
from copy import deepcopy


def _turns(count=100):
    rows = []
    for index in range(count):
        rows.append(
            {
                "turn_index": index + 1,
                "action_text": f"travel step {index % 6}",
                "location_id": f"location:{index % 5}",
                "quest_events": [{"quest_id": "quest:old_mill"}] if index % 25 == 0 else [],
                "currency_delta": {"silver": -1} if index % 20 == 0 else {},
                "journal_updates": ["new clue"] if index % 30 == 0 else [],
                "combat_event": {"encounter_id": "encounter:road"} if index == 40 else None,
            }
        )
    return rows


def test_ci_phase7_100_turn_readiness_report_renders_complete_result_without_critical_blockers():
    from app.rpg.session import build_100_turn_readiness_report_payload, build_100_turn_readiness_result

    readiness = build_100_turn_readiness_result(_turns(), report_bytes=250_000, transcript_debug_bytes=500_000)
    payload = build_100_turn_readiness_report_payload(readiness)

    assert payload["source"] == "deterministic_phase7_100_turn_readiness_report_gate"
    assert payload["readiness_source"] == "deterministic_phase7_100_turn_readiness_gate"
    assert payload["ok"] is True
    assert payload["certification_status"] == "advisory_not_final_certification"
    assert payload["turn_count"] == {
        "actual": 100,
        "expected": 100,
        "ok": True,
        "source": "deterministic_phase7_100_turn_readiness_gate",
    }
    assert payload["severity_counts"]["critical"] == 0
    assert payload["critical_blockers"] == []
    assert payload["progress_metrics"]["travel"] > 0
    assert payload["progress_metrics"]["quest"] > 0
    assert payload["progress_metrics"]["economy"] > 0
    assert payload["progress_metrics"]["combat"] > 0
    assert payload["progress_metrics"]["journal"] > 0


def test_ci_phase7_100_turn_readiness_report_maps_blockers_to_critical_source_backed_entries():
    from app.rpg.session import build_100_turn_readiness_report_payload, build_100_turn_readiness_result

    readiness = build_100_turn_readiness_result(
        _turns(20),
        expected_turns=100,
        report_bytes=2_000_000,
        transcript_debug_bytes=3_000_000,
    )
    payload = build_100_turn_readiness_report_payload(readiness)
    critical_kinds = {row["kind"] for row in payload["critical_blockers"]}

    assert payload["ok"] is False
    assert payload["reason"] == "phase7_100_turn_readiness_report_has_critical_blockers"
    assert payload["severity_counts"]["critical"] == 3
    assert critical_kinds == {
        "incomplete_turn_count",
        "report_growth_budget_exceeded",
        "transcript_debug_growth_budget_exceeded",
    }
    assert all(row["severity"] == "critical" for row in payload["critical_blockers"])
    assert all(row["source"] == "deterministic_phase7_100_turn_readiness_gate" for row in payload["critical_blockers"])


def test_ci_phase7_100_turn_readiness_report_maps_warnings_and_advisories():
    from app.rpg.session import build_100_turn_readiness_report_payload, build_100_turn_readiness_result

    turns = [{"turn_index": index + 1, "action_text": "wait", "location_id": "location:rusty_flagon"} for index in range(100)]
    readiness = build_100_turn_readiness_result(turns)
    payload = build_100_turn_readiness_report_payload(readiness)
    warning_kinds = {row["kind"] for row in payload["warnings"]}
    advisory_kinds = {row["kind"] for row in payload["advisories"]}

    assert payload["ok"] is True
    assert "repeated_action_loop_risk" in warning_kinds
    assert "repeated_location_loop_risk" in warning_kinds
    assert "no_progress_loop_risk" in warning_kinds
    assert "no_progress_signals_detected" in advisory_kinds
    assert "advisory_until_full_100_turn_autoplay_gate" in advisory_kinds
    assert all(row["source"] for row in payload["warnings"])
    assert all(row["source"] for row in payload["advisories"])


def test_ci_phase7_100_turn_readiness_report_html_is_escaped_safe_and_idempotent():
    from app.rpg.session import (
        append_100_turn_readiness_report_to_campaign_report_html,
        build_100_turn_readiness_report_payload,
        build_100_turn_readiness_result,
        render_100_turn_readiness_report_html,
    )

    readiness = build_100_turn_readiness_result(_turns())
    readiness = deepcopy(readiness)
    readiness["warnings"] = [
        {"kind": "<script>alert(1)</script>", "severity": "advisory", "source": "<bad&source>"}
    ]
    before = deepcopy(readiness)

    payload = build_100_turn_readiness_report_payload(readiness)
    html = render_100_turn_readiness_report_html(readiness)
    appended = append_100_turn_readiness_report_to_campaign_report_html(
        "<html><body><main><h1>Campaign Report</h1></main></body></html>",
        readiness,
    )
    appended_again = append_100_turn_readiness_report_to_campaign_report_html(appended, readiness)

    assert readiness == before
    assert payload["warnings"][0]["kind"] == "<script>alert(1)</script>"
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "&lt;bad&amp;source&gt;" in html
    assert 'id="phase7-100-turn-readiness-report"' in html
    assert "not final certification" in html
    assert appended == appended_again
    assert appended.count('id="phase7-100-turn-readiness-report"') == 1
    assert "Campaign Report" in appended
    assert "</main>" in appended


def test_ci_phase7_100_turn_readiness_report_contract_exports_and_provider_free_source():
    from app.rpg import session
    from app.rpg.session import turn_readiness_report

    readiness = session.assert_phase7_100_turn_readiness_report_ready()
    contract = session.build_100_turn_readiness_report_contract(readiness["payload"])
    source = inspect.getsource(turn_readiness_report).lower()

    assert readiness["ok"] is True
    assert readiness["reason"] == "phase7_100_turn_readiness_report_gate_ready"
    assert readiness["blockers"] == []
    assert contract["source"] == "deterministic_phase7_100_turn_readiness_report_gate"
    assert "Do not claim final 100-turn certification from this advisory report." in contract["forbidden_readiness_claims"]
    assert session.build_100_turn_readiness_report_payload
    assert session.render_100_turn_readiness_report_html
    assert session.append_100_turn_readiness_report_to_campaign_report_html
    assert session.build_100_turn_readiness_report_contract
    assert session.assert_phase7_100_turn_readiness_report_ready
    assert "openai" not in source
    assert "requests." not in source
    assert "httpx" not in source
    assert "subprocess" not in source
