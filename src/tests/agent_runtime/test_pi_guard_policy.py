from __future__ import annotations

from pathlib import Path


def test_pi_guard_rejects_shell_composition_syntax_structurally() -> None:
    source = (Path(__file__).parents[2] / "app" / "agent_runtime" / "pi_guard_extension.ts").read_text(encoding="utf-8")
    assert "forbiddenShellSyntax" in source
    assert 'normalized.includes("$(")' in source
    assert "Run each allowed command as a separate tool call." in source
    assert "commandRejectionReason" in source
    assert "&&" not in source.split("safeCommandPrefixes", 1)[1].split("];", 1)[0]


def test_pi_guard_narrows_shell_commands_to_issued_local_capabilities() -> None:
    source = (Path(__file__).parents[2] / "app" / "agent_runtime" / "pi_guard_extension.ts").read_text(encoding="utf-8")
    assert "OMNIX_AGENT_LOCAL_CAPABILITIES" in source
    assert 'localCapabilities.has("workspace.command")' in source
    assert 'localCapabilities.has("workspace.test")' in source
    assert 'localCapabilities.has("workspace.git_status")' in source
    assert 'localCapabilities.has("workspace.git_diff")' in source
    assert "issuedCommandPrefixes()" in source
