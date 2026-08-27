from __future__ import annotations
import pytest
from app.agent_runtime.profiles import get_agent_profile, resolve_profile_capabilities

def test_house_profile_has_external_home_authority_without_workspace_tools() -> None:
    profile = get_agent_profile("house")
    local, external = resolve_profile_capabilities(profile)
    assert local == []
    assert "home.get_state" in external and "home.set_state" in external

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
