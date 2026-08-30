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



def test_workspace_provenance_excludes_preexisting_dirty_paths(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    authority = WorkspaceAuthority(repo)
    assert authority.run_command(["git", "init"]).returncode == 0
    assert authority.run_command(["git", "config", "user.email", "test@example.com"]).returncode == 0
    assert authority.run_command(["git", "config", "user.name", "Test User"]).returncode == 0
    (repo / "clean.txt").write_text("clean\n", encoding="utf-8")
    (repo / "dirty.txt").write_text("base\n", encoding="utf-8")
    assert authority.run_command(["git", "add", "clean.txt", "dirty.txt"]).returncode == 0
    assert authority.run_command(["git", "commit", "-m", "base"]).returncode == 0

    (repo / "dirty.txt").write_text("preexisting\n", encoding="utf-8")
    baseline = authority.provenance_snapshot()
    assert baseline["dirty_paths"] == ["dirty.txt"]
    assert authority.run_owned_paths(baseline["dirty_paths"]) == []
    assert authority.git_diff([]) == ""

    (repo / "clean.txt").write_text("agent change\n", encoding="utf-8")
    assert authority.run_owned_paths(baseline["dirty_paths"]) == ["clean.txt"]
    scoped = authority.git_diff(["clean.txt"])
    assert "clean.txt" in scoped
    assert "dirty.txt" not in scoped
    assert authority.baseline_conflicts(baseline["dirty_digests"]) == []

    (repo / "dirty.txt").write_text("agent touched baseline dirty file\n", encoding="utf-8")
    assert authority.baseline_conflicts(baseline["dirty_digests"]) == ["dirty.txt"]


def test_workspace_scoped_diff_includes_new_untracked_file(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    authority = WorkspaceAuthority(repo)
    assert authority.run_command(["git", "init"]).returncode == 0
    (repo / "new.txt").write_text("new content\n", encoding="utf-8")

    diff = authority.git_diff(["new.txt"])

    assert "diff --git a/new.txt b/new.txt" in diff
    assert "+new content" in diff
