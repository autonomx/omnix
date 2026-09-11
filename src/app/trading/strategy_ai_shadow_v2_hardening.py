from __future__ import annotations

"""Correctness hardening for the AI Shadow v2 research experiment.

The v2 experiment deliberately keeps alpha, risk and execution separate.  This
module fixes boundaries that are easy to blur in the monitor itself:

* the morning catalyst arm receives one frozen catalyst prior for the session;
* execution/microstructure state is stripped from every alpha prompt;
* a filled long carries its deterministic invalidation forward as a stop;
* post-close reporting measures catalyst-aware lift against its blind control.

Nothing in this module can create real-money authority.  It only wraps the
research-only v2 monitor and preserves the existing deterministic execution
checks.
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from . import strategy_ai_shadow_v2_monitor as monitor
from .strategy_ai_shadow_v2 import AIShadowV2AlphaDecision, CatalystIntelligenceSnapshot
from .strategy_repository import StrategyEvent

_INSTALLED = False
_ORIGINAL_REFRESH_CATALYST = monitor.TradingAIShadowV2Monitor._refresh_catalyst
_ORIGINAL_RUN_ARM = monitor.TradingAIShadowV2Monitor._run_arm
_ORIGINAL_SUMMARY = monitor.TradingAIShadowV2Monitor._summary


def _morning_snapshot(
    events: list[StrategyEvent],
    instrument_id: str,
) -> CatalystIntelligenceSnapshot | None:
    freezes = [
        event
        for event in events
        if event.event_type == "ai_v2_catalyst_freeze"
        and event.instrument_id == instrument_id
        and isinstance(event.payload.get("snapshot"), dict)
    ]
    if not freezes:
        return None
    earliest = min(freezes, key=lambda event: (event.observed_at, event.event_id))
    try:
        return CatalystIntelligenceSnapshot.model_validate(earliest.payload["snapshot"])
    except Exception:
        return None


def _sanitized_alpha_feature(
    feature: dict[str, object],
    *,
    frozen_catalyst: CatalystIntelligenceSnapshot | None = None,
) -> dict[str, object]:
    """Return an alpha-only feature projection.

    Bid/ask/spread belong to deterministic execution/risk evaluation.  Keeping
    them out of the LLM prevents provider/execution quality from becoming a
    second implicit alpha veto, which was the dominant failure mode in the
    zero-trade session that motivated v2.
    """

    projected = dict(feature)
    projected.pop("market_microstructure", None)
    projected["execution_status_visible"] = False
    if frozen_catalyst is not None:
        projected["catalyst_intelligence"] = frozen_catalyst.model_dump(mode="json")
        projected["alpha_confirmation_hurdle"] = frozen_catalyst.influence.confirmation_hurdle
        projected["catalyst_snapshot_mode"] = "morning_frozen"
        # This matrix is keyed by the current persistence class in the base
        # monitor.  A later refresh could therefore leak an afternoon class into
        # the morning arm.  The frozen influence already carries any calibrated
        # morning prior, so drop the potentially mismatched matrix here.
        projected.pop("empirical_setup_calibration", None)
    return projected


def _active_stop_price(
    events: list[StrategyEvent],
    *,
    arm: str,
    instrument_id: str,
) -> Decimal | None:
    """Resolve the invalidation attached to the active filled entry."""

    buys = [
        event
        for event in events
        if event.event_type == "ai_v2_fill"
        and event.instrument_id == instrument_id
        and event.payload.get("arm") == arm
        and event.payload.get("side") == "buy"
        and event.state == "filled"
    ]
    if not buys:
        return None
    latest_buy = max(buys, key=lambda event: (event.observed_at, event.event_id))
    entries = [
        event
        for event in events
        if event.event_type == "ai_v2_decision"
        and event.instrument_id == instrument_id
        and event.payload.get("arm") == arm
        and event.payload.get("effective_state") == "enter"
        and event.observed_at <= latest_buy.observed_at
        and isinstance(event.payload.get("geometry"), dict)
    ]
    if not entries:
        return None
    geometry = max(entries, key=lambda event: (event.observed_at, event.event_id)).payload["geometry"]
    if geometry.get("valid") is not True or geometry.get("invalidation_price") is None:
        return None
    try:
        return Decimal(str(geometry["invalidation_price"]))
    except Exception:
        return None


def _stop_was_breached(row: dict[str, object], *, stop: Decimal, entry_time: datetime | None) -> bool:
    bars = row.get("bars")
    if not isinstance(bars, list):
        return False
    for bar in bars:
        if not getattr(bar, "is_final", False) or getattr(bar, "session", None) != "regular":
            continue
        if entry_time is not None and getattr(bar, "end_time", entry_time) < entry_time:
            continue
        low = getattr(bar, "low", None)
        if low is not None and Decimal(str(low)) <= stop:
            return True
    return False


def _episode_metrics(events: list[StrategyEvent], arm: str) -> dict[str, object]:
    rows = [
        event.payload["outcome"]
        for event in events
        if event.event_type == "ai_v2_opportunity_episode"
        and event.payload.get("arm") == arm
        and isinstance(event.payload.get("outcome"), dict)
    ]
    positive = [row for row in rows if row.get("positive_opportunity") is True]
    entered = [row for row in rows if row.get("entered") is True]
    captured = [row for row in positive if row.get("entered") is True]
    false_entries = [row for row in entered if row.get("positive_opportunity") is False]
    labeled = [row for row in rows if row.get("plus_two_r_before_minus_one_r") is not None]
    wins = [row for row in labeled if row.get("plus_two_r_before_minus_one_r") is True]
    peak_r = [Decimal(str(row["peak_r"])) for row in rows if row.get("peak_r") is not None]
    mae = [Decimal(str(row["mae_pct"])) for row in rows if row.get("mae_pct") is not None]
    missed_peak_r = [
        Decimal(str(row["peak_r"]))
        for row in positive
        if row.get("entered") is not True and row.get("peak_r") is not None
    ]

    def ratio(numerator: int, denominator: int) -> Decimal | None:
        return Decimal(numerator) / Decimal(denominator) if denominator else None

    recall = ratio(len(captured), len(positive))
    precision = ratio(len(entered) - len(false_entries), len(entered))
    two_r_rate = ratio(len(wins), len(labeled))
    return {
        "episode_count": len(rows),
        "entered_episode_count": len(entered),
        "good_entry_recall": str(recall) if recall is not None else None,
        "entry_precision": str(precision) if precision is not None else None,
        "two_r_before_minus_one_r_rate": str(two_r_rate) if two_r_rate is not None else None,
        "mean_peak_r": str(sum(peak_r, Decimal("0")) / Decimal(len(peak_r))) if peak_r else None,
        "mean_mae_pct": str(sum(mae, Decimal("0")) / Decimal(len(mae))) if mae else None,
        "missed_positive_mean_peak_r": (
            str(sum(missed_peak_r, Decimal("0")) / Decimal(len(missed_peak_r)))
            if missed_peak_r
            else None
        ),
        "false_entry_count": len(false_entries),
    }


def _metric_delta(catalyst: dict[str, object], control: dict[str, object], field: str) -> str | None:
    left, right = catalyst.get(field), control.get(field)
    if left is None or right is None:
        return None
    try:
        return str(Decimal(str(left)) - Decimal(str(right)))
    except Exception:
        return None


def _lift_metrics(events: list[StrategyEvent]) -> dict[str, object]:
    pairs = {
        "morning": ("morning_control", "morning_catalyst"),
        "full_session": ("full_session_control", "full_session_catalyst"),
    }
    output: dict[str, object] = {}
    for name, (control_arm, catalyst_arm) in pairs.items():
        control = _episode_metrics(events, control_arm)
        catalyst = _episode_metrics(events, catalyst_arm)
        output[name] = {
            "control": control,
            "catalyst": catalyst,
            "catalyst_minus_control": {
                "good_entry_recall": _metric_delta(catalyst, control, "good_entry_recall"),
                "entry_precision": _metric_delta(catalyst, control, "entry_precision"),
                "two_r_before_minus_one_r_rate": _metric_delta(
                    catalyst, control, "two_r_before_minus_one_r_rate"
                ),
                "mean_peak_r": _metric_delta(catalyst, control, "mean_peak_r"),
                "mean_mae_pct": _metric_delta(catalyst, control, "mean_mae_pct"),
                "missed_positive_mean_peak_r": _metric_delta(
                    catalyst, control, "missed_positive_mean_peak_r"
                ),
                "false_entry_count": str(
                    int(catalyst["false_entry_count"]) - int(control["false_entry_count"])
                ),
            },
        }
    return output


async def _refresh_catalyst_hardened(
    self,
    *,
    candidate,
    config,
    strategy_repository,
    research_repository,
    events,
    now,
    history,
):
    snapshot = await _ORIGINAL_REFRESH_CATALYST(
        self,
        candidate=candidate,
        config=config,
        strategy_repository=strategy_repository,
        research_repository=research_repository,
        events=events,
        now=now,
        history=history,
    )
    if _morning_snapshot(events, candidate.instrument_id) is None:
        session_date = now.astimezone(monitor._ET).date().isoformat()
        await self._append(
            strategy_repository,
            config,
            instrument_id=candidate.instrument_id,
            event_type="ai_v2_catalyst_freeze",
            state=snapshot.intraday_persistence_class,
            reason_code="AI_V2_MORNING_CATALYST_FROZEN",
            observed_at=now,
            payload={
                "snapshot": snapshot.model_dump(mode="json"),
                "snapshot_mode": "morning_frozen",
                "session_date": session_date,
                "research_only": True,
                "execution_authority": False,
            },
            identity=(candidate.instrument_id, session_date, "morning-catalyst-freeze"),
        )
    return snapshot


async def _run_arm_hardened(
    self,
    *,
    arm,
    rows,
    config,
    repository,
    events,
):
    prepared: list[dict[str, object]] = []
    for source in rows:
        row = dict(source)
        candidate = row["candidate"]
        instrument_id = candidate.instrument_id
        feature_by_arm = dict(row.get("feature_by_arm") or {})
        feature = dict(feature_by_arm.get(arm) or {})
        frozen = _morning_snapshot(events, instrument_id) if arm == "morning_catalyst" else None
        feature = _sanitized_alpha_feature(feature, frozen_catalyst=frozen)
        if arm == "full_session_catalyst":
            feature["catalyst_snapshot_mode"] = "event_refreshed"
        feature_by_arm[arm] = feature
        row["feature_by_arm"] = feature_by_arm

        position = monitor._position(events, arm, instrument_id)
        stop = _active_stop_price(events, arm=arm, instrument_id=instrument_id)
        if position.is_long and stop is not None and _stop_was_breached(
            row, stop=stop, entry_time=position.entry_time
        ):
            decision = AIShadowV2AlphaDecision(
                instrument_id=instrument_id,
                setup_family="unresolved",
                state="exit",
                quality_score=100,
                extension_risk="high",
                evidence_against=("deterministic invalidation breached",),
                thesis_changed=True,
                thesis="Deterministic risk boundary breached; alpha cannot override the stop.",
            )
            await self._apply_decision(
                arm=arm,
                decision=decision,
                row=row,
                config=config,
                repository=repository,
                events=events,
                trigger_reasons=("deterministic_stop_breached",),
            )
            # A breached deterministic stop owns the state transition.  Do not
            # ask the LLM to reinterpret the same bar, even if execution evidence
            # is temporarily unavailable and the exit must be retried next bar.
            continue
        prepared.append(row)

    if not prepared:
        return None
    return await _ORIGINAL_RUN_ARM(
        self,
        arm=arm,
        rows=prepared,
        config=config,
        repository=repository,
        events=events,
    )


async def _summary_hardened(
    self,
    *,
    config,
    repository,
    events,
    session_date,
    now,
):
    await _ORIGINAL_SUMMARY(
        self,
        config=config,
        repository=repository,
        events=events,
        session_date=session_date,
        now=now,
    )
    if now.astimezone(monitor._ET).time() < monitor.time(16, 0):
        return
    lift = _lift_metrics(events)
    await self._append(
        repository,
        config,
        instrument_id="__universe__",
        event_type="ai_v2_catalyst_lift_summary",
        state="complete",
        reason_code="AI_V2_CATALYST_CONTROL_LIFT",
        observed_at=now,
        payload={
            "version": monitor.AI_SHADOW_V2_VERSION,
            "session_date": session_date.isoformat(),
            "experiment": "identical_market_structure_catalyst_aware_vs_blind_control",
            "metrics": lift,
            "interpretation": (
                "Positive deltas for recall/precision/2R rate and negative deltas for missed opportunity "
                "or false entries favor catalyst awareness. Trade count alone is not a success metric."
            ),
            "research_only": True,
            "execution_authority": False,
        },
        identity=(session_date.isoformat(), monitor._key(lift), "catalyst-lift"),
    )


def install_ai_shadow_v2_hardening() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    monitor._EVENT_TYPES = tuple(dict.fromkeys((
        *monitor._EVENT_TYPES,
        "ai_v2_catalyst_freeze",
        "ai_v2_catalyst_lift_summary",
    )))
    monitor.TradingAIShadowV2Monitor._refresh_catalyst = _refresh_catalyst_hardened
    monitor.TradingAIShadowV2Monitor._run_arm = _run_arm_hardened
    monitor.TradingAIShadowV2Monitor._summary = _summary_hardened
    _INSTALLED = True


__all__ = [
    "install_ai_shadow_v2_hardening",
]
