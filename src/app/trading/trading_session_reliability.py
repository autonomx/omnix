from __future__ import annotations

"""Session reliability fixes and SHADOW-only strategy research overlays.

Canonical V2 and AUTO PAPER execution authority remain unchanged.
"""

import asyncio
import copy
import os
import re
from datetime import date, datetime, time, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict

from .models import MarketBar


_ET = ZoneInfo("America/New_York")
_INSTALLED = False
FULL_SESSION_1M_LIMIT = 500

DEEP_RECOVERY_RISK_OVERLAY_VERSION = "deep-recovery-risk-overlay-v1"
DEEP_RECOVERY_MAX_RISK_PCT = Decimal("8")
DEEP_RECOVERY_MAX_VWAP_EXTENSION_PCT = Decimal("10")

TREND_CONTINUATION_SETUP_ID = "trend_continuation_v1"
TREND_CONTINUATION_RULE_VERSION = "1.0.0-shadow"
TREND_MIN_1M_BARS = 20
TREND_MIN_SESSION_RETURN_PCT = Decimal("5")
TREND_MIN_VOLUME_RATIO = Decimal("1.25")
TREND_MIN_CLOSE_LOCATION = Decimal("0.60")
TREND_MAX_EMA9_EXTENSION_PCT = Decimal("6")
TREND_MAX_RISK_PCT = Decimal("8")


TrendState = Literal[
    "waiting_session",
    "waiting_history",
    "waiting_trend",
    "waiting_breakout",
    "waiting_volume",
    "too_extended",
    "risk_too_wide",
    "signal_ready",
    "expired",
]


class TrendContinuationShadowEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    setup_id: Literal["trend_continuation_v1"] = TREND_CONTINUATION_SETUP_ID
    rule_version: Literal["1.0.0-shadow"] = TREND_CONTINUATION_RULE_VERSION
    state: TrendState
    reason_code: str
    observed_at: datetime | None = None
    current_price: Decimal | None = None
    session_vwap: Decimal | None = None
    session_return_pct: Decimal | None = None
    ema9: Decimal | None = None
    ema20: Decimal | None = None
    ema9_extension_pct: Decimal | None = None
    prior_breakout_high: Decimal | None = None
    breakout_confirmed: bool | None = None
    volume_ratio: Decimal | None = None
    close_location: Decimal | None = None
    research_stop_price: Decimal | None = None
    research_risk_pct: Decimal | None = None
    execution_authority: Literal[False] = False

    @property
    def signal_ready(self) -> bool:
        return self.state == "signal_ready"


def _decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _ema(values: list[Decimal], period: int) -> list[Decimal | None]:
    output: list[Decimal | None] = [None] * len(values)
    if len(values) < period:
        return output
    value = sum(values[:period], Decimal("0")) / Decimal(period)
    output[period - 1] = value
    alpha = Decimal("2") / Decimal(period + 1)
    for index in range(period, len(values)):
        value = (values[index] - value) * alpha + value
        output[index] = value
    return output


def _close_location(bar: MarketBar) -> Decimal:
    width = bar.high - bar.low
    if width <= 0:
        return Decimal("1") if bar.close >= bar.open else Decimal("0")
    return (bar.close - bar.low) / width


