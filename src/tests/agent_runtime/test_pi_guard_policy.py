from __future__ import annotations

from pathlib import Path


def test_pi_guard_rejects_shell_composition_syntax_structurally() -> None:
    source = (Path(__file__).parents[2] / "app" / "agent_runtime" / "pi_guard_extension.ts").read_text(encoding="utf-8")
    assert "forbiddenShellSyntax" in source
    assert 'normalized.includes("$(")' in source
    assert "&&" not in source.split("safeCommandPrefixes", 1)[1].split("];", 1)[0]
