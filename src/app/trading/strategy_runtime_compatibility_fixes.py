from __future__ import annotations

"""Compatibility refinements for the Sep-11 Trading reliability overlays.

The reliability layer intentionally tightens causal market-data semantics. These
refinements keep those protections while preserving existing SHADOW research
contracts that do not grant order authority:

* evidence quality is ``primary_verified`` only when every source is primary;
* legacy/synthetic opportunity outcomes without timestamps remain reportable,
  while explicitly pre-open outcomes are still excluded;
* current-session guards apply only to a live same-day SHADOW universe, not to
  historical/synthetic replay fixtures;
* trend-continuation collection can use the repository's bounded event API when
  ``recent_events`` is unavailable;
* deep-recovery research may evaluate a causal partial current-session prefix,
  but provider failures still normalize to no bars and it remains SHADOW-only;
* the explicit V2 shadow-archive helper performs no archive read for AUTO PAPER
  or operator-attached universes.
"""

from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from zoneinfo import ZoneInfo

from . import strategy_ai_shadow_v2 as ai_v2
from . import strategy_ai_shadow_v2_hardening as v2_hardening
from . import strategy_deep_recovery_monitor as deep_monitor
from . import strategy_monitor
from . import strategy_runtime_reliability_fixes as runtime_fixes
from . import strategy_shadow_data_gap_guard as gap_guard
from . import strategy_shadow_universe as shadow_universe
from . import trading_session_reliability as session_reliability

_ET = ZoneInfo("America/New_York")
_INSTALLED = False
_ORIGINAL_TREND_COLLECTOR = None
_ORIGINAL_SHADOW_ARCHIVE = None
_ORIGINAL_EVALUATE_CANDIDATES = None


def _deterministic_evidence_quality(evidence):
    if not evidence:
        return "unresolved", False, 0
    primary = [item for item in evidence if item.source_type in {"sec", "company_ir"}]
    verified = bool(primary)
    if primary and len(primary) == len(evidence):
        quality = "primary_verified"
    elif primary:
        quality = "mixed"
    else:
        quality = "secondary_only"
    score = round(
        sum(max(0, 5 - int(item.source_authority_tier)) for item in evidence)
        / (len(evidence) * 4)
        * 100
    )
    return quality, verified, min(100, score)


def _outcome_is_valid_compat(row: dict[str, object]) -> bool:
    """Exclude known-invalid timestamps without invalidating legacy metrics.

    Older/synthetic outcome payloads predate ``started_at``. They cannot be
    classified as pre-open lookahead and should remain visible to historical
    calibration. Once a timestamp is present, the current-session constraint is
    strict.
    """

    value = row.get("started_at")
    if value in {None, ""}:
        return True
    try:
        started = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return False
    if started.tzinfo is None or not runtime_fixes._regular_session_reference(started):
        return False
    ended_value = row.get("ended_at")
    if ended_value in {None, ""}:
        return True
    try:
        ended = ended_value if isinstance(ended_value, datetime) else datetime.fromisoformat(str(ended_value))
    except (TypeError, ValueError):
        return False
    return ended.tzinfo is not None and ended.astimezone(_ET).date() == started.astimezone(_ET).date()


