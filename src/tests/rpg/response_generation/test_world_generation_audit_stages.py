from __future__ import annotations

from app.rpg.worlds.generation_audit_stages import (
    pre_repair_audit_report,
    two_stage_audit_report,
)


def _row(*, visibility: str = "public") -> dict:
    return {
        "topic_id": "setting_rules",
        "candidate": {
            "topic_id": "setting_rules",
            "documents": [
                {
                    "document_id": "lore:rules",
                    "topic_id": "setting_rules",
                    "title": "Setting Rules",
                    "full_text": "These setting rules are detailed enough to support deterministic audit coverage.",
                    "summary_500": "Detailed setting rules for deterministic audit coverage.",
                    "summary_120": "Detailed setting rules for audit coverage.",
                    "entities": [],
                    "visibility": visibility,
                }
            ],
            "provenance": {"generator": "deterministic_world_forge_v1"},
        },
    }


def test_pre_repair_audit_preserves_raw_findings() -> None:
    report = pre_repair_audit_report([_row(visibility="broadcast")])

    assert report["stage"] == "pre_repair"
    assert report["passed"] is False
    assert any(issue["code"] == "invalid_visibility" for issue in report["issues"])


def test_repair_delta_records_resolved_raw_finding() -> None:
    report = two_stage_audit_report(
        [_row(visibility="broadcast")],
        {"passed": True, "issues": [], "patches": [], "checks": {}},
    )

    delta = report["repair_delta"]
    assert report["passed"] is True
    assert delta["resolved_count"] >= 1
    assert any(issue["code"] == "invalid_visibility" for issue in delta["resolved"])
    assert delta["introduced"] == []


def test_repair_delta_exposes_new_post_repair_regression() -> None:
    report = two_stage_audit_report(
        [_row()],
        {
            "passed": False,
            "issues": [
                {
                    "code": "post_repair_regression",
                    "item_id": "lore:rules",
                    "severity": "error",
                    "message": "A regression appeared after repair.",
                }
            ],
        },
    )

    delta = report["repair_delta"]
    assert report["passed"] is False
    assert delta["introduced_count"] == 1
    assert delta["introduced"][0]["code"] == "post_repair_regression"