def evaluate_trend_continuation_shadow(
    bars: list[MarketBar] | tuple[MarketBar, ...],
    *,
    entry_start_et: time,
    last_entry_et: time,
    stop_buffer_bps: Decimal = Decimal("15"),
) -> TrendContinuationShadowEvaluation:
    """Detect a TNON-like no-L1 trend continuation without touching V2."""

    from .strategies.gap_pullback import session_vwap
    from .strategy_timeframes import resample_final_bars

    regular = sorted(
        (bar for bar in bars if bar.is_final and bar.session == "regular"),
        key=lambda bar: bar.start_time,
    )
    if not regular:
        return TrendContinuationShadowEvaluation(
            state="waiting_session",
            reason_code="TREND_CONTINUATION_WAITING_SESSION",
        )

    current = regular[-1]
    observed_at = current.end_time
    observed_et = observed_at.astimezone(_ET).time()
    base = {"observed_at": observed_at, "current_price": current.close}
    if observed_et < entry_start_et:
        return TrendContinuationShadowEvaluation(
            state="waiting_session",
            reason_code="TREND_CONTINUATION_ENTRY_WINDOW_NOT_OPEN",
            **base,
        )
    if observed_et > last_entry_et:
        return TrendContinuationShadowEvaluation(
            state="expired",
            reason_code="TREND_CONTINUATION_ENTRY_WINDOW_CLOSED",
            **base,
        )
    if len(regular) < TREND_MIN_1M_BARS:
        return TrendContinuationShadowEvaluation(
            state="waiting_history",
            reason_code="TREND_CONTINUATION_INSUFFICIENT_HISTORY",
            **base,
        )

    closes = [bar.close for bar in regular]
    ema9_values = _ema(closes, 9)
    ema20_values = _ema(closes, 20)
    ema9 = ema9_values[-1]
    ema20 = ema20_values[-1]
    ema9_prior = next((v for v in reversed(ema9_values[:-3]) if v is not None), None)
    ema20_prior = next((v for v in reversed(ema20_values[:-3]) if v is not None), None)
    vwap = session_vwap(regular)
    session_return = (
        (current.close / regular[0].open - Decimal("1")) * Decimal("100")
        if regular[0].open > 0
        else Decimal("0")
    )
    extension = (
        (current.close / ema9 - Decimal("1")) * Decimal("100")
        if ema9 is not None and ema9 > 0
        else None
    )
    common = {
        **base,
        "session_vwap": vwap,
        "session_return_pct": session_return,
        "ema9": ema9,
        "ema20": ema20,
        "ema9_extension_pct": extension,
    }
    trend_ok = (
        ema9 is not None
        and ema20 is not None
        and ema9_prior is not None
        and ema20_prior is not None
        and current.close > ema9 > ema20
        and ema9 > ema9_prior
        and ema20 > ema20_prior
        and vwap is not None
        and current.close > vwap
        and session_return >= TREND_MIN_SESSION_RETURN_PCT
    )
    if not trend_ok:
        return TrendContinuationShadowEvaluation(
            state="waiting_trend",
            reason_code="TREND_CONTINUATION_TREND_NOT_CONFIRMED",
            **common,
        )
    if extension is None or extension > TREND_MAX_EMA9_EXTENSION_PCT:
        return TrendContinuationShadowEvaluation(
            state="too_extended",
            reason_code="TREND_CONTINUATION_EMA_EXTENSION_TOO_HIGH",
            **common,
        )

    sampled = [
        bar for bar in resample_final_bars(regular, "3m") if bar.session == "regular"
    ]
    if len(sampled) < 6:
        return TrendContinuationShadowEvaluation(
            state="waiting_history",
            reason_code="TREND_CONTINUATION_3M_HISTORY_INSUFFICIENT",
            **common,
        )
    current_3m = sampled[-1]
    prior_high = max(bar.high for bar in sampled[-4:-1])
    breakout = current_3m.close > prior_high
    location = _close_location(current_3m)
    common.update(
        {
            "prior_breakout_high": prior_high,
            "breakout_confirmed": breakout,
            "close_location": location,
        }
    )
    if not breakout or location < TREND_MIN_CLOSE_LOCATION:
        return TrendContinuationShadowEvaluation(
            state="waiting_breakout",
            reason_code="TREND_CONTINUATION_WAITING_3M_BREAKOUT",
            **common,
        )

    prior_volume = sampled[-6:-1]
    average_volume = sum((bar.volume for bar in prior_volume), Decimal("0")) / Decimal(5)
    volume_ratio = current_3m.volume / average_volume if average_volume > 0 else None
    common["volume_ratio"] = volume_ratio
    if volume_ratio is None or volume_ratio < TREND_MIN_VOLUME_RATIO:
        return TrendContinuationShadowEvaluation(
            state="waiting_volume",
            reason_code="TREND_CONTINUATION_VOLUME_NOT_EXPANDING",
            **common,
        )

    stop_reference = min(bar.low for bar in sampled[-3:])
    stop_price = stop_reference * (
        Decimal("1") - Decimal(stop_buffer_bps) / Decimal("10000")
    )
    risk_pct = (
        (current.close - stop_price) / current.close * Decimal("100")
        if current.close > stop_price > 0
        else None
    )
    common.update(
        {"research_stop_price": stop_price, "research_risk_pct": risk_pct}
    )
    if risk_pct is None or risk_pct <= 0 or risk_pct > TREND_MAX_RISK_PCT:
        return TrendContinuationShadowEvaluation(
            state="risk_too_wide",
            reason_code="TREND_CONTINUATION_RISK_TOO_WIDE",
            **common,
        )
    return TrendContinuationShadowEvaluation(
        state="signal_ready",
        reason_code="TREND_CONTINUATION_BREAKOUT_SHADOW",
        **common,
    )


