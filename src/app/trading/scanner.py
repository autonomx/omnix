from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .indicators.engine import (
    CORE_INDICATOR_FORMULA_VERSION,
    average_true_range,
    exponential_moving_average,
    relative_strength_index,
    simple_moving_average,
)
from .models import BarsResponse, MarketBar


ScannerMetric = Literal["close", "percent_change", "volume", "sma", "ema", "rsi", "atr"]
ScannerOperator = Literal["gt", "gte", "lt", "lte"]
ScannerRunStatus = Literal["queued", "running", "completed", "failed", "cancelled", "timed_out"]


class TradingScannerRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule_id: str = Field(min_length=1, max_length=100)
    metric: ScannerMetric
    operator: ScannerOperator
    threshold: Decimal
    period: int = Field(default=14, ge=1, le=500)
    lookback_bars: int = Field(default=1, ge=1, le=499)


class TradingScannerDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scanner_id: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=200)
    instrument_ids: list[str] = Field(min_length=1, max_length=200)
    binding_ids: dict[str, str] = Field(default_factory=dict)
    interval: str = Field(default="1d", min_length=1, max_length=16)
    history_limit: int = Field(default=100, ge=2, le=500)
    rules: list[TradingScannerRule] = Field(min_length=1, max_length=20)
    max_concurrency: int = Field(default=4, ge=1, le=8)
    request_timeout_seconds: float = Field(default=10, ge=1, le=30)
    run_timeout_seconds: float = Field(default=120, ge=1, le=300)
    formula_version: str = CORE_INDICATOR_FORMULA_VERSION
    enabled: bool = True
    revision: int = Field(default=1, ge=1)
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @model_validator(mode="after")
    def validate_definition(self):
        if self.formula_version != CORE_INDICATOR_FORMULA_VERSION:
            raise ValueError(f"unsupported scanner formula version: {self.formula_version}")
        if len(set(self.instrument_ids)) != len(self.instrument_ids):
            raise ValueError("scanner instrument_ids must be unique")
        unknown_bindings = set(self.binding_ids) - set(self.instrument_ids)
        if unknown_bindings:
            raise ValueError(f"scanner binding_ids contain instruments outside allowlist: {sorted(unknown_bindings)}")
        required = max(scanner_rule_history(rule) for rule in self.rules)
        if self.history_limit < required:
            raise ValueError(
                f"history_limit {self.history_limit} is smaller than required metric history {required}"
            )
        return self


class TradingScannerRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    scanner_id: str
    status: ScannerRunStatus
    cancellation_requested: bool = False
    universe_count: int = 0
    completed_count: int = 0
    matched_count: int = 0
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_message: str | None = None
    definition_snapshot: dict[str, object]
    created_at: datetime | None = None
    updated_at: datetime | None = None


class TradingScannerResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    instrument_id: str
    requested_binding_id: str | None = None
    resolved_binding_id: str
    provider: str
    dataset_fingerprint: str
    source_as_of: datetime
    formula_version: str
    metrics: dict[str, Decimal]
    matched_rules: list[str]
    rank: int = Field(ge=1)
    score: Decimal


class ScannerExecutionSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ScannerRunStatus
    completed_count: int
    results: list[TradingScannerResult]
    error_message: str | None = None


class ScannerCancellation(Protocol):
    def is_set(self) -> bool: ...


class AsyncScannerCancellation:
    def __init__(self) -> None:
        self._event = asyncio.Event()

    def set(self) -> None:
        self._event.set()

    def is_set(self) -> bool:
        return self._event.is_set()


BarsFetcher = Callable[[str, str, int, str | None], BarsResponse]
ProgressCallback = Callable[[int], None]


def scanner_rule_history(rule: TradingScannerRule) -> int:
    if rule.metric == "percent_change":
        return rule.lookback_bars + 1
    if rule.metric in {"sma", "ema", "atr"}:
        return rule.period
    if rule.metric == "rsi":
        return rule.period + 1
    return 2


def _metric_key(rule: TradingScannerRule) -> str:
    if rule.metric == "percent_change":
        return f"percent_change:{rule.lookback_bars}"
    if rule.metric in {"sma", "ema", "rsi", "atr"}:
        return f"{rule.metric}:{rule.period}"
    return rule.metric


def scanner_metric_formula(rule: TradingScannerRule) -> str:
    if rule.metric == "percent_change":
        return f"((close[t] / close[t-{rule.lookback_bars}]) - 1) * 100"
    if rule.metric == "volume":
        return "final_bar.volume"
    if rule.metric == "close":
        return "final_bar.close"
    return f"{CORE_INDICATOR_FORMULA_VERSION}:{rule.metric}:{rule.period}"


