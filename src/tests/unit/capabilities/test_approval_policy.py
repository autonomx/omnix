from __future__ import annotations

from itertools import product

import pytest

from app.capabilities import default_capability_registry
from app.capabilities.approval_policy import (
    APPROVAL_POLICIES,
    default_approval_policy,
    only_tightens,
    requires_approval,
    run_approval_floor,
    strictest,
)
from app.platform.assistant_tools.registry import default_assistant_tools


def test_combining_policies_never_loosens() -> None:
    for policy, floor in product(APPROVAL_POLICIES, (None, *APPROVAL_POLICIES)):
        combined = strictest(policy, floor)
        assert only_tightens(combined, policy)
        if floor is not None:
            assert only_tightens(combined, floor)
    assert strictest("ask_sensitive", None) == "ask_sensitive"
    assert not only_tightens("allow_automatic", "ask_sensitive")
    with pytest.raises(ValueError):
        strictest("permissive")  # type: ignore[arg-type]


def test_destructive_and_deleting_calls_always_ask_unless_disabled() -> None:
    for policy in APPROVAL_POLICIES:
        expected = policy != "disabled"
        assert requires_approval(policy, effect="write", risk="low", destructive=True) is expected
        assert requires_approval(policy, effect="delete", risk="low") is expected
    assert requires_approval("ask_sensitive", effect="read", risk="low") is False
    assert requires_approval("ask_sensitive", effect="read", risk="medium") is True


def test_a_capability_and_its_assistant_action_default_to_the_same_policy() -> None:
    capabilities = {capability.id: capability for capability in default_capability_registry().assistant_projection()}
    for tool in default_assistant_tools():
        for action in tool.actions:
            capability = capabilities[action.id]
            assert default_approval_policy(
                effect=action.category,
                risk=action.risk_level,
                needs_confirmation=action.requires_confirmation,
                destructive=action.is_destructive,
            ) == default_approval_policy(
                effect=capability.effect,
                risk=capability.risk,
                needs_confirmation=capability.requires_confirmation,
                destructive=capability.destructive,
            )


@pytest.mark.parametrize(
    ("run_policy", "expected"),
    [("allow_automatic", "allow_automatic"), ("ask_sensitive", None), ("always_ask", "always_ask"), ("disabled", "disabled")],
)
def test_a_session_scoped_capability_is_exempt_only_from_the_default_run_policy(run_policy, expected) -> None:
    assert run_approval_floor(run_policy, session_scoped=True) == expected
    assert run_approval_floor(run_policy, session_scoped=False) == run_policy


def test_the_governed_browser_alone_declares_itself_session_scoped() -> None:
    from app.capabilities import default_capability_registry

    scoped = {row.id for row in default_capability_registry().all() if row.session_scoped}
    assert scoped and all(capability_id.startswith("browser.") for capability_id in scoped)
    assert {row.id for row in default_capability_registry().all() if row.id.startswith("browser.")} == scoped
