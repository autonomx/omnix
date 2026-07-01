from __future__ import annotations

from app.assist_core.plan_risk_item import normalize_plan_risk_item


def test_plan_risk_item_normalizes_fields_and_requires_review() -> None:
    assert normalize_plan_risk_item(
        {
            "id": "risk-1",
            "label": "State change",
            "severity": "high",
            "message": "Simulation must validate before use.",
        }
    ) == {
        "id": "risk-1",
        "label": "State change",
        "severity": "high",
        "message": "Simulation must validate before use.",
        "reviewRequired": True,
    }


def test_plan_risk_item_defaults_invalid_values_safely() -> None:
    assert normalize_plan_risk_item({"severity": "unknown"}) == {
        "id": "risk",
        "label": "Review risk",
        "severity": "medium",
        "message": "Review before use.",
        "reviewRequired": True,
    }
