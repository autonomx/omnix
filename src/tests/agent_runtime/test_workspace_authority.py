from __future__ import annotations

from pathlib import Path

import pytest

from app.agent_runtime.workspace import WorkspaceAuthority, WorkspacePolicyError


def test_workspace_authority_blocks_path_escape(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    authority = WorkspaceAuthority(workspace)
    assert authority.resolve_path("file.txt") == workspace / "file.txt"
    with pytest.raises(WorkspacePolicyError):
        authority.resolve_path("../outside.txt")


def test_workspace_command_policy_separates_local_git_from_publication(tmp_path: Path) -> None:
    authority = WorkspaceAuthority(tmp_path)
    with pytest.raises(WorkspacePolicyError):
        authority._validate_command(["git", "push", "origin", "main"])
    assert authority._validate_command(["git", "status", "--short"]) == ["git", "status", "--short"]
    assert authority._validate_command(["python", "-m", "pytest", "-q"]) == ["python", "-m", "pytest", "-q"]
