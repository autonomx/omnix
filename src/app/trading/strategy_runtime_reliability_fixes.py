from __future__ import annotations

"""Runtime correctness fixes recovered from the 2026-09-11 trading session.

This layer is deliberately narrow:

* executable top-of-book freshness follows the quote timestamp, not an older
  last-trade timestamp;
* SHADOW market-data consumers are restricted to the current Eastern session
  and can recover from a primary history exception through the existing Alpaca
  IEX research fallback;
* AI Shadow v2 shares the dedicated trading-research provider lane and circuit
  breaker instead of repeatedly starting doomed Codex calls during an outage;
* pre-open/stale-session opportunity outcomes are rejected and excluded from
  calibration/reporting;
* repeated identical legacy SHADOW data-gap events are emitted as a periodic
  heartbeat instead of once per monitor pass.

AUTO PAPER and live execution authority are not broadened. Genuine stale quotes,
wide spreads, halts, missing books and non-SHADOW data failures still fail closed.
"""

import asyncio
import copy
import threading
import time as monotonic_time
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from zoneinfo import ZoneInfo

from . import ai_shadow_reliability as provider_reliability
from . import strategy_ai_shadow_monitor as legacy_ai_monitor
from . import strategy_ai_shadow_v2_hardening as v2_hardening
from . import strategy_ai_shadow_v2_monitor as v2_monitor
from . import strategy_ai_shadow_v2_roadmap_policy as v2_policy
from . import strategy_deep_recovery_monitor as deep_monitor
from . import strategy_monitor
from .execution import assess_execution_observation, execution_observation_from_quote
from .providers import alpaca_iex
from .providers.errors import ProviderContractError, ProviderDataUnavailableError
from .strategy_ai_shadow_v2 import AIShadowV2Analyzer
from .us_equity_calendar import us_equity_session

_ET = ZoneInfo("America/New_York")
_REGULAR_OPEN = time(9, 30)
_REGULAR_CLOSE = time(16, 0)
_GAP_HEARTBEAT = timedelta(minutes=15)
_INSTALLED = False

_ORIGINAL_V2_RUN_CONFIG = None
_ORIGINAL_LEGACY_RUN_CONFIG = None
_ORIGINAL_DEEP_RUN_CONFIG = None
_ORIGINAL_EVALUATE_CANDIDATES = None
_ORIGINAL_LEGACY_APPEND = None
_ORIGINAL_V2_ASSESS = None
_ORIGINAL_EPISODE_EVALUATOR = None
_ORIGINAL_EPISODE_METRICS = None
_ORIGINAL_HISTORICAL_EPISODES = None
_ORIGINAL_DECISION_OUTCOME_METRICS = None

_GAP_LOCK = threading.RLock()
_GAP_LAST_EMITTED: dict[tuple[str, str, str, str, str], datetime] = {}


def _copy_response_with_bars(response: Any, bars: list[Any]) -> Any:
    """Replace bars without claiming stronger provenance than the source earned."""

    if response is None:
        return SimpleNamespace(bars=bars, provenance=None)
    if hasattr(response, "model_copy"):
        return response.model_copy(update={"bars": bars})
    cloned = copy.copy(response)
    setattr(cloned, "bars", bars)
    return cloned


def _session_bars(values: list[Any], *, session_date, observed_at: datetime) -> list[Any]:
    cutoff = observed_at.astimezone(timezone.utc)
    result = []
    for bar in values:
        start = getattr(bar, "start_time", None)
        end = getattr(bar, "end_time", None)
        if not isinstance(start, datetime) or not isinstance(end, datetime):
            continue
        if not bool(getattr(bar, "is_final", False)):
            continue
        if end.astimezone(timezone.utc) > cutoff:
            continue
        if start.astimezone(_ET).date() != session_date:
            continue
        result.append(bar)
    return sorted(result, key=lambda item: item.start_time)


def _merge_bars(primary: list[Any], fallback: list[Any]) -> list[Any]:
    merged: dict[datetime, Any] = {}
    for values in (fallback, primary):  # configured history wins exact duplicates
        for bar in values:
            merged[bar.start_time.astimezone(timezone.utc)] = bar
    return [merged[key] for key in sorted(merged)]


