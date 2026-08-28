from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from app.agent_runtime.contracts import AgentRunSpec, ModelRef, WorkspaceSpec
from app.agent_runtime.service import AgentRunService


def test_start_paths_require_diff_only_for_workspace_mutation_authority() -> None:
    root = Path(__file__).parents[2] / "app" / "agent_runtime"
    for name in ("api.py", "chat_bridge.py"):
        source = (root / name).read_text(encoding="utf-8")
        assert "task_requires_workspace_mutation" in source
        assert 'expected_artifacts=["diff"] if profile.requires_workspace' not in source


def test_diff_artifact_uses_blob_store_not_machine_local_temp_path(monkeypatch) -> None:
    class FakeAuthority:
        def __init__(self, _root):
            pass

        def git_diff(self) -> str:
            return "diff --git a/a.txt b/a.txt\n+changed\n"

    class FakeBlobStore:
        def __init__(self) -> None:
            self.storage_key = ""
            self.content = b""

        def put_bytes(self, storage_key: str, content: bytes):
            self.storage_key = storage_key
            self.content = content
            return {
                "storage_provider": "fake",
                "storage_key": storage_key,
                "checksum_sha256": "abc123",
                "byte_size": len(content),
                "created": True,
            }

    class FakeRepository:
        def __init__(self) -> None:
            self.artifact = None

        def add_artifact(self, artifact):
            self.artifact = artifact
            return artifact

    monkeypatch.setattr("app.agent_runtime.service.WorkspaceAuthority", FakeAuthority)
    service = object.__new__(AgentRunService)
    service.context = SimpleNamespace(workspace_id="workspace-1")
    service.blob_store = FakeBlobStore()
    repository = FakeRepository()
    spec = AgentRunSpec(
        run_id="run-1",
        task="change file",
        model=ModelRef(provider_id="test", model_id="model"),
        workspace=WorkspaceSpec(root="/issued/workspace", worktree="/issued/workspace"),
    )

    service._capture_diff(repository, spec)

    assert service.blob_store.storage_key.startswith("agent/runs/")
    assert service.blob_store.storage_key.endswith("/workspace.diff")
    assert service.blob_store.content == b"diff --git a/a.txt b/a.txt\n+changed\n"
    assert repository.artifact is not None
    assert repository.artifact.storage_ref == service.blob_store.storage_key
    assert repository.artifact.checksum == "abc123"
    assert repository.artifact.metadata["storage_provider"] == "fake"



def test_workspace_inspection_failure_fails_closed(monkeypatch, tmp_path) -> None:
    from app.agent_runtime.acceptance import evaluate_acceptance
    from app.agent_runtime.contracts import AgentRunSpec, ModelRef, WorkspaceSpec
    from app.agent_runtime.workspace import WorkspaceAuthority

    monkeypatch.setattr(
        WorkspaceAuthority,
        "git_status",
        lambda _self: (_ for _ in ()).throw(RuntimeError("git unavailable")),
    )
    spec = AgentRunSpec(
        task="Inspect code",
        profile="coding",
        model=ModelRef(provider_id="test", model_id="model"),
        capabilities=["workspace.read"],
        workspace=WorkspaceSpec(root=str(tmp_path)),
    )
    result = evaluate_acceptance(spec, events=[], artifacts=[])
    assert result.passed is False
    assert "workspace_inspection_failed" in result.failures
