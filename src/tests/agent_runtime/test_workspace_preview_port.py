"""Workspace previews find the run's workspace through AGENT_RUN_WORKSPACES (ADR-0016)."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.platform.assistant_tools import browser_adapter
from app.platform.assistant_tools.contracts import AGENT_RUN_WORKSPACES
from app.platform.assistant_tools.models import AssistantToolRequest
from app.runtime.ports import PortBinding, PortBindings, install_port_bindings, installed_port_bindings


@pytest.fixture
def bindings():
    previous = installed_port_bindings()
    yield lambda items: install_port_bindings(PortBindings.build(items))
    install_port_bindings(previous)


def _request() -> AssistantToolRequest:
    return AssistantToolRequest(
        tool_id="browser", action_id="browser.preview_workspace", session_id="s", proposal_id="agent:run-1:call",
    )


def test_preview_uses_the_run_workspace_and_launcher_the_agent_runtime_supplies(tmp_path, monkeypatch, bindings):
    package = tmp_path / "web"
    package.mkdir()
    (package / "package.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(browser_adapter, "_preview_package_path", lambda: "web")
    launcher = object()

    class Workspaces:
        def preview(self, run_id):
            assert run_id == "run-1"
            return SimpleNamespace(worktree=str(tmp_path), root=str(tmp_path)), launcher

    bindings([PortBinding(AGENT_RUN_WORKSPACES, Workspaces(), owner="agent-runtime")])
    run_id, root, chosen = browser_adapter._workspace_for_preview(_request())
    assert (run_id, root, chosen) == ("run-1", tmp_path.resolve(), launcher)


def test_preview_is_unavailable_without_the_agent_runtime(bindings):
    bindings([])
    with pytest.raises(ValueError, match="issued Agent workspace"):
        browser_adapter._workspace_for_preview(_request())