def _apply_deep_recovery_risk_overlay(evaluation):
    if not getattr(evaluation, "signal_ready", False):
        return evaluation

    risk_pct = _decimal(getattr(evaluation, "research_risk_pct", None))
    vwap_extension = _decimal(getattr(evaluation, "vwap_distance_pct", None))
    features = dict(getattr(evaluation, "hard_gate_features", {}) or {})
    features["deep_recovery_risk_overlay"] = {
        "version": DEEP_RECOVERY_RISK_OVERLAY_VERSION,
        "max_research_risk_pct": str(DEEP_RECOVERY_MAX_RISK_PCT),
        "max_vwap_extension_pct": str(DEEP_RECOVERY_MAX_VWAP_EXTENSION_PCT),
    }
    if risk_pct is None or risk_pct > DEEP_RECOVERY_MAX_RISK_PCT:
        return evaluation.model_copy(
            update={
                "state": "waiting_breakout",
                "reason_code": "DEEP_RECOVERY_RISK_TOO_WIDE",
                "hard_gate_features": features,
            }
        )
    if vwap_extension is None or vwap_extension > DEEP_RECOVERY_MAX_VWAP_EXTENSION_PCT:
        return evaluation.model_copy(
            update={
                "state": "waiting_breakout",
                "reason_code": "DEEP_RECOVERY_EXTENSION_TOO_HIGH",
                "hard_gate_features": features,
            }
        )
    return evaluation.model_copy(update={"hard_gate_features": features})


def _normalize_timestamp_text(value: str) -> str:
    text = value.strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    match = re.match(
        r"^(?P<prefix>\d{4}-\d{2}-\d{2}[Tt ]\d{2}:\d{2}:\d{2})"
        r"(?:\.(?P<fraction>\d+))?(?P<offset>[+-]\d{2}:?\d{2})$",
        text,
    )
    if not match:
        return text
    fraction = (match.group("fraction") or "")[:6]
    offset = match.group("offset")
    if len(offset) == 5 and ":" not in offset:
        offset = offset[:3] + ":" + offset[3:]
    return (
        match.group("prefix").replace("t", "T")
        + (f".{fraction}" if fraction else "")
        + offset
    )


def parse_alpaca_timestamp(value: Any, *, field: str) -> datetime:
    """Accept RFC3339/nanosecond and epoch forms; remain fail-closed."""

    from .providers.errors import ProviderContractError

    if value is None or value == "":
        raise ProviderContractError(
            f"Alpaca IEX snapshot is missing {field} timestamp"
        )
    parsed: datetime | None = None
    raw = repr(value)[:160]
    try:
        if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
            epoch = Decimal(str(value))
        elif isinstance(value, str) and re.fullmatch(
            r"[+-]?\d+(?:\.\d+)?", value.strip()
        ):
            epoch = Decimal(value.strip())
        else:
            epoch = None
        if epoch is not None:
            magnitude = abs(epoch)
            if magnitude >= Decimal("1e17"):
                epoch /= Decimal("1e9")
            elif magnitude >= Decimal("1e14"):
                epoch /= Decimal("1e6")
            elif magnitude >= Decimal("1e11"):
                epoch /= Decimal("1e3")
            parsed = datetime.fromtimestamp(float(epoch), tz=timezone.utc)
        elif isinstance(value, str):
            parsed = datetime.fromisoformat(_normalize_timestamp_text(value))
        else:
            raise TypeError("unsupported timestamp type")
    except (ValueError, TypeError, InvalidOperation, OverflowError, OSError) as exc:
        raise ProviderContractError(
            f"Alpaca IEX returned invalid {field} timestamp (value={raw})"
        ) from exc
    if parsed is None:
        raise ProviderContractError(
            f"Alpaca IEX returned invalid {field} timestamp (value={raw})"
        )
    if parsed.tzinfo is None:
        raise ProviderContractError(
            f"Alpaca IEX {field} timestamp must be timezone-aware"
        )
    return parsed.astimezone(timezone.utc)


