from __future__ import annotations

from pathlib import Path


def test_agent_api_exposes_pending_approval_list() -> None:
    source = (Path(__file__).parents[2] / "app" / "agent_runtime" / "api.py").read_text(encoding="utf-8")
    assert '/{run_id}/approvals' in source
    assert "list_agent_approvals" in source


def test_broker_exposes_exact_workspace_command_permission_flow() -> None:
    source = (Path(__file__).parents[2] / "app" / "agent_runtime" / "broker_api.py").read_text(encoding="utf-8")
    assert '"/{run_id}/command-authorization"' in source
    assert "approval_required" in source
    assert '"permission": "exact_command"' in source


def test_repository_preserves_batch_claim_contract() -> None:
    source = (Path(__file__).parents[2] / "app" / "agent_runtime" / "repository.py").read_text(encoding="utf-8")
    assert "def claim_commands(" in source
    assert "status = 'consumed'" in source
