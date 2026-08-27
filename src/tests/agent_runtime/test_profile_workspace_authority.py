from __future__ import annotations

from app.agent_runtime.contracts import AgentRunSpec, ModelRef
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
