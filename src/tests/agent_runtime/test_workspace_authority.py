from __future__ import annotations

from pathlib import Path

import pytest

from app.agent_runtime.workspace import (
    WorkspaceAuthority,
    WorkspacePolicyError,
    _workspace_process_environment,
)


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


def test_workspace_process_environment_preserves_windows_expansion_roots_without_secrets(monkeypatch) -> None:
    monkeypatch.setenv("PATH", "tool-path")
    monkeypatch.setenv("SYSTEMROOT", r"C:\Windows")
    monkeypatch.delenv("WINDIR", raising=False)
    monkeypatch.delenv("SYSTEMDRIVE", raising=False)
    monkeypatch.setenv("PROGRAMDATA", r"C:\ProgramData")
    monkeypatch.setenv("TEMP", r"C:\Temp")
    monkeypatch.setenv("OMNIX_TEST_SECRET", "must-not-leak")

    environment = _workspace_process_environment()

    assert environment["PATH"] == "tool-path"
    assert environment["SYSTEMROOT"] == r"C:\Windows"
    assert environment["WINDIR"] == r"C:\Windows"
    assert environment["SYSTEMDRIVE"] == "C:"
    assert environment["PROGRAMDATA"] == r"C:\ProgramData"
    assert environment["TEMP"] == r"C:\Temp"
    assert "OMNIX_TEST_SECRET" not in environment


def test_workspace_process_environment_keeps_explicit_overrides(monkeypatch) -> None:
    monkeypatch.setenv("SYSTEMROOT", r"C:\Windows")
    environment = _workspace_process_environment({"TEST_FLAG": "1", "SYSTEMDRIVE": "D:"})
    assert environment["TEST_FLAG"] == "1"
    assert environment["SYSTEMDRIVE"] == "D:"


def test_workspace_process_environment_expands_programdata_systemdrive_token(monkeypatch) -> None:
    monkeypatch.setenv("SYSTEMROOT", r"C:\Windows")
    monkeypatch.setenv("SYSTEMDRIVE", "C:")
    monkeypatch.setenv("PROGRAMDATA", r"%SystemDrive%\ProgramData")

    environment = _workspace_process_environment()

    assert environment["PROGRAMDATA"] == r"C:\ProgramData"


def test_workspace_process_environment_repairs_unresolved_windows_folder_values(monkeypatch) -> None:
    monkeypatch.setenv("SYSTEMROOT", r"C:\Windows")
    monkeypatch.setenv("SYSTEMDRIVE", "%SystemDrive%")
    monkeypatch.setenv("PROGRAMDATA", r"%SystemDrive%\ProgramData")
    monkeypatch.setenv("USERPROFILE", r"C:\Users\runner")
    monkeypatch.setenv("LOCALAPPDATA", r"%USERPROFILE%\AppData\Local")
    monkeypatch.setenv("TEMP", r"%LOCALAPPDATA%\Temp")
    monkeypatch.setenv("TMP", r"%UNKNOWN_ROOT%\Temp")

    environment = _workspace_process_environment()

    assert environment["SYSTEMDRIVE"] == "C:"
    assert environment["PROGRAMDATA"] == r"C:\ProgramData"
    assert environment["LOCALAPPDATA"] == r"C:\Users\runner\AppData\Local"
    assert environment["TEMP"] == r"C:\Users\runner\AppData\Local\Temp"
    assert environment["TMP"] == r"C:\Users\runner\AppData\Local\Temp"
    assert all("%" not in environment[key] for key in ("SYSTEMDRIVE", "PROGRAMDATA", "TEMP", "TMP"))


def test_workspace_quarantines_only_known_literal_systemdrive_cache(tmp_path: Path, monkeypatch) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    authority = WorkspaceAuthority(repository)
    assert authority.run_command(["git", "init"]).returncode == 0
    assert authority.run_command(["git", "config", "user.email", "test@example.com"]).returncode == 0
    assert authority.run_command(["git", "config", "user.name", "Test User"]).returncode == 0
    web = repository / "src" / "apps" / "web"
    web.mkdir(parents=True)
    (web / "package.json").write_text('{}\n', encoding="utf-8")
    assert authority.run_command(["git", "add", "src/apps/web/package.json"]).returncode == 0
    assert authority.run_command(["git", "commit", "-m", "base"]).returncode == 0

    contamination = web / "%SystemDrive%"
    cache = contamination / "ProgramData" / "Microsoft" / "Windows" / "Caches"
    cache.mkdir(parents=True)
    (cache / "cversions.2.db").write_bytes(b"cache")
    quarantine_root = tmp_path / "quarantine-root"
    quarantine_root.mkdir()
    monkeypatch.setattr("app.agent_runtime.workspace.tempfile.gettempdir", lambda: str(quarantine_root))

    records = authority.quarantine_generated_windows_cache_contamination()

    assert len(records) == 1
    assert records[0]["path"] == "src/apps/web/%SystemDrive%/"
    assert not contamination.exists()
    assert (Path(records[0]["quarantine_path"]) / "ProgramData" / "Microsoft" / "Windows" / "Caches" / "cversions.2.db").is_file()
    assert authority.git_status_paths() == []


def test_workspace_does_not_quarantine_ambiguous_literal_systemdrive_directory(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    authority = WorkspaceAuthority(repository)
    assert authority.run_command(["git", "init"]).returncode == 0
    web = repository / "src" / "apps" / "web"
    web.mkdir(parents=True)
    (web / "package.json").write_text('{}\n', encoding="utf-8")
    assert authority.run_command(["git", "add", "src/apps/web/package.json"]).returncode == 0
    contamination = web / "%SystemDrive%"
    cache = contamination / "ProgramData" / "Microsoft" / "Windows" / "Caches"
    cache.mkdir(parents=True)
    (contamination / "possible-source.txt").write_text("keep\n", encoding="utf-8")

    assert authority.quarantine_generated_windows_cache_contamination() == []
    assert contamination.is_dir()


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
