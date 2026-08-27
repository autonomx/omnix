from __future__ import annotations

from pathlib import Path


def test_docker_isolation_preserves_only_explicit_non_agent_environment() -> None:
    source = (
        Path(__file__).parents[2]
        / "app"
        / "agent_runtime"
        / "isolation.py"
    ).read_text(encoding="utf-8")
    assert "spec.execution.allowed_environment_keys" in source
    assert 'key.startswith("OMNIX_AGENT_") or key in explicit' in source
