from __future__ import annotations

"""Paired scheduling refinements for AI Shadow v2.

A catalyst fingerprint change is an event trigger for both treatment and control,
and only an *effective* armed state may create an armed-trigger recheck.
"""

from contextvars import ContextVar

from . import strategy_ai_shadow_v2_monitor as monitor
from . import strategy_ai_shadow_v2_roadmap_policy as roadmap
from .strategy_repository import StrategyEvent

_CURRENT_CATALYST_FINGERPRINTS: ContextVar[dict[str, str]] = ContextVar(
    "ai_shadow_v2_current_catalyst_fingerprints",
    default={},
)
_INSTALLED = False
_ORIGINAL_RUN_ARM = None
_ORIGINAL_DUE_REASONS = None


def _effective_armed_trigger_satisfied(
    previous: StrategyEvent | None,
    *,
    structure: monitor.MarketStructureSnapshot,
) -> bool:
    if previous is None or previous.payload.get("effective_state") != "armed":
        return False
    decision = previous.payload.get("decision")
    if not isinstance(decision, dict):
        return False
    try:
        trigger = monitor.StructuredAlphaTrigger.model_validate(decision.get("trigger"))
    except Exception:
        return False
    prior = None
    feature = previous.payload.get("feature_snapshot")
    if isinstance(feature, dict) and isinstance(feature.get("market_structure"), dict):
        try:
            prior = monitor.MarketStructureSnapshot.model_validate(feature["market_structure"])
        except Exception:
            prior = None
    return monitor.trigger_satisfied(
        trigger,
        structure=structure,
        previous_structure=prior,
    )


def _previous_catalyst_fingerprint(
    events: list[StrategyEvent],
    instrument_id: str,
) -> str | None:
    previous = monitor._previous_decision(
        events,
        "full_session_catalyst",
        instrument_id,
    )
    if previous is None:
        return None
    feature = previous.payload.get("feature_snapshot")
    if not isinstance(feature, dict):
        return None
    catalyst = feature.get("catalyst_intelligence")
    if not isinstance(catalyst, dict):
        return None
    value = catalyst.get("evidence_fingerprint")
    return str(value) if value else None


def _due_reasons_with_catalyst_event(
    events,
    *,
    arm,
    paired_arm,
    instrument_id,
    at,
    structure,
):
    assert _ORIGINAL_DUE_REASONS is not None
    reasons = list(
        _ORIGINAL_DUE_REASONS(
            events,
            arm=arm,
            paired_arm=paired_arm,
            instrument_id=instrument_id,
            at=at,
            structure=structure,
        )
    )
    if arm.startswith("full_session_") and paired_arm is not None:
        current = _CURRENT_CATALYST_FINGERPRINTS.get().get(instrument_id)
        previous = _previous_catalyst_fingerprint(events, instrument_id)
        if current is not None and previous is not None and current != previous:
            reason = "paired_catalyst_evidence_changed"
            if reason not in reasons:
                reasons.append(reason)
    if reasons and roadmap._pair_has_recent_error(
        events,
        arms=tuple(value for value in (arm, paired_arm) if value is not None),
        instrument_id=instrument_id,
        at=at,
    ):
        return ()
    return tuple(reasons)


async def _run_arm_with_catalyst_context(
    self,
    *,
    arm,
    rows,
    config,
    repository,
    events,
):
    assert _ORIGINAL_RUN_ARM is not None
    fingerprints: dict[str, str] = {}
    for row in rows:
        candidate = row.get("candidate")
        catalyst = row.get("catalyst")
        if candidate is None or catalyst is None:
            continue
        fingerprint = getattr(catalyst, "evidence_fingerprint", None)
        if fingerprint:
            fingerprints[candidate.instrument_id] = str(fingerprint)
    token = _CURRENT_CATALYST_FINGERPRINTS.set(fingerprints)
    try:
        return await _ORIGINAL_RUN_ARM(
            self,
            arm=arm,
            rows=rows,
            config=config,
            repository=repository,
            events=events,
        )
    finally:
        _CURRENT_CATALYST_FINGERPRINTS.reset(token)


def install_ai_shadow_v2_schedule_policy() -> None:
    global _INSTALLED, _ORIGINAL_RUN_ARM, _ORIGINAL_DUE_REASONS
    if _INSTALLED:
        return
    _ORIGINAL_RUN_ARM = monitor.TradingAIShadowV2Monitor._run_arm
    _ORIGINAL_DUE_REASONS = roadmap._due_reasons
    roadmap._previous_trigger_satisfied = _effective_armed_trigger_satisfied
    roadmap._due_reasons = _due_reasons_with_catalyst_event
    monitor.TradingAIShadowV2Monitor._run_arm = _run_arm_with_catalyst_context
    _INSTALLED = True


__all__ = [
    "install_ai_shadow_v2_schedule_policy",
]
