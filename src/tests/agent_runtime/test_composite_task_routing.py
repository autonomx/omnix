from __future__ import annotations

import pytest

from app.agent_runtime.profiles import (
    get_agent_profile,
    profile_external_ceiling,
    resolve_profile_capabilities,
)
from app.agent_runtime.router import route_omnix_request


@pytest.mark.parametrize(
    "prompt",
    [
        "Check my calendar and turn off the bedroom light",
        "Read my latest email and check whether the porch light is on",
        "Fix the trading UI and then research NVDA",
        "Research NVDA and then summarize my latest email",
        "Run the bedtime routine and then inspect CI",
        "Check my calendar and research today's top gainers",
        "Turn off the office light and tell me what changed in the repo",
        "Inspect CI and then check my calendar for tomorrow morning",
    ],
)
def test_mixed_domain_tasks_never_partially_direct_execute(prompt: str) -> None:
    decision = route_omnix_request(prompt)
    assert decision.lane == "agent"
    assert decision.hermes_recommended is True
    assert decision.reason == "mixed_intent_task"


@pytest.mark.parametrize(
    "profile_id,forbidden_capability",
    [
        ("coding", "home.set_state"),
        ("coding", "gmail.send_email"),
        ("house", "workspace.edit"),
        ("house", "gmail.read_email"),
        ("personal-assistant", "home.set_state"),
        ("personal-assistant", "workspace.command"),
        ("research", "gmail.send_email"),
        ("research", "home.set_state"),
        ("trading-research", "gmail.read_email"),
        ("trading-research", "home.set_state"),
    ],
)
def test_single_profile_ceiling_cannot_absorb_other_domain_authority(
    profile_id: str,
    forbidden_capability: str,
) -> None:
    profile = get_agent_profile(profile_id)
    assert forbidden_capability not in profile.capabilities
    assert forbidden_capability not in profile_external_ceiling(profile)


@pytest.mark.parametrize(
    "profile_id,requested_external",
    [
        ("coding", ["home.set_state"]),
        ("house", ["gmail.send_email"]),
        ("personal-assistant", ["research.web_search"]),
        ("research", ["calendar.create_event"]),
        ("trading-research", ["gmail.create_draft"]),
    ],
)
def test_profile_compiler_rejects_cross_domain_external_grants(
    profile_id: str,
    requested_external: list[str],
) -> None:
    with pytest.raises(ValueError, match="exceed selected profile"):
        resolve_profile_capabilities(
            get_agent_profile(profile_id),
            requested=[],
            requested_external=requested_external,
        )


def test_trading_research_profile_has_no_broker_mutation_authority() -> None:
    ceiling = profile_external_ceiling(get_agent_profile("trading-research"))
    assert "trading.market_quote" in ceiling
    assert "broker.place_order" not in ceiling
    assert "broker.cancel_order" not in ceiling
    assert "trading.place_order" not in ceiling


def test_house_profile_has_read_and_mutation_only_for_home_domain() -> None:
    ceiling = profile_external_ceiling(get_agent_profile("house"))
    assert {"home.get_state", "home.set_state"} <= ceiling
    assert not ceiling.intersection(
        {"gmail.send_email", "calendar.create_event", "research.web_search"}
    )


def test_personal_assistant_profile_cannot_mutate_workspace() -> None:
    profile = get_agent_profile("personal-assistant")
    assert "workspace.edit" not in profile.capabilities
    assert "workspace.write" not in profile.capabilities
    assert "workspace.command" not in profile.capabilities


def test_composite_task_requires_orchestration_even_when_one_leg_is_direct() -> None:
    decision = route_omnix_request(
        "Turn off the desk light and then check my calendar for conflicts"
    )
    assert decision.lane == "agent"
    assert decision.hermes_recommended is True
    assert decision.capability_id is None


def test_composite_task_does_not_inherit_direct_capability_id() -> None:
    decision = route_omnix_request(
        "Turn on the hallway light and then investigate why CI is red"
    )
    assert decision.lane == "agent"
    assert decision.hermes_recommended is True
    assert decision.capability_id is None
