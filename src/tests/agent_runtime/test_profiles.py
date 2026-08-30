from __future__ import annotations
import pytest
from app.agent_runtime.profiles import get_agent_profile, resolve_profile_capabilities, select_agent_profile_id

def test_house_profile_is_an_external_authority_ceiling_not_an_automatic_grant() -> None:
    profile = get_agent_profile("house")
    local, external = resolve_profile_capabilities(profile)
    assert local == []
    assert external == []
    _, issued = resolve_profile_capabilities(
        profile,
        requested_external=["home.get_state", "home.set_state"],
    )
    assert issued == ["home.get_state", "home.set_state"]

def test_trading_research_profile_has_no_order_authority() -> None:
    profile = get_agent_profile("trading-research")
    _, external = resolve_profile_capabilities(profile)
    assert not any("order" in capability or "trade" in capability for capability in external)

def test_profile_can_be_narrowed_but_not_widened() -> None:
    profile = get_agent_profile("coding")
    local, _ = resolve_profile_capabilities(profile, requested=["workspace.read"])
    assert local == ["workspace.read"]
    with pytest.raises(ValueError):
        resolve_profile_capabilities(profile, requested=["github.merge_pr"])


def test_coding_profile_keeps_publication_off_by_default_but_allows_explicit_request() -> None:
    profile = get_agent_profile("coding")
    _, default_external = resolve_profile_capabilities(profile)
    assert default_external == []

    _, issued = resolve_profile_capabilities(
        profile,
        requested_external=["github.push", "github.create_pr", "github.inspect_ci"],
    )
    assert issued == ["github.push", "github.create_pr", "github.inspect_ci"]

    with pytest.raises(ValueError):
        resolve_profile_capabilities(
            profile,
            requested_external=["gmail.send_email"],
        )



def test_coding_task_authority_is_minimized_for_read_only_and_execution_tasks() -> None:
    from app.agent_runtime.contracts import EvidenceDecision
    from app.agent_runtime.evidence import compile_task_authority

    profile = get_agent_profile("coding")
    read_only = compile_task_authority(
        profile,
        "Explain the router implementation",
        EvidenceDecision(),
    )
    assert "workspace.read" in read_only.required_local
    assert "workspace.edit" not in read_only.required_local
    assert "workspace.command" not in read_only.required_local

    diagnostic = compile_task_authority(
        profile,
        "Diagnose the failing tests without changing code",
        EvidenceDecision(),
    )
    assert "workspace.command" in diagnostic.required_local
    assert "workspace.test" in diagnostic.required_local
    assert "workspace.edit" not in diagnostic.required_local

    mutating = compile_task_authority(
        profile,
        "Fix the failing tests",
        EvidenceDecision(),
    )
    assert "workspace.edit" in mutating.required_local
    assert "workspace.test" in mutating.required_local


def test_ui_light_mode_theme_outranks_generic_home_light_keyword() -> None:
    prompt = "aurora light mode still doesn't look good. can you fix it. applies to all styles."
    assert select_agent_profile_id(prompt) == "coding"


def test_physical_light_request_still_selects_house_profile() -> None:
    assert select_agent_profile_id("fix the bedroom light; it won't turn on") == "house"