def _merge_causal_bars(
    primary: list[MarketBar] | tuple[MarketBar, ...],
    fallback: list[MarketBar] | tuple[MarketBar, ...],
    *,
    session_date: date,
    observed_at: datetime,
) -> list[MarketBar]:
    observed_utc = observed_at.astimezone(timezone.utc)
    merged: dict[datetime, MarketBar] = {}
    for bars in (fallback, primary):  # primary wins duplicate minutes
        for bar in bars:
            if (
                bar.is_final
                and bar.end_time <= observed_utc
                and bar.start_time.astimezone(_ET).date() == session_date
            ):
                merged[bar.start_time.astimezone(timezone.utc)] = bar
    return [merged[key] for key in sorted(merged)]


def _copy_response_with_bars(response: Any, bars: list[MarketBar]) -> Any:
    provenance = getattr(response, "provenance", None)
    updated_provenance = provenance
    if provenance is not None and hasattr(provenance, "model_copy"):
        updated_provenance = provenance.model_copy(
            update={
                "freshness_mode": "fallback",
                "fallback_reason": "provider_specific_1m_gap_filled_by_alpaca_iex",
                "history_complete": True,
            }
        )
    if hasattr(response, "model_copy"):
        updates: dict[str, object] = {"bars": bars}
        if updated_provenance is not None:
            updates["provenance"] = updated_provenance
        return response.model_copy(update=updates)
    cloned = copy.copy(response)
    setattr(cloned, "bars", bars)
    return cloned


class _FullSessionMarketServiceProxy:
    def __init__(
        self,
        delegate: Any,
        *,
        session_date: date,
        observed_at: datetime,
        allow_shadow_fallback: bool,
    ) -> None:
        self._delegate = delegate
        self._session_date = session_date
        self._observed_at = observed_at.astimezone(timezone.utc)
        self._allow_shadow_fallback = allow_shadow_fallback

    def __getattr__(self, name: str):
        return getattr(self._delegate, name)

    def bars(
        self,
        instrument_id,
        interval,
        limit=500,
        binding_id=None,
        cancellation=None,
    ):
        requested_limit = int(limit or FULL_SESSION_1M_LIMIT)
        if interval == "1m":
            requested_limit = max(requested_limit, FULL_SESSION_1M_LIMIT)
        response = self._delegate.bars(
            instrument_id,
            interval,
            requested_limit,
            binding_id,
        )
        if interval != "1m" or not self._allow_shadow_fallback:
            return response

        from .strategy_evaluability import assess_bar_coverage

        primary = list(getattr(response, "bars", ()) or ())
        coverage = assess_bar_coverage(
            primary,
            session_date=self._session_date,
            observed_at=self._observed_at,
            provider="configured_history",
        )
        if coverage.ready:
            return response
        try:
            fallback = list(
                self._delegate.execution_indicator_bars(
                    instrument_id,
                    binding_id,
                    as_of=self._observed_at,
                )
            )
        except Exception:
            return response
        merged = _merge_causal_bars(
            primary,
            fallback,
            session_date=self._session_date,
            observed_at=self._observed_at,
        )
        merged_coverage = assess_bar_coverage(
            merged,
            session_date=self._session_date,
            observed_at=self._observed_at,
            provider="configured_history+alpaca_iex",
            fallback_provider="alpaca_iex",
        )
        return (
            _copy_response_with_bars(response, merged)
            if merged_coverage.ready
            else response
        )


class _IntradaySchemaProviderProxy:
    def __init__(self, delegate: Any) -> None:
        self._delegate = delegate

    def __getattr__(self, name: str):
        return getattr(self._delegate, name)

    def chat_completion(self, *args, **kwargs):
        response_format = kwargs.get("response_format")
        if (
            isinstance(response_format, dict)
            and str(response_format.get("type") or "").casefold() == "json_object"
        ):
            from app.providers.structured.contracts import StructuredMode
            from app.providers.structured.schema_projection import project_provider_schema
            from .strategy_intraday_llm import IntradayLLMBatchResponse

            schema = project_provider_schema(
                IntradayLLMBatchResponse.model_json_schema(),
                mode=StructuredMode.JSON_SCHEMA,
                provider_name="chatgpt_codex",
            )
            kwargs = dict(kwargs)
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "intraday_llm_batch_response",
                    "strict": True,
                    "schema": schema,
                },
            }
        return self._delegate.chat_completion(*args, **kwargs)


