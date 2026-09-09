from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.agent_runtime import workspace_dependencies
from app.agent_runtime.workspace_dependencies import WorkspaceDependencyError, prepare_project_dependencies


def _node_project(root: Path) -> None:
    (root / "package.json").write_text(
        '{"name":"test-project","devDependencies":{"vitest":"^4.1.0"}}\n',
        encoding="utf-8",
    )
    (root / "package-lock.json").write_text('{"lockfileVersion":3}\n', encoding="utf-8")


def _ready_node_modules(root: Path) -> None:
    node_modules = root / "node_modules"
    node_modules.mkdir()
    (node_modules / "vitest").mkdir()
    (node_modules / "vitest" / "package.json").write_text('{}\n', encoding="utf-8")


def test_project_dependencies_reuse_existing_repository_tree(tmp_path: Path, monkeypatch) -> None:
    repository = tmp_path / "repository"
    worktree = tmp_path / "worktree"
    repository.mkdir()
    worktree.mkdir()
    _node_project(repository)
    _node_project(worktree)
    _ready_node_modules(repository)
    monkeypatch.setattr(workspace_dependencies, "_link_existing_node_modules", lambda *_args: True)
    monkeypatch.setattr(
        workspace_dependencies.subprocess,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("install should not run")),
    )

    assert prepare_project_dependencies(repository=repository, worktree=worktree) == "linked_existing"


def test_workspace_local_node_dependency_is_ready_but_not_root_linkable(tmp_path: Path) -> None:
    root = tmp_path / "repository"
    web = root / "src" / "apps" / "web"
    web.mkdir(parents=True)
    (root / "package.json").write_text(
        '{"name":"root","workspaces":["src/apps/web"]}\n',
        encoding="utf-8",
    )
    (web / "package.json").write_text(
        '{"name":"web","devDependencies":{"@types/node":"^22.12.0"}}\n',
        encoding="utf-8",
    )
    node_modules = root / "node_modules"
    node_modules.mkdir()
    node_types = web / "node_modules" / "@types" / "node"
    node_types.mkdir(parents=True)
    (node_types / "package.json").write_text('{}\n', encoding="utf-8")

    assert workspace_dependencies._node_modules_ready(root, {"@types/node"})
    assert not workspace_dependencies._node_modules_ready(
        root,
        {"@types/node"},
        root_only=True,
    )


def test_project_dependencies_install_missing_tree_with_locked_ci(tmp_path: Path, monkeypatch) -> None:
    repository = tmp_path / "repository"
    worktree = tmp_path / "worktree"
    repository.mkdir()
    worktree.mkdir()
    _node_project(repository)
    _node_project(worktree)
    commands: list[list[str]] = []

    def fake_run(command, **kwargs):
        commands.append(command)
        assert kwargs["cwd"] == worktree
        _ready_node_modules(worktree)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(workspace_dependencies.shutil, "which", lambda _name: "npm.cmd")
    monkeypatch.setattr(workspace_dependencies.subprocess, "run", fake_run)

    assert prepare_project_dependencies(repository=repository, worktree=worktree) == "installed"
    assert commands and commands[0][1:] == [
        "ci",
        "--ignore-scripts",
        "--include=dev",
        "--no-audit",
        "--no-fund",
        "--prefer-offline",
    ]


def test_project_dependencies_use_isolated_worktree_manifest(tmp_path: Path, monkeypatch) -> None:
    repository = tmp_path / "repository"
    worktree = tmp_path / "worktree"
    repository.mkdir()
    worktree.mkdir()
    (repository / "package.json").write_text(
        '{"name":"repository","devDependencies":{"uncommitted-tool":"1.0.0"}}\n',
        encoding="utf-8",
    )
    _node_project(worktree)

    def fake_run(_command, **kwargs):
        assert kwargs["cwd"] == worktree
        _ready_node_modules(worktree)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(workspace_dependencies.shutil, "which", lambda _name: "npm.cmd")
    monkeypatch.setattr(workspace_dependencies.subprocess, "run", fake_run)

    assert prepare_project_dependencies(repository=repository, worktree=worktree) == "installed"


def test_project_dependencies_fail_clearly_when_install_fails(tmp_path: Path, monkeypatch) -> None:
    repository = tmp_path / "repository"
    worktree = tmp_path / "worktree"
    repository.mkdir()
    worktree.mkdir()
    _node_project(repository)
    _node_project(worktree)

    monkeypatch.setattr(workspace_dependencies.shutil, "which", lambda _name: "npm.cmd")
    monkeypatch.setattr(
        workspace_dependencies.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=1, stdout="", stderr="registry unavailable"),
    )

    with pytest.raises(WorkspaceDependencyError, match="Node dependency installation failed.*registry unavailable"):
        prepare_project_dependencies(repository=repository, worktree=worktree)