class _CurrentShadowSessionProxy:
    """SHADOW-only history recovery with a hard current-session boundary."""

    def __init__(self, delegate: Any, *, session_date, observed_at: datetime) -> None:
        self._delegate = delegate
        self._session_date = session_date
        self._observed_at = observed_at.astimezone(timezone.utc)

    def __getattr__(self, name: str):
        return getattr(self._delegate, name)

    def bars(self, instrument_id, interval, limit=500, binding_id=None, cancellation=None):
        if interval != "1m":
            return self._delegate.bars(instrument_id, interval, limit, binding_id)

        requested_limit = max(500, int(limit or 500))
        response = None
        primary_error: Exception | None = None
        try:
            response = self._delegate.bars(
                instrument_id,
                interval,
                requested_limit,
                binding_id,
            )
            primary = _session_bars(
                list(getattr(response, "bars", ()) or ()),
                session_date=self._session_date,
                observed_at=self._observed_at,
            )
        except Exception as exc:
            primary_error = exc
            primary = []

        # Before the regular session there is intentionally no regular-bar
        # fallback. Returning only same-date premarket evidence prevents the v2
        # monitor from silently reusing yesterday's close as today's structure.
        if self._observed_at.astimezone(_ET).time() < _REGULAR_OPEN:
            if response is not None:
                return _copy_response_with_bars(response, primary)
            if primary_error is not None:
                raise primary_error
            return SimpleNamespace(bars=[])

        needs_fallback = primary_error is not None or not primary
        if not needs_fallback:
            try:
                from .strategy_evaluability import assess_bar_coverage

                needs_fallback = not assess_bar_coverage(
                    primary,
                    session_date=self._session_date,
                    observed_at=self._observed_at,
                    provider="shadow_primary_history",
                ).ready
            except Exception:
                # Coverage telemetry must never make an otherwise usable primary
                # response fail. Existing downstream deterministic checks remain
                # authoritative.
                needs_fallback = False

        fallback: list[Any] = []
        if needs_fallback:
            try:
                fallback = _session_bars(
                    list(
                        self._delegate.execution_indicator_bars(
                            instrument_id,
                            binding_id,
                            as_of=self._observed_at,
                        )
                    ),
                    session_date=self._session_date,
                    observed_at=self._observed_at,
                )
            except Exception:
                fallback = []

        merged = _merge_bars(primary, fallback)
        if merged:
            return _copy_response_with_bars(response, merged)
        if primary_error is not None:
            raise primary_error
        return _copy_response_with_bars(response, primary)


