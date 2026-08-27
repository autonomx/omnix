from __future__ import annotations

from app.agent_runtime.workflows import WorkflowDefinition, WorkflowStepDefinition


def test_workflow_definition_versions_deterministic_procedure() -> None:
    workflow = WorkflowDefinition(
        id="bedtime",
        version=2,
        name="Bedtime",
        steps=[
            WorkflowStepDefinition(
                id="plug-off",
                capability_id="kasa.turn_off",
                input_template={"target": "$input.target"},
                requires_approval=True,
                retry_limit=1,
            )
        ],
    )
    assert workflow.steps[0].capability_id == "kasa.turn_off"
    assert workflow.steps[0].requires_approval
