from __future__ import annotations

import json
from pathlib import Path


_FRAGMENT = (
    Path(__file__).resolve().parent
    / "autoplay_llm_campaign_parts"
    / "zz_bundle_p_1000_turn_readiness_dashboard.pyfrag"
)


def _load_bundle_p_namespace():
    namespace = {"__name__": "_bundle_p_1000_turn_readiness_dashboard_test"}
    exec(compile(_FRAGMENT.read_text(encoding="utf-8"), str(_FRAGMENT), "exec"), namespace, namespace)
    return namespace


def _aggregator_payload(preflight=True, live=True):
    return {
        "format_version": "bundle_o_1000_turn_readiness_aggregator_summary_v1",
        "source": "bundle_o_1000_turn_readiness_aggregator",
        "ok": preflight,
        "ready_for_1000_turn_preflight": preflight,
        "ready_for_live_1000_turn_run": live,
        "required_gate_count": 3,
        "passing_required_gate_count": 3 if preflight else 2,
        "missing_required_gates": [] if preflight else ["content_depth"],
        "failing_required_gates": [] if preflight else ["memory_state_compression"],
        "recommended_next_step": "run_1000_turn_preflight" if preflight else "fix_required_readiness_gates_before_1000_turn_preflight",
        "gate_statuses": [
            {"name": "content_depth", "category": "content", "ok": preflight, "advisory_failure_count": 0 if preflight else 1},
            {"name": "memory_state_compression", "category": "bounded_state", "ok": preflight, "advisory_failure_count": 0 if preflight else 1},
            {"name": "story_arc_end_state_v2", "category": "campaign", "ok": True, "advisory_failure_count": 0},
        ],
        "category_rollup": {
            "content": {"gate_count": 1, "pass_count": 1 if preflight else 0, "fail_count": 0 if preflight else 1},
            "bounded_state": {"gate_count": 1, "pass_count": 1 if preflight else 0, "fail_count": 0 if preflight else 1},
            "campaign": {"gate_count": 1, "pass_count": 1, "fail_count": 0},
        },
    }


def test_bundle_p_dashboard_summary_reports_live_ready_state():
    namespace = _load_bundle_p_namespace()
    dashboard = namespace["_bundle_p_build_dashboard_summary"](_aggregator_payload(preflight=True, live=True))

    assert dashboard["format_version"] == "bundle_p_1000_turn_readiness_dashboard_summary_v1"
    assert dashboard["source"] == "bundle_p_1000_turn_readiness_dashboard"
    assert dashboard["ok"] is True
    assert dashboard["status_label"] == "Live Ready"
    assert dashboard["status_class"] == "pass"
    assert dashboard["ready_for_1000_turn_preflight"] is True
    assert dashboard["ready_for_live_1000_turn_run"] is True
    assert dashboard["completion_percent"] == 100
    assert dashboard["missing_required_gate_count"] == 0
    assert dashboard["failing_required_gate_count"] == 0
    assert dashboard["recommended_next_step"] == "run_1000_turn_preflight"


def test_bundle_p_dashboard_summary_reports_not_ready_state():
    namespace = _load_bundle_p_namespace()
    dashboard = namespace["_bundle_p_build_dashboard_summary"](_aggregator_payload(preflight=False, live=False))

    assert dashboard["ok"] is False
    assert dashboard["status_label"] == "Not Ready"
    assert dashboard["status_class"] == "fail"
    assert dashboard["completion_percent"] == 66
    assert dashboard["missing_required_gate_count"] == 1
    assert dashboard["failing_required_gate_count"] == 1
    assert dashboard["missing_required_gates"] == ["content_depth"]
    assert dashboard["failing_required_gates"] == ["memory_state_compression"]


def test_bundle_p_writes_dashboard_summary_when_aggregator_is_exported(tmp_path):
    namespace = _load_bundle_p_namespace()
    original_write_text = namespace["_BUNDLE_P_ORIGINAL_PATH_WRITE_TEXT"]
    try:
        (tmp_path / "one-thousand-turn-readiness-aggregator-summary.json").write_text(
            json.dumps(_aggregator_payload(preflight=True, live=False)),
            encoding="utf-8",
        )

        dashboard_path = tmp_path / "one-thousand-turn-readiness-dashboard-summary.json"
        assert dashboard_path.exists()
        dashboard = json.loads(dashboard_path.read_text(encoding="utf-8"))
        assert dashboard["ok"] is True
        assert dashboard["status_label"] == "Preflight Ready"
        assert dashboard["status_class"] == "warn"
        assert dashboard["completion_percent"] == 100
    finally:
        Path.write_text = original_write_text


def test_bundle_p_injects_dashboard_report_section_with_collapsed_raw_json(tmp_path):
    namespace = _load_bundle_p_namespace()
    original_write_text = namespace["_BUNDLE_P_ORIGINAL_PATH_WRITE_TEXT"]
    try:
        (tmp_path / "one-thousand-turn-readiness-aggregator-summary.json").write_text(
            json.dumps(_aggregator_payload(preflight=True, live=True)),
            encoding="utf-8",
        )
        report_path = tmp_path / "autoplay-campaign-report.html"
        report_path.write_text(
            "<html><body><h1>Autoplay Campaign Report</h1><main><p>Body</p></main></body></html>",
            encoding="utf-8",
        )
        rendered = report_path.read_text(encoding="utf-8")

        assert 'id="bundle-p-1000-turn-readiness-dashboard"' in rendered
        assert "1000-Turn Readiness Dashboard" in rendered
        assert "Progress: 3/3 required gates passing (100%)." in rendered
        assert "content_depth" in rendered
        assert "Category Rollup" in rendered
        assert '<details class="bundle-p-raw-details">' in rendered
        raw_start = rendered.index('<details class="bundle-p-raw-details">')
        raw_open = rendered[raw_start : rendered.index(">", raw_start) + 1]
        assert " open" not in raw_open
        assert "<p>Body</p>" in rendered
    finally:
        Path.write_text = original_write_text
