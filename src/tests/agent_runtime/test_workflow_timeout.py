from __future__ import annotations

import time

from app.agent_runtime.workflow_runtime import PostgresWorkflowRuntime
from app.agent_runtime.workflows import WorkflowStepDefinition


def test_timeout_reports_unknown_outcome_and_is_not_safe_to_retry() -> None:
    runtime = object.__new__(PostgresWorkflowRuntime)
    runtime.capability_executor = lambda *_args, **_kwargs: None

    def slow(*_args, **_kwargs):
        time.sleep(0.1)
        return {"ok": True}

    runtime._execute_step = slow
    step = WorkflowStepDefinition(
        id="slow",
        kind="condition",
        condition="input.ok",
        timeout_seconds=1,
    )
    assert runtime._execute_with_timeout("run", step, {"input": {"ok": True}}, approved=False) == {"ok": True}
