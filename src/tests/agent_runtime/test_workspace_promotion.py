from __future__ import annotations

from pathlib import Path

import pytest

from app.agent_runtime.contracts import AgentArtifact, AgentRunSnapshot, AgentRunSpec, ModelRef, RunChangeSet, WorkspaceSpec
from app.agent_runtime.service import AgentRunService
from app.agent_runtime.workspace import WorkspaceAuthority
from app.agent_runtime.workspace_promotion import WorkspacePromotionError, promote_change_set
from app.persistence.blob_store import LocalBlobStore


def _repository(tmp_path: Path) -> tuple[Path, WorkspaceAuthority]:
    root = tmp_path / "repository"
    root.mkdir()
    authority = WorkspaceAuthority(root)
    assert authority.run_command(["git", "init"]).returncode == 0
    assert authority.run_command(["git", "config", "user.email", "test@example.com"]).returncode == 0
    assert authority.run_command(["git", "config", "user.name", "Test User"]).returncode == 0
    (root / "target.txt").write_text("before\n", encoding="utf-8")
    assert authority.run_command(["git", "add", "target.txt"]).returncode == 0
    assert authority.run_command(["git", "commit", "-m", "base"]).returncode == 0
    return root, authority


def _change_set(authority: WorkspaceAuthority, patch: str) -> RunChangeSet:
    return RunChangeSet(
        change_set_id="change-set-1",
        run_id="run-1",
        task_revision_id="revision-1",
        baseline_id="baseline-1",
        baseline_head_sha=authority.git_head(),
        candidate_workspace_state_id="candidate-1",
        run_owned_paths=["target.txt"],
        tracked_patch_sha256="tracked-1",
        patch_checksum="patch-1",
        patch_storage_ref="patch-1",
    )


def test_promote_change_set_applies_candidate_and_is_idempotent(tmp_path: Path) -> None:
    repository, authority = _repository(tmp_path)
    source = tmp_path / "source"
    source_authority = WorkspaceAuthority.create_worktree(
        repository,
        source,
        base_ref=authority.git_head(),
    )
    (source / "target.txt").write_text("after\n", encoding="utf-8")
    patch = source_authority.git_diff(["target.txt"])
    change_set = _change_set(authority, patch)
    (repository / "user-note.txt").write_text("keep me\n", encoding="utf-8")

    result = promote_change_set(
        source_root=source,
        target_root=repository,
        change_set=change_set,
        patch=patch,
    )

    assert result.status == "applied"
    assert (repository / "target.txt").read_text(encoding="utf-8") == "after\n"
    assert (repository / "user-note.txt").read_text(encoding="utf-8") == "keep me\n"

    repeated = promote_change_set(
        source_root=source,
        target_root=repository,
        change_set=change_set,
        patch=patch,
    )
    assert repeated.status == "already_applied"


def test_promote_change_set_fails_on_conflicting_dirty_path(tmp_path: Path) -> None:
    repository, authority = _repository(tmp_path)
    source = tmp_path / "source"
    source_authority = WorkspaceAuthority.create_worktree(
        repository,
        source,
        base_ref=authority.git_head(),
    )
    (source / "target.txt").write_text("agent change\n", encoding="utf-8")
    patch = source_authority.git_diff(["target.txt"])
    change_set = _change_set(authority, patch)
    (repository / "target.txt").write_text("user change\n", encoding="utf-8")

    with pytest.raises(WorkspacePromotionError, match="conflicting dirty paths"):
        promote_change_set(
            source_root=source,
            target_root=repository,
            change_set=change_set,
            patch=patch,
        )

    assert (repository / "target.txt").read_text(encoding="utf-8") == "user change\n"


def test_promote_change_set_fails_when_repository_head_advanced(tmp_path: Path) -> None:
    repository, authority = _repository(tmp_path)
    source = tmp_path / "source"
    source_authority = WorkspaceAuthority.create_worktree(
        repository,
        source,
        base_ref=authority.git_head(),
    )
    (source / "target.txt").write_text("agent change\n", encoding="utf-8")
    patch = source_authority.git_diff(["target.txt"])
    change_set = _change_set(authority, patch)
    (repository / "other.txt").write_text("new commit\n", encoding="utf-8")
    assert authority.run_command(["git", "add", "other.txt"]).returncode == 0
    assert authority.run_command(["git", "commit", "-m", "concurrent change"]).returncode == 0

    with pytest.raises(WorkspacePromotionError, match="advanced since the agent started"):
        promote_change_set(
            source_root=source,
            target_root=repository,
            change_set=change_set,
            patch=patch,
        )


def test_service_promotes_the_accepted_run_change_set(tmp_path: Path) -> None:
    repository, authority = _repository(tmp_path)
    source = tmp_path / "source"
    source_authority = WorkspaceAuthority.create_worktree(
        repository,
        source,
        base_ref=authority.git_head(),
    )
    (source / "target.txt").write_text("service promotion\n", encoding="utf-8")
    patch = source_authority.git_diff(["target.txt"])
    change_set = _change_set(authority, patch)
    blob_store = LocalBlobStore(tmp_path / "blobs")
    blob = blob_store.put_bytes("run-1/accepted.patch", patch.encode("utf-8"))
    change_set = change_set.model_copy(update={
        "patch_checksum": blob["checksum_sha256"],
        "patch_storage_ref": blob["storage_key"],
    })
    artifact = AgentArtifact(
        run_id="run-1",
        kind="diff",
        name="run-change-set.patch",
        metadata={"run_change_set": change_set.model_dump(mode="json")},
    )

    class Repository:
        def list_events(self, _run_id, *, after_sequence=0, limit=5000):
            del after_sequence, limit
            return []

        def list_artifacts(self, _run_id):
            return [artifact]

    service = object.__new__(AgentRunService)
    service.blob_store = blob_store
    current = AgentRunSnapshot(
        run_id="run-1",
        spec=AgentRunSpec(
            run_id="run-1",
            task="Update the target",
            profile="coding",
            model=ModelRef(provider_id="test", model_id="model"),
            expected_artifacts=["diff"],
            workspace=WorkspaceSpec(
                root=str(source),
                repository=str(repository),
                worktree=str(source),
            ),
        ),
    )

    result = service._promote_accepted_workspace(
        Repository(),
        current,
        task_revision_id="revision-1",
        workspace_state_id="candidate-1",
    )

    assert result is not None
    assert result["status"] == "applied"
    assert (repository / "target.txt").read_text(encoding="utf-8") == "service promotion\n"
