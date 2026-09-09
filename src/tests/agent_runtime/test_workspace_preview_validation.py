from __future__ import annotations

from pathlib import Path
import subprocess
from unittest.mock import Mock

import pytest

from app.assistant_tools import browser_adapter
from app.assistant_tools.models import AssistantToolRequest


def _completed(argv: list[str], *, stdout: str = "", returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(argv, returncode, stdout=stdout, stderr="")


def _request(action_id: str, input_payload: dict[str, object]) -> AssistantToolRequest:
    return AssistantToolRequest(
        tool_id="browser",
        action_id=action_id,
        session_id="chat:test",
        proposal_id="agent:run-preview-test:tool-call",
        input=input_payload,
    )


@pytest.fixture(autouse=True)
def _use_agent_browser_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OMNIX_AGENT_BROWSER_BACKEND", "agent-browser")


def test_windows_browser_environment_uses_fixed_gpu_compatibility_args(monkeypatch) -> None:
    monkeypatch.setattr(browser_adapter.os, "name", "nt")
    monkeypatch.setenv("AGENT_BROWSER_ARGS", "--user-data-dir=C:\\unsafe-profile")

    environment = browser_adapter._minimal_environment()

    assert environment["AGENT_BROWSER_ARGS"] == "--in-process-gpu,--disable-gpu"


def test_windows_browser_backend_prefers_playwright_when_available(monkeypatch) -> None:
    monkeypatch.delenv("OMNIX_AGENT_BROWSER_BACKEND", raising=False)
    monkeypatch.setattr(browser_adapter.os, "name", "nt")
    monkeypatch.setattr(browser_adapter, "_playwright_available", lambda: True)

    assert browser_adapter._browser_backend() == "playwright"


def test_playwright_cleanup_command_overrides_original_action() -> None:
    request = _request("browser.assert_text_contains", {"selector": "body", "expected": "done"})

    close_request = browser_adapter._playwright_request_for_command(
        request,
        ["agent-browser", "assert", "close"],
    )

    assert close_request.action_id == "browser.close"
    assert close_request.input == {}


def test_browser_open_workspace_preview_uses_managed_exact_worktree_url(monkeypatch) -> None:
    url = "http://127.0.0.1:43123/chatbot"
    start = Mock(
        return_value=(
            url,
            {
                "workspace_preview": True,
                "workspace_preview_url": "http://127.0.0.1:43123",
                "workspace_preview_port": 43123,
                "workspace_preview_path": "/chatbot",
            },
        )
    )
    calls: list[list[str]] = []

    def fake_run(argv: list[str], *, timeout_seconds: int | None = None):
        calls.append(list(argv))
        return _completed(argv)

    monkeypatch.setattr(browser_adapter, "browser_available", lambda: True)
    monkeypatch.setattr(browser_adapter, "_start_workspace_preview", start)
    monkeypatch.setattr(browser_adapter, "_run", fake_run)

    result = browser_adapter.run_browser_tool_request(
        _request(
            "browser.open",
            {"workspace_preview": True, "path": "/chatbot"},
        )
    )

    assert result.error is None
    assert result.output["workspace_preview"] is True
    assert result.output["url"] == url
    assert calls and calls[0][-2:] == ["open", url]
    start.assert_called_once()


def test_agent_browser_session_is_scoped_to_the_agent_run() -> None:
    first, _ = browser_adapter._command_for(
        _request("browser.snapshot", {})
    )
    second_request = AssistantToolRequest(
        tool_id="browser",
        action_id="browser.snapshot",
        session_id="chat:test",
        proposal_id="agent:other-run:tool-call",
    )
    second, _ = browser_adapter._command_for(second_request)

    first_session = first[first.index("--session") + 1]
    second_session = second[second.index("--session") + 1]
    assert first_session != second_session


def test_failed_workspace_preview_open_retries_with_a_fresh_browser_session(monkeypatch) -> None:
    starts = [
        (
            "http://127.0.0.1:43123/chatbot",
            {
                "workspace_preview": True,
                "workspace_preview_url": "http://127.0.0.1:43123",
                "workspace_preview_port": 43123,
                "workspace_preview_path": "/chatbot",
            },
        ),
        (
            "http://127.0.0.1:43124/chatbot",
            {
                "workspace_preview": True,
                "workspace_preview_url": "http://127.0.0.1:43124",
                "workspace_preview_port": 43124,
                "workspace_preview_path": "/chatbot",
            },
        ),
    ]
    calls: list[tuple[list[str], int | None]] = []

    def fake_run(argv: list[str], *, timeout_seconds: int | None = None):
        calls.append((list(argv), timeout_seconds))
        if argv[-1] == "close":
            return _completed(argv)
        if argv[-2:] == ["open", "http://127.0.0.1:43123/chatbot"]:
            return subprocess.CompletedProcess(argv, 1, stdout="", stderr="CDP response channel closed")
        return _completed(argv)

    monkeypatch.setattr(browser_adapter, "browser_available", lambda: True)
    monkeypatch.setattr(browser_adapter, "_start_workspace_preview", Mock(side_effect=starts))
    monkeypatch.setattr(browser_adapter, "_stop_workspace_preview", Mock(return_value=True))
    monkeypatch.setattr(browser_adapter, "_run", fake_run)

    result = browser_adapter.run_browser_tool_request(
        _request("browser.open", {"workspace_preview": True, "path": "/chatbot"})
    )

    assert result.error is None
    assert result.output["url"] == "http://127.0.0.1:43124/chatbot"
    open_calls = [argv for argv, _timeout in calls if argv[-2] == "open"]
    assert len(open_calls) == 2
    assert open_calls[0][open_calls[0].index("--session") + 1] != open_calls[1][open_calls[1].index("--session") + 1]


def test_failed_workspace_preview_retry_closes_the_retried_browser_session(monkeypatch) -> None:
    starts = [
        (
            "http://127.0.0.1:43125/chatbot",
            {"workspace_preview": True, "workspace_preview_url": "http://127.0.0.1:43125"},
        ),
        (
            "http://127.0.0.1:43126/chatbot",
            {"workspace_preview": True, "workspace_preview_url": "http://127.0.0.1:43126"},
        ),
    ]
    calls: list[list[str]] = []

    def fake_run(argv: list[str], *, timeout_seconds: int | None = None):
        calls.append(list(argv))
        if argv[-1] == "close":
            return _completed(argv)
        return subprocess.CompletedProcess(argv, 1, stdout="", stderr="CDP response channel closed")

    monkeypatch.setattr(browser_adapter, "browser_available", lambda: True)
    monkeypatch.setattr(browser_adapter, "_start_workspace_preview", Mock(side_effect=starts))
    monkeypatch.setattr(browser_adapter, "_stop_workspace_preview", Mock(return_value=True))
    monkeypatch.setattr(browser_adapter, "_run", fake_run)

    result = browser_adapter.run_browser_tool_request(
        _request("browser.open", {"workspace_preview": True, "path": "/chatbot"})
    )

    assert result.error == "browser_command_failed"
    assert sum(argv[-1] == "close" for argv in calls) == 2


def test_passing_browser_assertion_cleans_preview_and_browser_without_separate_capability(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run(argv: list[str], *, timeout_seconds: int | None = None):
        calls.append(list(argv))
        if argv[-1] == "close":
            assert timeout_seconds == 5
            return _completed(argv)
        return _completed(argv, stdout="‹")

    stop = Mock(return_value=True)
    monkeypatch.setattr(browser_adapter, "browser_available", lambda: True)
    monkeypatch.setattr(browser_adapter, "_run", fake_run)
    monkeypatch.setattr(browser_adapter, "_stop_workspace_preview", stop)

    result = browser_adapter.run_browser_tool_request(
        _request(
            "browser.assert_text_not_contains",
            {"selector": ".assistant-side-panel-minimize", "expected": "Minimize"},
        )
    )

    assert result.error is None
    assert result.output["assertion_passed"] is True
    assert result.output["cleanup"] == {
        "workspace_preview_stopped": True,
        "browser_closed": True,
    }
    assert len(calls) == 2
    assert calls[1][-1] == "close"
    stop.assert_called_once()


def test_passing_assertion_without_workspace_preview_does_not_close_browser(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run(argv: list[str], *, timeout_seconds: int | None = None):
        calls.append(list(argv))
        return _completed(argv, stdout="‹")

    stop = Mock(return_value=False)
    monkeypatch.setattr(browser_adapter, "browser_available", lambda: True)
    monkeypatch.setattr(browser_adapter, "_run", fake_run)
    monkeypatch.setattr(browser_adapter, "_stop_workspace_preview", stop)

    result = browser_adapter.run_browser_tool_request(
        _request(
            "browser.assert_text_not_contains",
            {"selector": ".assistant-side-panel-minimize", "expected": "Minimize"},
        )
    )

    assert result.error is None
    assert result.output["assertion_passed"] is True
    assert result.output["cleanup"] == {
        "workspace_preview_stopped": False,
        "browser_closed": False,
    }
    assert len(calls) == 1
    stop.assert_called_once()


def test_failed_browser_assertion_keeps_preview_available_for_repair(monkeypatch) -> None:
    stop = Mock(return_value=True)
    monkeypatch.setattr(browser_adapter, "browser_available", lambda: True)
    monkeypatch.setattr(
        browser_adapter,
        "_run",
        lambda argv, *, timeout_seconds=None: _completed(argv, stdout="Minimize"),
    )
    monkeypatch.setattr(browser_adapter, "_stop_workspace_preview", stop)

    result = browser_adapter.run_browser_tool_request(
        _request(
            "browser.assert_text_not_contains",
            {"selector": ".assistant-side-panel-minimize", "expected": "Minimize"},
        )
    )

    assert result.error == "browser_assertion_failed"
    stop.assert_not_called()


def test_run_id_is_bound_from_broker_execution_identity() -> None:
    request = _request("browser.get_url", {})
    assert browser_adapter._run_id_from_request(request) == "run-preview-test"


def test_pi_guard_rejects_shell_preview_and_prompt_uses_managed_preview() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    guard = (repo_root / "src/app/agent_runtime/pi_guard_extension.ts").read_text(encoding="utf-8")
    runtime = (repo_root / "src/app/agent_runtime/pi_runtime.py").read_text(encoding="utf-8")
    broker_extension = (repo_root / "src/app/agent_runtime/pi_broker_extension.ts").read_text(encoding="utf-8")

    assert "managedPreviewShellCommand" in guard
    assert "Do not launch npm/vite dev or preview servers through shell commands" in guard
    assert "workspace_preview" in runtime
    assert "automatically tears down the workspace preview and browser session" in runtime
    assert "workspace_preview: true" in broker_extension
    assert "usedManagedWorkspacePreview" in broker_extension
    assert "Managed workspace preview cleanup is Omnix-owned" in broker_extension
