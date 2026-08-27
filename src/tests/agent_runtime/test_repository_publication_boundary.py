from __future__ import annotations

from app.assistant_tools.models import AssistantToolRequest
from app.assistant_tools.repo_adapter import FakeRepositoryRuntimeAdapter, run_repository_tool_request


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
