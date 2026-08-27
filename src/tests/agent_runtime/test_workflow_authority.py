from __future__ import annotations

import pytest

from app.agent_runtime.workflow_runtime import PostgresWorkflowRuntime, WorkflowRuntimeError
from app.agent_runtime.workflows import WorkflowDefinition, WorkflowStepDefinition


def test_mutating_capability_retry_is_fail_closed() -> None:
    step = WorkflowStepDefinition(
        id="write",
        capability_id="home.set_state",
        retry_limit=3,
    )
    assert PostgresWorkflowRuntime._step_retry_safe(step) is False
    assert PostgresWorkflowRuntime._step_requires_approval(step) is True


def test_read_capability_can_be_retried_without_widening_authority() -> None:
    step = WorkflowStepDefinition(
        id="read",
        capability_id="home.get_state",
        retry_limit=3,
    )
    assert PostgresWorkflowRuntime._step_retry_safe(step) is True
    assert PostgresWorkflowRuntime._step_requires_approval(step) is False


def test_workflow_rejects_worker_zone_capability() -> None:
    definition = WorkflowDefinition(
        id="bad-worker",
        name="Bad worker",
        steps=[WorkflowStepDefinition(id="read", capability_id="workspace.read")],
    )
    with pytest.raises(WorkflowRuntimeError):
        PostgresWorkflowRuntime._validate_definition_capabilities(definition)
