"""What an approval policy is, how policies order, and what each one requires.

Every layer that names, defaults, combines or applies an approval policy asks here:
the capability registry and its assistant-tool projection, MCP operator policy, the
capability grant's floor, an agent run's requested policy and the broker's run floor.

Policies order from loosest to strictest (``APPROVAL_POLICIES``). Combining policies
only ever tightens: a floor, a run policy or a requested policy can raise what a
capability's own policy demands, never lower it (approval never expands authority).
The module is pure: no I/O, no configuration reads.
"""
from __future__ import annotations

from typing import Literal, TypeGuard, get_args

ApprovalPolicy = Literal["allow_automatic", "ask_sensitive", "always_ask", "disabled"]
APPROVAL_POLICIES: tuple[ApprovalPolicy, ...] = get_args(ApprovalPolicy)
"""Loosest first; ``disabled`` forbids the call outright."""

_STRENGTH = {policy: rank for rank, policy in enumerate(APPROVAL_POLICIES)}

# Effects that change state. A capability declares ``create``/``mutate``; its
# assistant-tool projection calls both ``write``.
_STATE_CHANGING_EFFECTS = frozenset({"create", "mutate", "write", "delete", "execute"})

def is_approval_policy(value: object) -> TypeGuard[ApprovalPolicy]:
    return value in _STRENGTH


def approval_strength(policy: ApprovalPolicy) -> int:
    try:
        return _STRENGTH[policy]
    except KeyError:
        raise ValueError(f"unknown approval policy {policy!r}") from None


def strictest(*policies: ApprovalPolicy | None) -> ApprovalPolicy:
    """The strictest of the given policies; ``None`` (no floor) is skipped."""
    named = [policy for policy in policies if policy is not None]
    if not named:
        raise ValueError("strictest() needs at least one policy")
    return max(named, key=approval_strength)


def only_tightens(requested: ApprovalPolicy, ceiling: ApprovalPolicy) -> bool:
    """Whether ``requested`` is at least as strict as the ``ceiling`` it replaces."""
    return approval_strength(requested) >= approval_strength(ceiling)


def default_approval_policy(
    *,
    effect: str,
    risk: str,
    needs_confirmation: bool = False,
    destructive: bool = False,
) -> ApprovalPolicy:
    """The policy a capability gets when its declaration names none."""
    if destructive or effect == "delete" or needs_confirmation or risk == "high":
        return "always_ask"
    if effect in _STATE_CHANGING_EFFECTS or risk == "medium":
        return "ask_sensitive"
    return "allow_automatic"


def requires_approval(
    policy: ApprovalPolicy,
    *,
    effect: str,
    risk: str,
    needs_confirmation: bool = False,
    destructive: bool = False,
) -> bool:
    """Whether a call under ``policy`` waits for a principal's approval.

    ``disabled`` is not a question of approval: callers block it before asking.
    A destructive or deleting call always asks under every other policy.
    """
    if policy == "disabled":
        return False
    if policy == "always_ask" or destructive or effect == "delete":
        return True
    if policy == "ask_sensitive":
        return effect != "read" or risk != "low" or needs_confirmation
    return False


def run_approval_floor(run_policy: ApprovalPolicy, *, session_scoped: bool) -> ApprovalPolicy | None:
    """The floor an agent run's policy puts under one of its capability calls.

    ``None`` means the capability's own policy decides alone: a capability that runs
    in a task-scoped session adapter (``Capability.session_scoped``, the governed
    browser) under the default ``ask_sensitive`` run policy, so a validation click is
    not a wait. An ``always_ask`` or ``disabled`` run still applies to it. The floor
    is combined with ``strictest``, so it can only tighten.
    """
    approval_strength(run_policy)
    if run_policy == "ask_sensitive" and session_scoped:
        return None
    return run_policy


__all__ = [
    "APPROVAL_POLICIES",
    "ApprovalPolicy",
    "approval_strength",
    "default_approval_policy",
    "is_approval_policy",
    "only_tightens",
    "requires_approval",
    "run_approval_floor",
    "strictest",
]
