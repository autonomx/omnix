from __future__ import annotations

from app.assist_core.plan_step_item import normalize_plan_step_item


def test_plan_step_item_normalizes_fields_and_requires_review() -> None:
    assert normalize_plan_step_item(
        {
            "id": "step-1",
            "title": "Inspect proposal",
            "description": "Read before applying anything.",
            "status": "ready",
        }
    ) == {
        "id": "step-1",
        "title": "Inspect proposal",
        "description": "Read before applying anything.",
        "status": "ready",
        "reviewRequired": True,
    }


def test_plan_step_item_defaults_invalid_values_safely() -> None:
    assert normalize_plan_step_item({"status": "unknown"}) == {
        "id": "step",
        "title": "Review step",
        "description": "Review before use.",
        "status": "pending",
        "reviewRequired": True,
    }
