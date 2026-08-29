from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.agent_runtime import api
from app.agent_runtime.local_workspace import (
    LocalWorkspaceSelectionError,
    local_request_host_allowed,
    local_workspace_repository_root,
    validate_local_workspace_root,
)


def test_validate_local_workspace_root_resolves_existing_directory(tmp_path) -> None:
    assert validate_local_workspace_root(str(tmp_path)) == str(tmp_path.resolve())


def test_validate_local_workspace_root_rejects_file(tmp_path) -> None:
    file_path = tmp_path / "file.txt"
    file_path.write_text("x", encoding="utf-8")
    with pytest.raises(LocalWorkspaceSelectionError, match="not a directory"):
        validate_local_workspace_root(str(file_path))


def test_validate_local_workspace_root_rejects_missing_path(tmp_path) -> None:
    with pytest.raises(LocalWorkspaceSelectionError, match="does not exist"):
        validate_local_workspace_root(str(tmp_path / "missing"))


@pytest.mark.parametrize("host", ["127.0.0.1", "::1", "localhost", "testclient"])
def test_local_workspace_picker_allows_loopback_hosts(host: str) -> None:
    assert local_request_host_allowed(host) is True


@pytest.mark.parametrize("host", ["192.168.1.10", "10.0.0.8", "example.com", None])
def test_local_workspace_picker_rejects_non_loopback_hosts(host: str | None) -> None:
    assert local_request_host_allowed(host) is False


def test_repository_root_detection_is_bounded_to_git_result(monkeypatch, tmp_path) -> None:
    repo = tmp_path / "repo"
    child = repo / "src"
    child.mkdir(parents=True)
    monkeypatch.setattr("app.agent_runtime.local_workspace.shutil.which", lambda name: "git")
    monkeypatch.setattr(
        "app.agent_runtime.local_workspace.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout=str(repo),
            stderr="",
        ),
    )
    assert local_workspace_repository_root(str(child)) == str(repo.resolve())


def test_repository_root_detection_returns_none_for_non_git_folder(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("app.agent_runtime.local_workspace.shutil.which", lambda name: "git")
    monkeypatch.setattr(
        "app.agent_runtime.local_workspace.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=128,
            stdout="",
            stderr="not a repository",
        ),
    )
    assert local_workspace_repository_root(str(tmp_path)) is None


def test_workspace_picker_endpoint_returns_selected_folder(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(api, "pick_local_workspace", lambda: str(tmp_path.resolve()))
    request = SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"))
    response = api.pick_agent_workspace(request)
    assert response.path == str(tmp_path.resolve())
    assert response.name == tmp_path.name
    assert response.cancelled is False


def test_workspace_picker_endpoint_reports_cancel(monkeypatch) -> None:
    monkeypatch.setattr(api, "pick_local_workspace", lambda: None)
    request = SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"))
    response = api.pick_agent_workspace(request)
    assert response.path is None
    assert response.cancelled is True


def test_workspace_picker_endpoint_rejects_remote_client() -> None:
    request = SimpleNamespace(client=SimpleNamespace(host="192.168.1.44"))
    with pytest.raises(HTTPException) as caught:
        api.pick_agent_workspace(request)
    assert caught.value.status_code == 403