def _episode_metrics_compat(events, arm):
    """Compute filtered episode metrics without depending on installer order."""

    rows = []
    excluded = 0
    for event in events:
        if event.event_type != "ai_v2_opportunity_episode":
            continue
        if event.payload.get("arm") != arm:
            continue
        outcome = event.payload.get("outcome") if isinstance(event.payload, dict) else None
        if not isinstance(outcome, dict):
            continue
        if not _outcome_is_valid_compat(outcome):
            excluded += 1
            continue
        rows.append(outcome)

    positive = [row for row in rows if row.get("positive_opportunity") is True]
    entered = [row for row in rows if row.get("entered") is True]
    captured = [row for row in positive if row.get("entered") is True]
    false_entries = [row for row in entered if row.get("positive_opportunity") is False]
    labeled = [
        row for row in rows
        if row.get("plus_two_r_before_minus_one_r") is not None
    ]
    wins = [row for row in labeled if row.get("plus_two_r_before_minus_one_r") is True]
    peak_r = [
        Decimal(str(row["peak_r"]))
        for row in rows
        if row.get("peak_r") is not None
    ]
    mae = [
        Decimal(str(row["mae_pct"]))
        for row in rows
        if row.get("mae_pct") is not None
    ]
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
        "two_r_before_minus_one_r_rate": (
            str(two_r_rate) if two_r_rate is not None else None
        ),
        "mean_peak_r": (
            str(sum(peak_r, Decimal("0")) / Decimal(len(peak_r)))
            if peak_r else None
        ),
        "mean_mae_pct": (
            str(sum(mae, Decimal("0")) / Decimal(len(mae)))
            if mae else None
        ),
        "missed_positive_mean_peak_r": (
            str(sum(missed_peak_r, Decimal("0")) / Decimal(len(missed_peak_r)))
            if missed_peak_r else None
        ),
        "false_entry_count": len(false_entries),
        "data_quality_excluded_episode_count": excluded,
    }


def _lift_metrics_compat(events):
    """Compute catalyst lift through the compatibility-aware episode path."""

    pairs = {
        "morning": ("morning_control", "morning_catalyst"),
        "full_session": ("full_session_control", "full_session_catalyst"),
    }
    output: dict[str, object] = {}
    for name, (control_arm, catalyst_arm) in pairs.items():
        control = _episode_metrics_compat(events, control_arm)
        catalyst = _episode_metrics_compat(events, catalyst_arm)
        output[name] = {
            "control": control,
            "catalyst": catalyst,
            "catalyst_minus_control": {
                "good_entry_recall": v2_hardening._metric_delta(
                    catalyst, control, "good_entry_recall"
                ),
                "entry_precision": v2_hardening._metric_delta(
                    catalyst, control, "entry_precision"
                ),
                "two_r_before_minus_one_r_rate": v2_hardening._metric_delta(
                    catalyst, control, "two_r_before_minus_one_r_rate"
                ),
                "mean_peak_r": v2_hardening._metric_delta(
                    catalyst, control, "mean_peak_r"
                ),
                "mean_mae_pct": v2_hardening._metric_delta(
                    catalyst, control, "mean_mae_pct"
                ),
                "missed_positive_mean_peak_r": v2_hardening._metric_delta(
                    catalyst, control, "missed_positive_mean_peak_r"
                ),
                "false_entry_count": str(
                    int(catalyst["false_entry_count"])
                    - int(control["false_entry_count"])
                ),
            },
        }
    return output


class _BoundedRecentEventsRepository:
    def __init__(self, delegate: Any, *, session_date) -> None:
        self._delegate = delegate
        self._session_date = session_date

    def __getattr__(self, name: str):
        return getattr(self._delegate, name)

    def recent_events(self, strategy_id: str, limit: int = 10_000):
        start_et = datetime.combine(self._session_date, time(0, 0), tzinfo=_ET)
        end_et = start_et + timedelta(days=1)
        return self._delegate.events_by_types_between(
            strategy_id,
            event_types=("trend_continuation_shadow",),
            start_time=start_et.astimezone(timezone.utc),
            end_time=end_et.astimezone(timezone.utc),
            limit=limit,
        )


async def _collect_trend_signal_compat(
    monitor,
    config,
    repository,
    market_service,
    universe,
    *,
    now: datetime,
) -> None:
    assert _ORIGINAL_TREND_COLLECTOR is not None
    active_repository = repository
    if (
        not hasattr(repository, "recent_events")
        and hasattr(repository, "events_by_types_between")
    ):
        active_repository = _BoundedRecentEventsRepository(
            repository,
            session_date=universe.session_date,
        )
    return await _ORIGINAL_TREND_COLLECTOR(
        monitor,
        config,
        active_repository,
        market_service,
        universe,
        now=now,
    )


