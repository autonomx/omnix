"""Runtime behaviour follows declared profile attributes, not profile ids (WP-8.2)."""
from __future__ import annotations

import ast
from pathlib import Path

from app.platform.agent_runtime.profiles import (
    get_agent_profile,
    list_agent_profiles,
    profile_external_ceiling,
    profile_produces_diff,
    profile_repository_guidance,
)

RUNTIME = Path(__file__).resolve().parents[2] / "app" / "platform" / "agent_runtime"


def test_the_coding_profiles_declare_their_behaviour() -> None:
    assert {profile.id for profile in list_agent_profiles() if profile.produces_diff} == {"coding"}
    assert {profile.id for profile in list_agent_profiles() if profile.repository_guidance} == {"coding", "coding-reviewer"}
    assert {profile.id for profile in list_agent_profiles() if profile.operator_mcp_tools} == {"coding"}


def test_an_unknown_or_missing_profile_has_no_attributes() -> None:
    # get_agent_profile defaults a missing id to coding; attribute lookups must not.
    for profile_id in (None, "", "unknown", "coding-reviewer"):
        assert not profile_produces_diff(profile_id)
    assert profile_produces_diff("Coding")
    assert not profile_repository_guidance(None)


def test_operator_mcp_tools_join_only_profiles_that_declare_them(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.capabilities.mcp_policy.configured_mcp_capability_ids",
        lambda: {"mcp.fixture.read"},
    )
    assert "mcp.fixture.read" in profile_external_ceiling(get_agent_profile("coding"))
    assert "mcp.fixture.read" not in profile_external_ceiling(get_agent_profile("coding-reviewer"))
    assert "mcp.fixture.read" not in profile_external_ceiling(get_agent_profile("research"))


def test_no_runtime_module_checks_for_the_coding_profile_by_id() -> None:
    # The coding pipeline (diff, quality gates, planning, guidance, MCP tools)
    # follows the attributes above. Other id comparisons are domain routing
    # (research vs trading-research) or identify reviewer children.
    profile_ids = {"coding"}
    offenders = []
    for path in sorted(RUNTIME.glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Compare):
                continue
            for operand in (node.left, *node.comparators):
                values = operand.elts if isinstance(operand, (ast.Set, ast.Tuple, ast.List)) else [operand]
                if any(isinstance(value, ast.Constant) and value.value in profile_ids for value in values):
                    offenders.append(f"{path.name}:{node.lineno}")
    assert offenders == [], "declare a profile attribute in profiles.py instead"
