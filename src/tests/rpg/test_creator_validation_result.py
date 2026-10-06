"""A creator validation result survives its own serialization."""
from __future__ import annotations

from app.apps.rpg.creator.validation import ValidationIssue, ValidationResult


def test_a_validation_result_round_trips_through_its_dict() -> None:
    result = ValidationResult(issues=[ValidationIssue(path="/title", code="missing", message="Title is required.")])

    restored = ValidationResult.from_dict(result.to_dict())

    assert restored == result
    assert restored.is_blocking()
