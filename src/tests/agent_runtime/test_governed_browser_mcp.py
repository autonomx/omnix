from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from app.agent_runtime.capabilities import default_capability_registry
from app.agent_runtime.coding_external_authority import (
    coding_external_capabilities_for_task,
    task_requires_browser_authority,
)
from app.agent_runtime.mcp_policy import (
    configured_mcp_capability_ids,
    load_mcp_policy,
)
from app.agent_runtime.profiles import get_agent_profile, profile_external_ceiling
from app.assistant_tools import browser_adapter, mcp_adapter
from app.assistant_tools.models import AssistantToolRequest
from app.assistant_tools.validation import is_valid_action_id


def _write_policy(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "servers": [
                    {
                        "name": "docs",
                        "transport": "http",
                        "url": "https://mcp.example.test/mcp",
                        "enabled": True,
                        "tools": [
                            {
                                "name": "search-docs",
                                "capability_id": "mcp.docs.search_docs",
                                "description": "Search configured documentation.",
                                "effect": "read",
                                "risk": "low",
                                "approval_policy": "allow_automatic",
                            },
                            {
                                "name": "publish-doc",
                                "capability_id": "mcp.docs.publish_doc",
                                "description": "Publish a documentation update.",
                                "effect": "mutate",
                                "risk": "high",
                                "approval_policy": "always_ask",
                            },
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def test_browser_registry_surface_excludes_arbitrary_eval() -> None:
    registry = default_capability_registry()
    ids = {row.id for row in registry.all()}
    assert "browser.open" in ids
    assert "browser.snapshot" in ids
    assert "browser.screenshot" in ids
    assert "browser.evaluate" not in ids
    assert "browser.eval" not in ids


def test_browser_authority_is_coding_only_and_task_scoped() -> None:
    coding = profile_external_ceiling(get_agent_profile("coding"))
    reviewer = profile_external_ceiling(get_agent_profile("coding-reviewer"))
    assert "browser.open" in coding
    assert "browser.open" not in reviewer

    assert task_requires_browser_authority("Fix the React modal and verify the UI")
    assert "browser.open" in coding_external_capabilities_for_task(
        "Fix the React modal and verify the UI"
    )
    assert not task_requires_browser_authority("Refactor the Python repository layer")
    assert "browser.open" not in coding_external_capabilities_for_task(
        "Refactor the Python repository layer"
    )
    assert not task_requires_browser_authority(
        "Fix the frontend CSS but do not use the browser"
    )


def test_browser_open_is_origin_scoped_and_uses_agent_browser_safeguards(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OMNIX_AGENT_BROWSER_ALLOWED_DOMAINS", raising=False)
    request = AssistantToolRequest(
        tool_id="browser",
        action_id="browser.open",
        session_id="session-123",
        input={"url": "http://127.0.0.1:5173/quiz"},
    )
    argv, metadata = browser_adapter._command_for(request)
    assert metadata["url"] == "http://127.0.0.1:5173/quiz"
    assert "--allowed-domains" in argv
    assert "--content-boundaries" in argv
    assert "--no-webmcp" in argv
    assert "--session" in argv

    rejected = AssistantToolRequest(
        tool_id="browser",
        action_id="browser.open",
        session_id="session-123",
        input={"url": "https://example.com/"},
    )
    with pytest.raises(ValueError, match="outside"):
        browser_adapter._command_for(rejected)


def test_browser_adapter_executes_argv_without_shell(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(browser_adapter, "browser_available", lambda: True)

    def fake_run(argv: list[str]) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout='{"ok":true}', stderr="")

    monkeypatch.setattr(browser_adapter, "_run", fake_run)
    result = browser_adapter.run_browser_tool_request(
        AssistantToolRequest(
            tool_id="browser",
            action_id="browser.snapshot",
            session_id="run-a",
        )
    )
    assert result.error is None
    assert calls and calls[0][-2:] == ["snapshot", "--json"]
    assert "--no-webmcp" in calls[0]


def test_mcp_policy_is_explicit_dynamic_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = tmp_path / "policy.json"
    _write_policy(policy)
    monkeypatch.setenv("OMNIX_AGENT_MCP_POLICY_PATH", str(policy))

    assert configured_mcp_capability_ids() == (
        "mcp.docs.search_docs",
        "mcp.docs.publish_doc",
    )
    assert is_valid_action_id("mcp.docs.search_docs")
    assert not is_valid_action_id("mcp.docs.search-docs")

    registry = default_capability_registry()
    read_cap = registry.get("mcp.docs.search_docs")
    write_cap = registry.get("mcp.docs.publish_doc")
    assert read_cap is not None and read_cap.effect == "read"
    assert write_cap is not None and write_cap.effect == "mutate"
    assert write_cap.approval_policy == "always_ask"

    coding = profile_external_ceiling(get_agent_profile("coding"))
    reviewer = profile_external_ceiling(get_agent_profile("coding-reviewer"))
    assert "mcp.docs.search_docs" in coding
    assert "mcp.docs.search_docs" not in reviewer
    assert "mcp.docs.search_docs" in coding_external_capabilities_for_task(
        "Use the docs MCP server to look up the API before implementing this"
    )
    assert "mcp.docs.search_docs" not in coding_external_capabilities_for_task(
        "Refactor the parser without external tools"
    )


def test_invalid_mcp_policy_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = tmp_path / "policy.json"
    policy.write_text(
        '{"version":1,"servers":[{"name":"BAD-NAME","transport":"http","url":"https://example.test","tools":[]}]}',
        encoding="utf-8",
    )
    monkeypatch.setenv("OMNIX_AGENT_MCP_POLICY_PATH", str(policy))
    assert load_mcp_policy().servers == ()
    assert configured_mcp_capability_ids() == ()


def test_mcporter_call_uses_only_isolated_policy_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = tmp_path / "policy.json"
    _write_policy(policy)
    monkeypatch.setenv("OMNIX_AGENT_MCP_POLICY_PATH", str(policy))
    monkeypatch.setattr(mcp_adapter, "mcporter_available", lambda: True)
    observed: dict[str, object] = {}

    def fake_run(
        argv: list[str], *, cwd: str, env: dict[str, str]
    ) -> subprocess.CompletedProcess[str]:
        observed["argv"] = list(argv)
        observed["cwd"] = cwd
        config_index = argv.index("--config") + 1
        config = Path(argv[config_index])
        payload = json.loads(config.read_text(encoding="utf-8"))
        observed["config"] = payload
        return subprocess.CompletedProcess(
            argv,
            0,
            stdout='{"content":[{"type":"text","text":"ok"}]}',
            stderr="",
        )

    monkeypatch.setattr(mcp_adapter, "_run", fake_run)
    result = mcp_adapter.run_mcp_tool_request(
        AssistantToolRequest(
            tool_id="mcp",
            action_id="mcp.docs.search_docs",
            session_id="run-mcp",
            input={"query": "typed clients"},
        )
    )
    assert result.error is None
    argv = observed["argv"]
    assert isinstance(argv, list)
    assert "--config" in argv and "--root" in argv and "--no-oauth" in argv
    assert "docs.search-docs" in argv
    config = observed["config"]
    assert isinstance(config, dict)
    assert set(config["mcpServers"]) == {"docs"}

    blocked = mcp_adapter.run_mcp_tool_request(
        AssistantToolRequest(
            tool_id="mcp",
            action_id="mcp.evil.delete_everything",
            input={},
        )
    )
    assert blocked.error == "mcp_capability_not_configured"