async def _evaluate_candidates_compat(self, config, repository, market_service, universe):
    """Apply the same-day causal proxy only to the live SHADOW session.

    Historical replay and deterministic fixture universes have their own fixed
    causal clocks. Comparing those archives to wall-clock ``datetime.now()``
    would incorrectly erase their bars and can change replay results.
    """

    assert _ORIGINAL_EVALUATE_CANDIDATES is not None
    now = datetime.now(timezone.utc)
    universe_date = getattr(universe, "session_date", None)
    if (
        getattr(config, "mode", None) == "shadow"
        and universe_date is not None
        and universe_date != now.astimezone(_ET).date()
    ):
        base = runtime_fixes._ORIGINAL_EVALUATE_CANDIDATES
        if base is None:
            raise RuntimeError("strategy_monitor_base_evaluator_not_installed")
        return await base(self, config, repository, market_service, universe)
    return await _ORIGINAL_EVALUATE_CANDIDATES(
        self,
        config,
        repository,
        market_service,
        universe,
    )


class _DeepRecoveryCausalProxy:
    """Current-session proxy that permits incomplete primary research prefixes."""

    def __init__(self, delegate: Any, *, session_date, observed_at: datetime) -> None:
        self._delegate = delegate
        self._inner = runtime_fixes._CurrentShadowSessionProxy(
            delegate,
            session_date=session_date,
            observed_at=observed_at,
        )

    def __getattr__(self, name: str):
        return getattr(self._delegate, name)

    def bars(self, instrument_id, interval, limit=500, binding_id=None, cancellation=None):
        base = gap_guard._ORIGINAL_PROXY_BARS
        if base is None:
            return SimpleNamespace(bars=[], provenance=None)
        try:
            return base(
                self._inner,
                instrument_id,
                interval,
                limit,
                binding_id,
                cancellation,
            )
        except Exception:
            return SimpleNamespace(bars=[], provenance=None)


async def _run_deep_recovery_compat(self, repository, market_service, config, *, now):
    base = runtime_fixes._ORIGINAL_DEEP_RUN_CONFIG
    if base is None:
        raise RuntimeError("deep_recovery_base_run_config_not_installed")
    proxy = _DeepRecoveryCausalProxy(
        market_service,
        session_date=now.astimezone(_ET).date(),
        observed_at=now,
    )
    return await base(self, repository, proxy, config, now=now)


def _resolve_v2_shadow_archive_guarded(config, repository, *, now=None):
    if config.mode != "shadow" or config.active_universe_id is not None:
        return None
    assert _ORIGINAL_SHADOW_ARCHIVE is not None
    return _ORIGINAL_SHADOW_ARCHIVE(config, repository, now=now)


def install_strategy_runtime_compatibility_fixes() -> None:
    global _INSTALLED, _ORIGINAL_TREND_COLLECTOR, _ORIGINAL_SHADOW_ARCHIVE
    global _ORIGINAL_EVALUATE_CANDIDATES
    if _INSTALLED:
        return

    _ORIGINAL_TREND_COLLECTOR = session_reliability._collect_trend_signal
    _ORIGINAL_SHADOW_ARCHIVE = shadow_universe.resolve_v2_shadow_archive
    _ORIGINAL_EVALUATE_CANDIDATES = strategy_monitor.TradingStrategyMonitor._evaluate_candidates

    ai_v2.deterministic_evidence_quality = _deterministic_evidence_quality
    runtime_fixes._outcome_is_valid = _outcome_is_valid_compat
    v2_hardening._episode_metrics = _episode_metrics_compat
    v2_hardening._lift_metrics = _lift_metrics_compat
    session_reliability._collect_trend_signal = _collect_trend_signal_compat
    strategy_monitor.TradingStrategyMonitor._evaluate_candidates = _evaluate_candidates_compat
    deep_monitor.TradingStrategyDeepRecoveryShadowMonitor._run_config = _run_deep_recovery_compat
    shadow_universe.resolve_v2_shadow_archive = _resolve_v2_shadow_archive_guarded

    _INSTALLED = True


__all__ = ["install_strategy_runtime_compatibility_fixes"]
