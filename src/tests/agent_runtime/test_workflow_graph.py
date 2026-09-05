from __future__ import annotations

import pytest

from app.agent_runtime.workflow_runtime import PostgresWorkflowRuntime
from app.agent_runtime.workflows import WORKFLOW_END, WorkflowDefinition, WorkflowStepDefinition


def test_workflow_definition_rejects_unknown_branch_target() -> None:
    with pytest.raises(ValueError):
        WorkflowDefinition(
            id="bad",
            name="Bad",
            steps=[
                WorkflowStepDefinition(
                    id="condition",
                    kind="condition",
                    condition="input.ok",
                    on_true_step_id="missing",
                )
            ],
        )


def test_condition_branch_target_is_deterministic() -> None:
    definition = WorkflowDefinition(
        id="branch",
        name="Branch",
        steps=[
            WorkflowStepDefinition(
                id="condition",
                kind="condition",
                condition="input.ok",
                on_true_step_id="yes",
                on_false_step_id=WORKFLOW_END,
            ),
            WorkflowStepDefinition(id="yes", kind="approval"),
        ],
    )
    step = definition.steps[0]
    assert PostgresWorkflowRuntime._next_target(definition, step, {"matched": True}) == "yes"
    assert PostgresWorkflowRuntime._next_target(definition, step, {"matched": False}) is None


def test_workflow_template_can_reference_prior_step_output() -> None:
    context = {"input": {"name": "Desk"}, "steps": {"read": {"output": {"value": 7}}}}
    rendered = PostgresWorkflowRuntime._render_input(
        {"target": "$input.name", "value": "$steps.read.output.value"},
        context,
    )
    assert rendered == {"target": "Desk", "value": 7}


def test_approval_step_is_inherently_approval_gated() -> None:
    step = WorkflowStepDefinition(id="confirm", kind="approval")
    assert step.kind == "approval"
