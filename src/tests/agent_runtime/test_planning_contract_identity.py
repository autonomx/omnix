from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.agent_runtime.planning_contracts import (
    ImplementationPlanSubmission,
    PlanImpactDisposition,
    PlanItem,
    PlanValidationIntent,
    RequirementPlanCoverage,
)


def test_plan_submission_rejects_duplicate_plan_item_ids() -> None:
    with pytest.raises(ValidationError, match="duplicate plan item id"):
        ImplementationPlanSubmission(
            changes=[
                PlanItem(id="change", intent="first"),
                PlanItem(id="change", intent="second"),
            ]
        )


def test_plan_submission_rejects_duplicate_validation_ids() -> None:
    with pytest.raises(ValidationError, match="duplicate validation id"):
        ImplementationPlanSubmission(
            validations=[
                PlanValidationIntent(id="validate", kind="test"),
                PlanValidationIntent(id="validate", kind="repository_invariant"),
            ]
        )


def test_plan_submission_rejects_duplicate_requirement_coverage_ids() -> None:
    with pytest.raises(ValidationError, match="duplicate requirement coverage id"):
        ImplementationPlanSubmission(
            requirement_coverage=[
                RequirementPlanCoverage(requirement_id="R1"),
                RequirementPlanCoverage(requirement_id="R1"),
            ]
        )


def test_plan_submission_rejects_duplicate_impact_candidate_ids() -> None:
    with pytest.raises(ValidationError, match="duplicate impact candidate id"):
        ImplementationPlanSubmission(
            impacts=[
                PlanImpactDisposition(candidate_id="C1", disposition="modify"),
                PlanImpactDisposition(candidate_id="C1", disposition="verify"),
            ]
        )