async def _collect_trend_signal(
    monitor,
    config,
    repository,
    market_service,
    universe,
    *,
    now: datetime,
) -> None:
    if not (
        os.environ.get("OMNIX_TRADING_TREND_CONTINUATION_SHADOW", "1")
        .strip()
        .lower()
        in {"1", "true", "yes", "on"}
        and config.enabled
        and config.mode == "shadow"
        and config.config.strategy_version == "2.0.0"
        and getattr(universe, "discovery_source", None) == "finviz"
    ):
        return

    from .strategy_evaluability import assess_bar_coverage
    from .strategy_shadow_execution import observe_shadow_execution
    from .trade_logging import trade_log

    recent = await asyncio.to_thread(
        repository.recent_events,
        config.strategy_id,
        10_000,
    )
    signaled = {
        event.instrument_id
        for event in recent
        if event.event_type == "trend_continuation_shadow"
        and event.observed_at.astimezone(_ET).date() == universe.session_date
    }
    for candidate in universe.candidates:
        if candidate.instrument_id in signaled:
            continue
        try:
            response = await asyncio.to_thread(
                market_service.bars,
                candidate.instrument_id,
                "1m",
                FULL_SESSION_1M_LIMIT,
                candidate.binding_id,
            )
            bars = list(response.bars)
            coverage = assess_bar_coverage(
                bars,
                session_date=universe.session_date,
                observed_at=now,
                provider="trend_continuation_shadow",
            )
            if not coverage.ready:
                continue
            evaluation = evaluate_trend_continuation_shadow(
                bars,
                entry_start_et=config.risk.entry_start_et,
                last_entry_et=config.risk.last_entry_et,
                stop_buffer_bps=config.config.stop_buffer_bps,
            )
        except Exception as exc:
            trade_log(
                "auto_trading",
                "trend_continuation_shadow_error",
                strategy_id=config.strategy_id,
                instrument_id=candidate.instrument_id,
                error_type=type(exc).__name__,
                detail=str(exc),
                execution_authority=False,
            )
            continue
        if not evaluation.signal_ready:
            continue

        execution = None
        execution_error = None
        risk_decision = {
            "allowed": False,
            "reason_codes": ["TREND_CONTINUATION_EXECUTION_EVIDENCE_ERROR"],
        }
        try:
            evidence = await asyncio.to_thread(
                observe_shadow_execution,
                market_service,
                instrument_id=candidate.instrument_id,
                binding_id=candidate.binding_id,
            )
            execution = evidence.execution
            reasons = []
            if execution.get("halted") is True:
                reasons.append("TREND_CONTINUATION_HALTED")
            if execution.get("execution_eligible") is not True:
                reasons.append("TREND_CONTINUATION_EXECUTION_INELIGIBLE")
            spread = _decimal(execution.get("spread_bps"))
            if spread is None:
                reasons.append("TREND_CONTINUATION_SPREAD_MISSING")
            elif spread > config.risk.max_spread_bps:
                reasons.append("TREND_CONTINUATION_SPREAD_TOO_WIDE")
            risk_decision = {
                "allowed": not reasons,
                "reason_codes": list(dict.fromkeys(reasons)),
            }
        except Exception as exc:
            execution_error = f"{type(exc).__name__}: {exc}"

        observed_at = evaluation.observed_at or now
        persisted = await monitor._event(
            repository,
            config,
            instrument_id=candidate.instrument_id,
            event_type="trend_continuation_shadow",
            state="signal_ready",
            reason_code="TREND_CONTINUATION_SHADOW_SIGNAL",
            observed_at=observed_at,
            payload={
                "setup_id": evaluation.setup_id,
                "rule_version": evaluation.rule_version,
                "evaluation": evaluation.model_dump(mode="json"),
                "universe_id": universe.universe_id,
                "bar_coverage": coverage.model_dump(mode="json"),
                "execution": execution,
                "execution_error": execution_error,
                "risk_decision": risk_decision,
                "research_only": True,
                "execution_authority": False,
            },
        )
        if persisted:
            trade_log(
                "auto_trading",
                "trend_continuation_shadow_signal",
                strategy_id=config.strategy_id,
                instrument_id=candidate.instrument_id,
                observed_at=observed_at,
                session_return_pct=evaluation.session_return_pct,
                volume_ratio=evaluation.volume_ratio,
                ema9_extension_pct=evaluation.ema9_extension_pct,
                research_risk_pct=evaluation.research_risk_pct,
                execution_eligible=risk_decision["allowed"],
                execution_authority=False,
            )


