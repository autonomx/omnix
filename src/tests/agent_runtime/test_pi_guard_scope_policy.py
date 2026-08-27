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


def test_pi_guard_checks_option_embedded_paths_before_command_execution() -> None:
    source = (
        Path(__file__).parents[2]
        / "app"
        / "agent_runtime"
        / "pi_guard_extension.ts"
    ).read_text(encoding="utf-8")
    assert 'const equalsIndex = token.indexOf("=");' in source
    assert 'if (token.startsWith("-")) {' in source
    assert "if (equalsIndex < 0) continue;" in source
    assert "token = token.slice(equalsIndex + 1);" in source
