from __future__ import annotations

from pathlib import Path


def test_pi_guard_enforces_scope_and_durable_budget_before_tools() -> None:
    source = (
        Path(__file__).parents[2]
        / "app"
        / "agent_runtime"
        / "pi_guard_extension.ts"
    ).read_text(encoding="utf-8")
    assert "OMNIX_AGENT_ALLOWED_PATHS" in source
    assert "OMNIX_AGENT_FORBIDDEN_PATHS" in source
    assert "budget/tool" in source
    assert "environmentExpansion" in source
    assert "pathAllowed" in source
