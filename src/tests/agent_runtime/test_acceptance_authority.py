from __future__ import annotations

from pathlib import Path


def test_start_paths_require_diff_only_for_workspace_mutation_authority() -> None:
    root = Path(__file__).parents[2] / "app" / "agent_runtime"
    for name in ("api.py", "chat_bridge.py"):
        source = (root / name).read_text(encoding="utf-8")
        assert 'capability in {"workspace.edit", "workspace.write"}' in source
        assert 'expected_artifacts=["diff"] if profile.requires_workspace' not in source
