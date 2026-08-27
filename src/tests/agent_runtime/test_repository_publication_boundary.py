from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.agent_runtime.broker_api import (
    BrokerCapabilityRequest,
    _bind_authoritative_capability_input,
)
from app.agent_runtime.contracts import AgentRunSpec, ModelRef, WorkspaceSpec
from app.assistant_tools.models import AssistantToolRequest
from app.assistant_tools.repo_adapter import (
    FakeRepositoryRuntimeAdapter,
    _github_repository_from_remote,
    run_repository_tool_request,
)


def _coding_snapshot():
    return SimpleNamespace(
        spec=AgentRunSpec(
            run_id="run-1",
            task="Publish prepared change",
            model=ModelRef(provider_id="test", model_id="model"),
            workspace=WorkspaceSpec(
                root="/issued/worktree",
                worktree="/issued/worktree",
                repository="autonomx/omnix",
            ),
            external_capabilities=["github.push"],
        )
    )


def test_publication_actions_are_explicit_capabilities() -> None:
    adapter = FakeRepositoryRuntimeAdapter()
    push = run_repository_tool_request(
        AssistantToolRequest(
            tool_id="github",
            action_id="github.push",
            input={"repository": "autonomx/omnix", "worktree": "/tmp/w", "branch": "agent/test"},
        ),
        adapter,
    )
    assert push.error is None
    assert push.state_changed

    ci = run_repository_tool_request(
        AssistantToolRequest(
            tool_id="github",
            action_id="github.inspect_ci",
            input={"repository": "autonomx/omnix", "ref": "abc"},
        ),
        adapter,
    )
    assert ci.error is None
    assert ci.state_changed is False


def test_broker_binds_push_to_issued_worktree_and_origin() -> None:
    request = BrokerCapabilityRequest(
        input={"repository": "autonomx/omnix", "branch": "agent/test"},
        proposal_id="push-1",
    )
    bound = _bind_authoritative_capability_input(
        _coding_snapshot(),
        "github.push",
        request,
    )
    assert bound.input["worktree"] == "/issued/worktree"
    assert bound.input["remote"] == "origin"
    assert bound.input["branch"] == "agent/test"


@pytest.mark.parametrize(
    ("field", "value", "detail"),
    [
        ("worktree", "/other/repo", "agent_push_worktree_is_omnix_managed"),
        ("remote", "evil", "agent_push_remote_is_omnix_managed"),
    ],
)
def test_model_cannot_override_push_authority(field: str, value: str, detail: str) -> None:
    request = BrokerCapabilityRequest(
        input={
            "repository": "autonomx/omnix",
            "branch": "agent/test",
            field: value,
        }
    )
    with pytest.raises(HTTPException) as caught:
        _bind_authoritative_capability_input(
            _coding_snapshot(),
            "github.push",
            request,
        )
    assert caught.value.status_code == 403
    assert caught.value.detail == detail


@pytest.mark.parametrize(
    "remote",
    [
        "https://github.com/autonomx/omnix.git",
        "git@github.com:autonomx/omnix.git",
        "ssh://git@github.com/autonomx/omnix.git",
    ],
)
def test_github_remote_parser_binds_repository_identity(remote: str) -> None:
    assert _github_repository_from_remote(remote) == ("autonomx", "omnix")


def test_non_github_remote_is_rejected() -> None:
    with pytest.raises(ValueError):
        _github_repository_from_remote("https://example.com/autonomx/omnix.git")
