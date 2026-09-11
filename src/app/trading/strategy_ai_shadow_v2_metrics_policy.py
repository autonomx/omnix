from __future__ import annotations

"""Version-isolated metrics for the AI Shadow v2 experiment."""

from . import strategy_ai_shadow_v2_hardening as hardening
from .strategy_ai_shadow_v2_roadmap_policy import AI_SHADOW_V2_POLICY_VERSION
from .strategy_repository import StrategyEvent

_INSTALLED = False
_ORIGINAL_EPISODE_METRICS = hardening._episode_metrics


def _policy_events(events: list[StrategyEvent]) -> list[StrategyEvent]:
    return [
        event
        for event in events
        if event.event_type != "ai_v2_opportunity_episode"
        or event.payload.get("policy_version") == AI_SHADOW_V2_POLICY_VERSION
    ]


def _episode_metrics_policy(events: list[StrategyEvent], arm: str) -> dict[str, object]:
    return _ORIGINAL_EPISODE_METRICS(_policy_events(events), arm)


def install_ai_shadow_v2_metrics_policy() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    # hardening._lift_metrics resolves _episode_metrics dynamically from its
    # module globals, so replacing this one helper also version-isolates lift.
    hardening._episode_metrics = _episode_metrics_policy
    _INSTALLED = True


__all__ = [
    "install_ai_shadow_v2_metrics_policy",
]
