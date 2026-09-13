from __future__ import annotations

"""Version- and observation-isolated metrics for AI Shadow v2."""

from datetime import timezone

from . import strategy_ai_shadow_v2_hardening as hardening
from . import strategy_ai_shadow_v2_roadmap_policy as roadmap
from .strategy_ai_shadow_v2_roadmap_policy import AI_SHADOW_V2_POLICY_VERSION
from .strategy_repository import StrategyEvent

_INSTALLED = False
_ORIGINAL_EPISODE_METRICS = hardening._episode_metrics
_ORIGINAL_LIFT_METRICS = hardening._lift_metrics
_ORIGINAL_DECISION_OUTCOME_METRICS = roadmap._decision_outcome_metrics


def _policy_events(events: list[StrategyEvent]) -> list[StrategyEvent]:
    return [
        event
        for event in events
        if event.event_type != "ai_v2_opportunity_episode"
        or event.payload.get("policy_version") == AI_SHADOW_V2_POLICY_VERSION
    ]


def _decision_key(event: StrategyEvent) -> tuple[str, str]:
    return (
        event.instrument_id,
        event.observed_at.astimezone(timezone.utc).isoformat(),
    )


def _decision_events(events: list[StrategyEvent], arm: str) -> list[StrategyEvent]:
    result: list[StrategyEvent] = []
    for event in events:
        if event.event_type != "ai_v2_decision" or event.payload.get("arm") != arm:
            continue
        feature = event.payload.get("feature_snapshot")
        if not isinstance(feature, dict):
            continue
        if feature.get("experiment_policy_version") != AI_SHADOW_V2_POLICY_VERSION:
            continue
        result.append(event)
    return result


def _paired_arm(arm: str) -> str | None:
    return {
        "morning_control": "morning_catalyst",
        "morning_catalyst": "morning_control",
        "full_session_control": "full_session_catalyst",
        "full_session_catalyst": "full_session_control",
    }.get(arm)


def _shared_decision_keys(
    events: list[StrategyEvent],
    control_arm: str,
    catalyst_arm: str,
) -> set[tuple[str, str]]:
    control = {_decision_key(event) for event in _decision_events(events, control_arm)}
    catalyst = {_decision_key(event) for event in _decision_events(events, catalyst_arm)}
    return control & catalyst


def _same_decision_schedule(
    events: list[StrategyEvent],
    control_arm: str,
    catalyst_arm: str,
) -> bool:
    control = {_decision_key(event) for event in _decision_events(events, control_arm)}
    catalyst = {_decision_key(event) for event in _decision_events(events, catalyst_arm)}
    return control == catalyst


def _episode_metrics_policy(events: list[StrategyEvent], arm: str) -> dict[str, object]:
    return _ORIGINAL_EPISODE_METRICS(_policy_events(events), arm)


def _decision_outcome_metrics_policy(
    events: list[StrategyEvent],
    arm: str,
) -> dict[str, object]:
    paired_arm = _paired_arm(arm)
    if paired_arm is None:
        return _ORIGINAL_DECISION_OUTCOME_METRICS(events, arm)
    shared = _shared_decision_keys(events, arm, paired_arm)
    decision_by_id = {
        event.event_id: event
        for event in _decision_events(events, arm)
        if _decision_key(event) in shared
    }
    filtered: list[StrategyEvent] = []
    for event in events:
        if event.event_type != "ai_v2_decision_outcome":
            filtered.append(event)
            continue
        if event.payload.get("arm") != arm:
            filtered.append(event)
            continue
        decision_event_id = str(event.payload.get("decision_event_id") or "")
        if decision_event_id in decision_by_id:
            filtered.append(event)
    metrics = _ORIGINAL_DECISION_OUTCOME_METRICS(filtered, arm)
    metrics["paired_decision_count"] = len(decision_by_id)
    metrics["paired_only"] = True
    return metrics


def _lift_metrics_policy(events: list[StrategyEvent]) -> dict[str, object]:
    values = _ORIGINAL_LIFT_METRICS(_policy_events(events))
    for name, (control_arm, catalyst_arm) in {
        "morning": ("morning_control", "morning_catalyst"),
        "full_session": ("full_session_control", "full_session_catalyst"),
    }.items():
        pair = values.get(name)
        if not isinstance(pair, dict):
            continue
        valid = _same_decision_schedule(events, control_arm, catalyst_arm)
        pair["comparison_valid"] = valid
        pair["requires_same_decision_schedule"] = True
        if valid:
            continue
        delta = pair.get("catalyst_minus_control")
        if isinstance(delta, dict):
            for key in list(delta):
                delta[key] = None
        pair["comparison_note"] = (
            "Episode metrics are descriptive only because catalyst/control decision observations were not fully paired."
        )
    return values


def install_ai_shadow_v2_metrics_policy() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    hardening._episode_metrics = _episode_metrics_policy
    hardening._lift_metrics = _lift_metrics_policy
    roadmap._decision_outcome_metrics = _decision_outcome_metrics_policy
    _INSTALLED = True


__all__ = [
    "install_ai_shadow_v2_metrics_policy",
]
