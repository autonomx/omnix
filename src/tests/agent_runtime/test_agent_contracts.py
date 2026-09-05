from __future__ import annotations

import pytest

from app.agent_runtime.contracts import AgentRunSpec, ModelRef, ResourceScope, SuccessCriterion, WorkspaceSpec


def test_run_spec_keeps_model_and_authority_runtime_neutral() -> None:
    spec = AgentRunSpec(
        run_id="run-1",
        task="Fix failing tests",
        model=ModelRef(provider_id="lmstudio", model_id="qwen"),
        capabilities=["workspace.read", "workspace.edit"],
        resource_scopes=[
            ResourceScope(capability="workspace.read", resource_type="repository", resource_id="F:/LLM/omnix")
        ],
        workspace=WorkspaceSpec(root="F:/LLM/omnix"),
        success_criteria=[SuccessCriterion(id="tests", description="Targeted tests pass")],
    )
    assert spec.runtime == "pi"
    assert spec.model.provider_id == "lmstudio"
    assert spec.success_criteria[0].required is True


def test_run_spec_is_immutable_authority_envelope() -> None:
    spec = AgentRunSpec(task="Inspect repo", model=ModelRef(provider_id="test", model_id="model"))
    with pytest.raises(Exception):
        spec.capabilities = ["github.merge_pr"]
