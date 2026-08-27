from __future__ import annotations

from app.agent_runtime.api import StartAgentRunRequest


def test_coding_vertical_slice_defaults_have_no_publication_authority() -> None:
    request = StartAgentRunRequest(
        task="Fix test",
        provider_id="lmstudio",
        model_id="test-model",
        repository="F:/LLM/omnix",
    )
    assert "workspace.edit" in request.capabilities
    assert "workspace.test" in request.capabilities
    assert not any(value.startswith("github.") for value in request.capabilities)
