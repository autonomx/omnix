from __future__ import annotations

import pytest

from app.agent_runtime.contracts import AgentRunSpec, ModelRef, ResourceScope, WorkspaceSpec
from app.agent_runtime.evidence import EvidenceCompilationError
from app.agent_runtime.profiles import list_agent_profiles
from app.agent_runtime.service import AgentRunService


def test_every_profile_with_local_capabilities_requires_explicit_workspace() -> None:
    for profile in list_agent_profiles():
        if profile.capabilities:
            assert profile.requires_workspace, profile.id


def test_non_workspace_profile_keeps_workspace_unset() -> None:
    spec = AgentRunSpec(
        run_id="run-research",
        task="research",
        profile="research",
        model=ModelRef(provider_id="test", model_id="model"),
        workspace=None,
    )

    issued = AgentRunService._prepare_workspace(spec)

    assert issued.workspace is None



def test_service_boundary_rejects_external_authority_outside_profile_ceiling() -> None:
    spec = AgentRunSpec(
        run_id="run-research-escalation",
        task="Explain TCP",
        profile="research",
        model=ModelRef(provider_id="test", model_id="model"),
        external_capabilities=["gmail.send_email"],
    )
    with pytest.raises(EvidenceCompilationError) as caught:
        AgentRunService._validate_run_spec_authority(spec)
    assert caught.value.code == "run_spec_exceeds_profile_ceiling"


def test_service_boundary_rejects_workspace_for_non_workspace_profile() -> None:
    spec = AgentRunSpec(
        run_id="run-research-workspace",
        task="Explain TCP",
        profile="research",
        model=ModelRef(provider_id="test", model_id="model"),
        workspace=WorkspaceSpec(root="/tmp/not-authorized"),
    )
    with pytest.raises(EvidenceCompilationError) as caught:
        AgentRunService._validate_run_spec_authority(spec)
    assert caught.value.code == "workspace_outside_profile_ceiling"


def test_service_boundary_rejects_scope_for_unissued_capability() -> None:
    spec = AgentRunSpec(
        run_id="run-coding-scope",
        task="Inspect code",
        profile="coding",
        model=ModelRef(provider_id="test", model_id="model"),
        capabilities=["workspace.read"],
        workspace=WorkspaceSpec(root="/tmp/workspace"),
        resource_scopes=[
            ResourceScope(
                capability="github.read_repo",
                resource_type="repository",
                resource_id="autonomx/omnix",
            )
        ],
    )
    with pytest.raises(EvidenceCompilationError) as caught:
        AgentRunService._validate_run_spec_authority(spec)
    assert caught.value.code == "resource_scope_outside_run_authority"