def scanner_metric_value(rule: TradingScannerRule, bars: Sequence[MarketBar]) -> Decimal | None:
    if not bars:
        return None
    closes = [Decimal(bar.close) for bar in bars]
    if rule.metric == "close":
        return closes[-1]
    if rule.metric == "volume":
        return Decimal(bars[-1].volume)
    if rule.metric == "percent_change":
        if len(closes) <= rule.lookback_bars or closes[-rule.lookback_bars - 1] == 0:
            return None
        return (closes[-1] / closes[-rule.lookback_bars - 1] - Decimal("1")) * Decimal("100")
    if rule.metric == "sma":
        values = simple_moving_average(closes, rule.period)
    elif rule.metric == "ema":
        values = exponential_moving_average(closes, rule.period)
    elif rule.metric == "rsi":
        values = relative_strength_index(closes, rule.period)
    else:
        values = average_true_range(
            [Decimal(bar.high) for bar in bars],
            [Decimal(bar.low) for bar in bars],
            closes,
            rule.period,
        )
    return values[-1] if values else None


def scanner_rule_matches(rule: TradingScannerRule, value: Decimal) -> bool:
    if rule.operator == "gt":
        return value > rule.threshold
    if rule.operator == "gte":
        return value >= rule.threshold
    if rule.operator == "lt":
        return value < rule.threshold
    return value <= rule.threshold


def _score(rule: TradingScannerRule, value: Decimal) -> Decimal:
    denominator = abs(rule.threshold) if rule.threshold != 0 else Decimal("1")
    if rule.operator in {"gt", "gte"}:
        return (value - rule.threshold) / denominator
    return (rule.threshold - value) / denominator


def evaluate_scanner_dataset(
    definition: TradingScannerDefinition,
    run_id: str,
    response: BarsResponse,
    requested_binding_id: str | None,
) -> TradingScannerResult | None:
    bars = [bar for bar in response.bars if bar.is_final]
    metrics: dict[str, Decimal] = {}
    formulas: dict[str, str] = {}
    matched: list[str] = []
    score = Decimal("0")
    for rule in definition.rules:
        value = scanner_metric_value(rule, bars)
        if value is None:
            return None
        metrics[_metric_key(rule)] = value
        formulas[rule.rule_id] = scanner_metric_formula(rule)
        if scanner_rule_matches(rule, value):
            matched.append(rule.rule_id)
            score += _score(rule, value)
    if len(matched) != len(definition.rules):
        return None
    metrics["_formula_count"] = Decimal(len(formulas))
    return TradingScannerResult(
        run_id=run_id,
        instrument_id=response.instrument.instrument_id,
        requested_binding_id=requested_binding_id,
        resolved_binding_id=response.binding.binding_id,
        provider=response.binding.provider,
        dataset_fingerprint=response.provenance.dataset_fingerprint,
        source_as_of=response.provenance.as_of,
        formula_version=definition.formula_version,
        metrics=metrics,
        matched_rules=matched,
        rank=1,
        score=score,
    )


async def execute_scanner(
    definition: TradingScannerDefinition,
    run_id: str,
    fetch_bars: BarsFetcher,
    cancellation: ScannerCancellation,
    progress: ProgressCallback | None = None,
) -> ScannerExecutionSummary:
    semaphore = asyncio.Semaphore(definition.max_concurrency)
    completed = 0

    async def scan(instrument_id: str) -> TradingScannerResult | None:
        nonlocal completed
        if cancellation.is_set():
            return None
        async with semaphore:
            if cancellation.is_set():
                return None
            requested_binding = definition.binding_ids.get(instrument_id)
            response = await asyncio.wait_for(
                asyncio.to_thread(
                    fetch_bars,
                    instrument_id,
                    definition.interval,
                    definition.history_limit,
                    requested_binding,
                ),
                timeout=definition.request_timeout_seconds,
            )
            result = evaluate_scanner_dataset(
                definition,
                run_id,
                response,
                requested_binding,
            )
            completed += 1
            if progress:
                progress(completed)
            return result

    tasks = [asyncio.create_task(scan(instrument_id)) for instrument_id in definition.instrument_ids]
    try:
        raw_results = await asyncio.wait_for(
            asyncio.gather(*tasks),
            timeout=definition.run_timeout_seconds,
        )
    except asyncio.TimeoutError:
        for task in tasks:
            task.cancel()
        return ScannerExecutionSummary(
            status="timed_out",
            completed_count=completed,
            results=[],
            error_message="scanner run exceeded run_timeout_seconds",
        )
    except asyncio.CancelledError:
        for task in tasks:
            task.cancel()
        raise
    except Exception as exc:
        for task in tasks:
            task.cancel()
        return ScannerExecutionSummary(
            status="failed",
            completed_count=completed,
            results=[],
            error_message=f"{type(exc).__name__}: {exc}",
        )
    if cancellation.is_set():
        return ScannerExecutionSummary(
            status="cancelled",
            completed_count=completed,
            results=[],
        )
    ranked = sorted(
        [result for result in raw_results if result is not None],
        key=lambda result: (-result.score, result.instrument_id),
    )
    ranked = [result.model_copy(update={"rank": index + 1}) for index, result in enumerate(ranked)]
    return ScannerExecutionSummary(
        status="completed",
        completed_count=completed,
        results=ranked,
    )


def scanner_definition_fingerprint(definition: TradingScannerDefinition) -> str:
    payload = definition.model_dump(mode="json", exclude={"revision", "created_at", "updated_at"})
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