def _alpaca_execution_observation_quote_clock(
    self,
    instrument_id: str,
    *,
    policy=None,
    cancellation=None,
):
    """Use quote age for executable book freshness; keep last trade as price data."""

    headers = alpaca_iex.alpaca_iex_auth_headers()
    binding = self.get_binding(instrument_id)
    response = self.runtime.get(
        f"{self.data_url}/v2/stocks/{binding.provider_symbol}/snapshot",
        params={"feed": "iex"},
        headers=headers,
        timeout=10,
        cancellation=cancellation,
    )
    try:
        payload = response.json()
    except ValueError as exc:
        raise ProviderContractError("Alpaca IEX returned invalid snapshot JSON") from exc
    if not isinstance(payload, dict):
        raise ProviderContractError("Alpaca IEX snapshot payload is malformed")

    latest_quote = payload.get("latestQuote")
    latest_trade = payload.get("latestTrade")
    if not isinstance(latest_trade, dict):
        raise ProviderDataUnavailableError("Alpaca IEX snapshot has no latest trade")

    quote_available = isinstance(latest_quote, dict)
    quote_timestamp_degraded = False
    quote_time = None
    if quote_available:
        try:
            quote_time = alpaca_iex._parse_timestamp(latest_quote.get("t"), field="quote")
        except ProviderContractError:
            quote_available = False
            quote_timestamp_degraded = True
    trade_time = alpaca_iex._parse_timestamp(latest_trade.get("t"), field="trade")

    # The executable object is the bid/ask book. A quiet symbol can have a fresh
    # book and an older last trade; taking min(quote_time, trade_time) incorrectly
    # converts that valid book into STALE_MARKET_DATA.
    source_time = quote_time if quote_available and quote_time is not None else trade_time

    minute_bar = payload.get("minuteBar")
    bar_start_time = None
    bar_high = bar_low = bar_volume = None
    if isinstance(minute_bar, dict):
        timestamp = minute_bar.get("t")
        if timestamp not in {None, ""}:
            bar_start_time = alpaca_iex._parse_timestamp(timestamp, field="minute bar")
        bar_high = minute_bar.get("h")
        bar_low = minute_bar.get("l")
        bar_volume = minute_bar.get("v")

    daily_bar = payload.get("dailyBar")
    cumulative_volume = (
        daily_bar.get("v")
        if isinstance(daily_bar, dict) and daily_bar.get("v") is not None
        else None
    )
    now = self.clock()
    if now.tzinfo is None:
        raise ProviderContractError("Alpaca IEX provider clock must be timezone-aware")
    now = now.astimezone(timezone.utc)
    quote = {
        "instrument_id": instrument_id,
        "binding_id": binding.binding_id,
        "provider": self.provider_id,
        "bid": latest_quote.get("bp") if quote_available else None,
        "ask": latest_quote.get("ap") if quote_available else None,
        "bid_size": alpaca_iex._round_lot_shares(latest_quote.get("bs")) if quote_available else None,
        "ask_size": alpaca_iex._round_lot_shares(latest_quote.get("as")) if quote_available else None,
        "last": latest_trade.get("p"),
        "high": bar_high,
        "low": bar_low,
        "bar_volume": bar_volume,
        "bar_start_time": bar_start_time.isoformat() if bar_start_time else None,
        "cumulative_volume": cumulative_volume,
        "source_time": source_time,
        "received_at": now.isoformat(),
        "session": us_equity_session(source_time),
        "freshness_mode": "fallback" if quote_timestamp_degraded else "live",
        "halted": alpaca_iex.default_alpaca_iex_status_cache().halted(binding.provider_symbol),
    }
    try:
        observation = execution_observation_from_quote(
            quote,
            binding_id=binding.binding_id,
            provider=self.provider_id,
            received_at=now,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ProviderContractError("Alpaca IEX snapshot is missing executable prices") from exc
    return assess_execution_observation(observation, policy)


def _regular_session_reference(at: datetime) -> bool:
    local = at.astimezone(_ET)
    return _REGULAR_OPEN <= local.time() <= _REGULAR_CLOSE


def _outcome_is_valid(row: dict[str, object]) -> bool:
    value = row.get("started_at")
    try:
        started = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return False
    if started.tzinfo is None or not _regular_session_reference(started):
        return False
    ended_value = row.get("ended_at")
    if ended_value is None:
        return True
    try:
        ended = ended_value if isinstance(ended_value, datetime) else datetime.fromisoformat(str(ended_value))
    except (TypeError, ValueError):
        return False
    return ended.tzinfo is not None and ended.astimezone(_ET).date() == started.astimezone(_ET).date()


def _evaluate_opportunity_current_session(*args, **kwargs):
    started_at = kwargs.get("started_at")
    if not isinstance(started_at, datetime) or started_at.tzinfo is None:
        raise ValueError("opportunity_episode_requires_timezone_aware_reference")
    if not _regular_session_reference(started_at):
        raise ValueError("opportunity_episode_requires_current_regular_session_reference")
    assert _ORIGINAL_EPISODE_EVALUATOR is not None
    return _ORIGINAL_EPISODE_EVALUATOR(*args, **kwargs)


def _filtered_events_for_outcomes(events: list[Any], *, event_type: str) -> tuple[list[Any], int]:
    filtered: list[Any] = []
    excluded = 0
    for event in events:
        if event.event_type != event_type:
            filtered.append(event)
            continue
        outcome = event.payload.get("outcome") if isinstance(event.payload, dict) else None
        if isinstance(outcome, dict) and not _outcome_is_valid(outcome):
            excluded += 1
            continue
        filtered.append(event)
    return filtered, excluded


def _episode_metrics_current_session(events, arm):
    assert _ORIGINAL_EPISODE_METRICS is not None
    filtered, excluded = _filtered_events_for_outcomes(
        list(events), event_type="ai_v2_opportunity_episode"
    )
    result = dict(_ORIGINAL_EPISODE_METRICS(filtered, arm))
    result["data_quality_excluded_episode_count"] = sum(
        1
        for event in events
        if event.event_type == "ai_v2_opportunity_episode"
        and event.payload.get("arm") == arm
        and isinstance(event.payload.get("outcome"), dict)
        and not _outcome_is_valid(event.payload["outcome"])
    )
    return result


def _historical_episodes_current_session(repository, strategy_id: str):
    assert _ORIGINAL_HISTORICAL_EPISODES is not None
    return [
        row for row in _ORIGINAL_HISTORICAL_EPISODES(repository, strategy_id)
        if isinstance(row, dict) and _outcome_is_valid(row)
    ]


def _decision_outcome_metrics_current_session(events, arm):
    assert _ORIGINAL_DECISION_OUTCOME_METRICS is not None
    filtered, _ = _filtered_events_for_outcomes(
        list(events), event_type="ai_v2_decision_outcome"
    )
    result = dict(_ORIGINAL_DECISION_OUTCOME_METRICS(filtered, arm))
    result["data_quality_excluded_decision_outcome_count"] = sum(
        1
        for event in events
        if event.event_type == "ai_v2_decision_outcome"
        and event.payload.get("arm") == arm
        and isinstance(event.payload.get("outcome"), dict)
        and not _outcome_is_valid(event.payload["outcome"])
    )
    return result


def _v2_assess_with_shared_circuit(self: AIShadowV2Analyzer, *, arm, rows):
    """Put v2 on the same isolated provider and outage circuit as AI Shadow v1."""

    assert _ORIGINAL_V2_ASSESS is not None
    self.provider_factory = provider_reliability.get_trading_research_provider
    now = monotonic_time.monotonic()
    circuit = provider_reliability._CIRCUIT
    if circuit.is_open(now):
        raise provider_reliability.AIShadowReliabilityError(
            "ai_shadow_v2_provider_circuit_open",
            f"retry_after_seconds={circuit.retry_after(now)};failure_count={circuit.failure_count}",
        )

    last_error: Exception | None = None
    for attempt in range(2):
        try:
            result = _ORIGINAL_V2_ASSESS(self, arm=arm, rows=rows)
            circuit.success()
            return result
        except Exception as exc:
            if not provider_reliability._transport_failure(exc):
                raise
            last_error = exc
            provider_reliability._retire_trading_research_provider()
            if attempt == 0:
                continue
    delay = circuit.trip(monotonic_time.monotonic())
    raise provider_reliability.AIShadowReliabilityError(
        "ai_shadow_v2_transport_exhausted",
        f"attempts=2;retry_after_seconds={delay};last={type(last_error).__name__}:{last_error}",
    ) from last_error


async def _legacy_append_throttled(
    self,
    repository,
    config,
    *,
    instrument_id,
    event_type,
    state,
    reason_code,
    observed_at,
    payload,
    identity,
):
    assert _ORIGINAL_LEGACY_APPEND is not None
    if event_type in {"ai_shadow_input_gap", "ai_shadow_data_gap"}:
        policy = str(payload.get("policy") or "") if isinstance(payload, dict) else ""
        key = (config.strategy_id, instrument_id, event_type, reason_code, policy)
        current = observed_at.astimezone(timezone.utc)
        with _GAP_LOCK:
            previous = _GAP_LAST_EMITTED.get(key)
            if previous is not None and timedelta(0) <= current - previous < _GAP_HEARTBEAT:
                return False
            _GAP_LAST_EMITTED[key] = current
        payload = dict(payload)
        payload["duplicate_gap_heartbeat_seconds"] = int(_GAP_HEARTBEAT.total_seconds())
        payload["gap_sampling"] = "state_or_periodic_heartbeat"
    return await _ORIGINAL_LEGACY_APPEND(
        self,
        repository,
        config,
        instrument_id=instrument_id,
        event_type=event_type,
        state=state,
        reason_code=reason_code,
        observed_at=observed_at,
        payload=payload,
        identity=identity,
    )


async def _run_v2_current_session(self, config, repository, research_repository, market_service, *, now):
    assert _ORIGINAL_V2_RUN_CONFIG is not None
    proxy = _CurrentShadowSessionProxy(
        market_service,
        session_date=now.astimezone(_ET).date(),
        observed_at=now,
    )
    return await _ORIGINAL_V2_RUN_CONFIG(
        self, config, repository, research_repository, proxy, now=now
    )


async def _run_legacy_current_session(self, config, repository, market_service, *, now):
    assert _ORIGINAL_LEGACY_RUN_CONFIG is not None
    proxy = _CurrentShadowSessionProxy(
        market_service,
        session_date=now.astimezone(_ET).date(),
        observed_at=now,
    )
    return await _ORIGINAL_LEGACY_RUN_CONFIG(self, config, repository, proxy, now=now)


async def _run_deep_current_session(self, repository, market_service, config, *, now):
    assert _ORIGINAL_DEEP_RUN_CONFIG is not None
    proxy = _CurrentShadowSessionProxy(
        market_service,
        session_date=now.astimezone(_ET).date(),
        observed_at=now,
    )
    return await _ORIGINAL_DEEP_RUN_CONFIG(self, repository, proxy, config, now=now)


async def _evaluate_shadow_current_session(self, config, repository, market_service, universe):
    assert _ORIGINAL_EVALUATE_CANDIDATES is not None
    if getattr(config, "mode", None) != "shadow":
        return await _ORIGINAL_EVALUATE_CANDIDATES(
            self, config, repository, market_service, universe
        )
    now = datetime.now(timezone.utc)
    proxy = _CurrentShadowSessionProxy(
        market_service,
        session_date=getattr(universe, "session_date", now.astimezone(_ET).date()),
        observed_at=now,
    )
    return await _ORIGINAL_EVALUATE_CANDIDATES(
        self, config, repository, proxy, universe
    )


def install_strategy_runtime_reliability_fixes() -> None:
    global _INSTALLED
    global _ORIGINAL_V2_RUN_CONFIG, _ORIGINAL_LEGACY_RUN_CONFIG
    global _ORIGINAL_DEEP_RUN_CONFIG, _ORIGINAL_EVALUATE_CANDIDATES
    global _ORIGINAL_LEGACY_APPEND, _ORIGINAL_V2_ASSESS
    global _ORIGINAL_EPISODE_EVALUATOR, _ORIGINAL_EPISODE_METRICS
    global _ORIGINAL_HISTORICAL_EPISODES, _ORIGINAL_DECISION_OUTCOME_METRICS
    if _INSTALLED:
        return

    # Capture only after every earlier policy installer has run; this preserves
    # the stacked v2 catalyst/schedule/metrics/risk behavior.
    _ORIGINAL_V2_RUN_CONFIG = v2_monitor.TradingAIShadowV2Monitor._run_config
    _ORIGINAL_LEGACY_RUN_CONFIG = legacy_ai_monitor.TradingAIShadowMonitor._run_config
    _ORIGINAL_DEEP_RUN_CONFIG = deep_monitor.TradingStrategyDeepRecoveryShadowMonitor._run_config
    _ORIGINAL_EVALUATE_CANDIDATES = strategy_monitor.TradingStrategyMonitor._evaluate_candidates
    _ORIGINAL_LEGACY_APPEND = legacy_ai_monitor.TradingAIShadowMonitor._append
    _ORIGINAL_V2_ASSESS = AIShadowV2Analyzer.assess
    _ORIGINAL_EPISODE_EVALUATOR = v2_monitor.evaluate_opportunity_episode
    _ORIGINAL_EPISODE_METRICS = v2_hardening._episode_metrics
    _ORIGINAL_HISTORICAL_EPISODES = v2_monitor._historical_episodes
    _ORIGINAL_DECISION_OUTCOME_METRICS = v2_policy._decision_outcome_metrics

    alpaca_iex.AlpacaIexExecutionProvider.execution_observation = _alpaca_execution_observation_quote_clock
    AIShadowV2Analyzer.assess = _v2_assess_with_shared_circuit
    v2_monitor.evaluate_opportunity_episode = _evaluate_opportunity_current_session
    v2_hardening._episode_metrics = _episode_metrics_current_session
    v2_monitor._historical_episodes = _historical_episodes_current_session
    v2_policy._decision_outcome_metrics = _decision_outcome_metrics_current_session

    legacy_ai_monitor.TradingAIShadowMonitor._append = _legacy_append_throttled
    v2_monitor.TradingAIShadowV2Monitor._run_config = _run_v2_current_session
    legacy_ai_monitor.TradingAIShadowMonitor._run_config = _run_legacy_current_session
    deep_monitor.TradingStrategyDeepRecoveryShadowMonitor._run_config = _run_deep_current_session
    strategy_monitor.TradingStrategyMonitor._evaluate_candidates = _evaluate_shadow_current_session
    _INSTALLED = True


__all__ = [
    "_CurrentShadowSessionProxy",
    "_outcome_is_valid",
    "install_strategy_runtime_reliability_fixes",
]
