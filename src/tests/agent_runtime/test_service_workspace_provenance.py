from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from app.agent_runtime.contracts import AgentRunSpec, ModelRef, WorkspaceSpec
from app.agent_runtime.service import AgentRunService
from app.agent_runtime.workspace import WorkspaceAuthority


class _ArtifactRepository:
    def __init__(self) -> None:
        self.artifacts = []

    def add_artifact(self, artifact):
        self.artifacts.append(artifact)
        return artifact

    def list_artifacts(self, _run_id):
        return list(self.artifacts)


class _BlobStore:
    def put_bytes(self, storage_key: str, content: bytes):
        return {
            "storage_key": storage_key,
            "checksum_sha256": "checksum",
            "storage_provider": "test",
            "byte_size": len(content),
        }


def _git_repo(tmp_path: Path) -> tuple[Path, WorkspaceAuthority]:
    repo = tmp_path / "repo"
    repo.mkdir()
    authority = WorkspaceAuthority(repo)
    assert authority.run_command(["git", "init"]).returncode == 0
    assert authority.run_command(["git", "config", "user.email", "test@example.com"]).returncode == 0
    assert authority.run_command(["git", "config", "user.name", "Test User"]).returncode == 0
    (repo / "clean.py").write_text("value = 1\n", encoding="utf-8")
    (repo / "dirty.py").write_text("value = 10\n", encoding="utf-8")
    assert authority.run_command(["git", "add", "clean.py", "dirty.py"]).returncode == 0
    assert authority.run_command(["git", "commit", "-m", "base"]).returncode == 0
    return repo, authority


def _service() -> AgentRunService:
    service = object.__new__(AgentRunService)
    service.context = SimpleNamespace(workspace_id="workspace-1")
    service.blob_store = _BlobStore()
    return service


def _spec(repo: Path) -> AgentRunSpec:
    return AgentRunSpec(
        run_id="run-provenance",
        task="Implement the requested code change",
        profile="coding",
        model=ModelRef(provider_id="test", model_id="model"),
        workspace=WorkspaceSpec(root=str(repo), repository=str(repo), worktree=str(repo)),
        expected_artifacts=["diff"],
    )


def test_service_diff_contains_only_changes_created_after_run_baseline(tmp_path: Path) -> None:
    repo, _authority = _git_repo(tmp_path)
    (repo / "dirty.py").write_text("preexisting = True\n", encoding="utf-8")
    repository = _ArtifactRepository()
    service = _service()
    spec = _spec(repo)

    service._capture_workspace_baseline(repository, spec)
    (repo / "clean.py").write_text("value = 2\n", encoding="utf-8")
    service._capture_diff(repository, spec)

    baseline = next(item for item in repository.artifacts if item.name == "workspace-baseline.json")
    diff = next(item for item in repository.artifacts if item.name == "workspace.diff")
    assert baseline.metadata["dirty_paths"] == ["dirty.py"]
    assert diff.metadata["modified_paths"] == ["clean.py"]
    assert diff.metadata["baseline_conflicts"] == []
    assert diff.metadata["file_stats"] == [
        {"path": "clean.py", "additions": 1, "deletions": 1}
    ]
    assert diff.metadata["additions"] == 1
    assert diff.metadata["deletions"] == 1
    assert "clean.py" in diff.metadata["preview"]
    assert "dirty.py" not in diff.metadata["preview"]


def test_service_diff_flags_preexisting_dirty_file_touched_during_run(tmp_path: Path) -> None:
    repo, _authority = _git_repo(tmp_path)
    (repo / "dirty.py").write_text("preexisting = True\n", encoding="utf-8")
    repository = _ArtifactRepository()
    service = _service()
    spec = _spec(repo)

    service._capture_workspace_baseline(repository, spec)
    (repo / "clean.py").write_text("value = 2\n", encoding="utf-8")
    (repo / "dirty.py").write_text("agent_overwrote = True\n", encoding="utf-8")
    service._capture_diff(repository, spec)

    diff = next(item for item in repository.artifacts if item.name == "workspace.diff")
    assert diff.metadata["modified_paths"] == ["clean.py"]
    assert diff.metadata["baseline_conflicts"] == ["dirty.py"]
    assert "dirty.py" not in diff.metadata["preview"]