def install_trading_session_reliability() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    from . import strategy_ai_shadow_monitor as ai_monitor
    from . import strategy_deep_recovery as deep_recovery
    from . import strategy_deep_recovery_monitor as deep_monitor
    from . import strategy_intraday_llm as intraday_llm
    from . import strategy_monitor
    from .providers import alpaca_iex

    original_intraday_provider = intraday_llm._default_provider

    def schema_aware_intraday_provider():
        provider = original_intraday_provider()
        provider_name = str(
            getattr(provider, "provider_name", "")
            or getattr(getattr(provider, "config", None), "provider_type", "")
        ).strip().casefold()
        return (
            _IntradaySchemaProviderProxy(provider)
            if provider is not None and provider_name == "chatgpt_codex"
            else provider
        )

    intraday_llm._default_provider = schema_aware_intraday_provider
    alpaca_iex._parse_timestamp = parse_alpaca_timestamp

    original_deep_evaluate = deep_recovery.evaluate_deep_recovery_shadow

    def deep_evaluate(candidate, bars, config):
        return _apply_deep_recovery_risk_overlay(
            original_deep_evaluate(candidate, bars, config)
        )

    deep_recovery.evaluate_deep_recovery_shadow = deep_evaluate
    deep_monitor.evaluate_deep_recovery_shadow = deep_evaluate

    original_deep_run = deep_monitor.TradingStrategyDeepRecoveryShadowMonitor._run_config

    async def deep_run(self, repository, market_service, config, *, now):
        proxy = _FullSessionMarketServiceProxy(
            market_service,
            session_date=now.astimezone(_ET).date(),
            observed_at=now,
            allow_shadow_fallback=True,
        )
        return await original_deep_run(
            self, repository, proxy, config, now=now
        )

    deep_monitor.TradingStrategyDeepRecoveryShadowMonitor._run_config = deep_run

    original_ai_run = ai_monitor.TradingAIShadowMonitor._run_config

    async def ai_run(self, config, repository, market_service, *, now):
        proxy = _FullSessionMarketServiceProxy(
            market_service,
            session_date=now.astimezone(_ET).date(),
            observed_at=now,
            allow_shadow_fallback=True,
        )
        return await original_ai_run(
            self, config, repository, proxy, now=now
        )

    ai_monitor.TradingAIShadowMonitor._run_config = ai_run

    original_evaluate = strategy_monitor.TradingStrategyMonitor._evaluate_candidates

    async def evaluate(self, config, repository, market_service, universe):
        now = datetime.now(timezone.utc)
        proxy = _FullSessionMarketServiceProxy(
            market_service,
            session_date=getattr(
                universe, "session_date", now.astimezone(_ET).date()
            ),
            observed_at=now,
            allow_shadow_fallback=config.mode == "shadow",
        )
        proposals = await original_evaluate(
            self, config, repository, proxy, universe
        )
        if hasattr(universe, "session_date") and hasattr(universe, "candidates"):
            await _collect_trend_signal(
                self,
                config,
                repository,
                proxy,
                universe,
                now=now,
            )
        return proposals

    strategy_monitor.TradingStrategyMonitor._evaluate_candidates = evaluate
    _INSTALLED = True


__all__ = [
    "DEEP_RECOVERY_MAX_RISK_PCT",
    "DEEP_RECOVERY_MAX_VWAP_EXTENSION_PCT",
    "FULL_SESSION_1M_LIMIT",
    "TREND_CONTINUATION_RULE_VERSION",
    "TREND_CONTINUATION_SETUP_ID",
    "TrendContinuationShadowEvaluation",
    "evaluate_trend_continuation_shadow",
    "install_trading_session_reliability",
    "parse_alpaca_timestamp",
]
