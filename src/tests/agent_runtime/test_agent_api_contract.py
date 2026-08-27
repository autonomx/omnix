from __future__ import annotations

from app.agent_runtime.api import StartAgentRunRequest
from app.agent_runtime.profiles import (
    get_agent_profile,
    resolve_profile_capabilities,
)


def test_coding_vertical_slice_defaults_have_no_publication_authority() -> None:
    request = StartAgentRunRequest(
        task="Fix test",
        provider_id="lmstudio",
        model_id="test-model",
        repository="F:/LLM/omnix",
    )
    profile = get_agent_profile(request.profile)
    local, external = resolve_profile_capabilities(
        profile,
        requested=request.capabilities,
        requested_external=request.external_capabilities,
    )
    assert "workspace.edit" in local
    assert "workspace.test" in local
    assert not any(value.startswith("github.") for value in external)
