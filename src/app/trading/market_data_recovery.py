from __future__ import annotations

"""Shared interval-agnostic market-data recovery orchestration.

Recovery produces canonical evidence plus explicit unresolved ranges. It never
declares a feature trustworthy; feature_qualification owns that downstream
decision. No synthetic halt/no-trade bars are created.
"""

from collections.abc import Callable
from datetime import date, datetime, time, timedelta, timezone
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .models import MarketBar
from .strategy_timeframes import resample_final_bars


_ET = ZoneInfo("America/New_York")
_REGULAR_OPEN = time(9, 30)
_REGULAR_CLOSE = time(16, 0)

RecoveryStatus = Literal["COMPLETE", "PARTIAL", "UNAVAILABLE"]


class RecoveryAttempt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    stage: Literal[
        "primary",
        "primary_retry",
        "fallback",
        "lower_resolution_rebuild",
        "nontrading_confirmation",
    ]
    source: str
    succeeded: bool
    bar_count: int = Field(default=0, ge=0)
    detail: str | None = None


class RecoveredBarSeries(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True)

    instrument_id: str
    interval: str
    session_date: date
    observed_at: datetime
    bars: tuple[MarketBar, ...]
    status: RecoveryStatus
    unresolved_starts: tuple[datetime, ...] = ()
    confirmed_nontrading_starts: tuple[datetime, ...] = ()
    attempts: tuple[RecoveryAttempt, ...] = ()
    source_providers: tuple[str, ...] = ()

    @field_validator("observed_at")
    @classmethod
    def _aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("recovery observed_at must be timezone-aware")
        return value.astimezone(timezone.utc)


def interval_duration(interval: str) -> timedelta:
    raw = interval.strip().lower()
    if raw.endswith("m") and raw[:-1].isdigit():
        return timedelta(minutes=int(raw[:-1]))
    if raw.endswith("h") and raw[:-1].isdigit():
        return timedelta(hours=int(raw[:-1]))
    raise ValueError(f"unsupported_recovery_interval:{interval}")


def _session_bounds(session_date: date) -> tuple[datetime, datetime]:
    start = datetime.combine(session_date, _REGULAR_OPEN, tzinfo=_ET).astimezone(timezone.utc)
    end = datetime.combine(session_date, _REGULAR_CLOSE, tzinfo=_ET).astimezone(timezone.utc)
    return start, end


def _expected_last_start(
    session_date: date,
    observed_at: datetime,
    step: timedelta,
) -> datetime | None:
    start, end = _session_bounds(session_date)
    now = min(observed_at.astimezone(timezone.utc), end)
    if now <= start:
        return None
    seconds = int(step.total_seconds())
    elapsed = int((now - start).total_seconds())
    completed = elapsed // seconds
    if completed <= 0:
        return None
    return min(start + step * (completed - 1), end - step)


def _canonicalize(
    bars: list[MarketBar] | tuple[MarketBar, ...],
    *,
    interval: str,
    session_date: date,
    observed_at: datetime,
) -> list[MarketBar]:
    candidates = [
        bar
        for bar in bars
        if bar.is_final
        and bar.interval == interval
        and bar.session == "regular"
        and bar.start_time.astimezone(_ET).date() == session_date
        and bar.end_time.astimezone(timezone.utc) <= observed_at.astimezone(timezone.utc)
    ]
    by_window: dict[tuple[datetime, datetime], MarketBar] = {}
    for bar in candidates:
        key = (
            bar.start_time.astimezone(timezone.utc),
            bar.end_time.astimezone(timezone.utc),
        )
        prior = by_window.get(key)
        if prior is None:
            by_window[key] = bar
            continue
        prior_rank = (
            getattr(prior, "ingestion_revision", 1),
            getattr(prior, "received_at", prior.end_time),
            getattr(prior, "provider_sequence", None) or -1,
        )
        current_rank = (
            getattr(bar, "ingestion_revision", 1),
            getattr(bar, "received_at", bar.end_time),
            getattr(bar, "provider_sequence", None) or -1,
        )
        if current_rank > prior_rank:
            by_window[key] = bar
    return sorted(by_window.values(), key=lambda bar: bar.start_time)


def _missing_starts(
    bars: list[MarketBar],
    *,
    interval: str,
    session_date: date,
    observed_at: datetime,
) -> tuple[datetime, ...]:
    step = interval_duration(interval)
    last = _expected_last_start(session_date, observed_at, step)
    if last is None:
        return ()
    start, _ = _session_bounds(session_date)
    starts = {bar.start_time.astimezone(timezone.utc) for bar in bars}
    missing: list[datetime] = []
    cursor = start
    while cursor <= last:
        if cursor not in starts:
            missing.append(cursor)
        cursor += step
    return tuple(missing)


def _safe_fetch(
    fetcher: Callable[[], list[MarketBar] | tuple[MarketBar, ...]],
    *,
    stage: str,
    source: str,
) -> tuple[list[MarketBar], RecoveryAttempt]:
    try:
        values = list(fetcher())
    except Exception as exc:
        return [], RecoveryAttempt(
            stage=stage,
            source=source,
            succeeded=False,
            detail=f"{type(exc).__name__}: {exc}",
        )
    return values, RecoveryAttempt(
        stage=stage,
        source=source,
        succeeded=True,
        bar_count=len(values),
    )


def recover_market_bars(
    *,
    instrument_id: str,
    interval: str,
    session_date: date,
    observed_at: datetime,
    primary_fetch: Callable[[], list[MarketBar] | tuple[MarketBar, ...]],
    primary_source: str,
    primary_retry_fetch: Callable[[], list[MarketBar] | tuple[MarketBar, ...]] | None = None,
    fallback_fetch: Callable[[], list[MarketBar] | tuple[MarketBar, ...]] | None = None,
    fallback_source: str | None = None,
    lower_resolution_fetch: Callable[[], list[MarketBar] | tuple[MarketBar, ...]] | None = None,
    lower_resolution_source: str | None = None,
    confirm_nontrading: Callable[[datetime, datetime], bool] | None = None,
) -> RecoveredBarSeries:
    """Recover one canonical target interval through ordered, auditable stages."""

    if observed_at.tzinfo is None:
        raise ValueError("recovery clock must be timezone-aware")
    attempts: list[RecoveryAttempt] = []
    collected: list[MarketBar] = []

    primary, attempt = _safe_fetch(
        primary_fetch,
        stage="primary",
        source=primary_source,
    )
    attempts.append(attempt)
    collected.extend(primary)
    canonical = _canonicalize(
        collected,
        interval=interval,
        session_date=session_date,
        observed_at=observed_at,
    )
    missing = _missing_starts(
        canonical,
        interval=interval,
        session_date=session_date,
        observed_at=observed_at,
    )

    if missing and primary_retry_fetch is not None:
        retry, attempt = _safe_fetch(
            primary_retry_fetch,
            stage="primary_retry",
            source=primary_source,
        )
        attempts.append(attempt)
        collected.extend(retry)
        canonical = _canonicalize(
            collected,
            interval=interval,
            session_date=session_date,
            observed_at=observed_at,
        )
        missing = _missing_starts(
            canonical,
            interval=interval,
            session_date=session_date,
            observed_at=observed_at,
        )

    if missing and fallback_fetch is not None:
        fallback, attempt = _safe_fetch(
            fallback_fetch,
            stage="fallback",
            source=fallback_source or "fallback",
        )
        attempts.append(attempt)
        collected.extend(fallback)
        canonical = _canonicalize(
            collected,
            interval=interval,
            session_date=session_date,
            observed_at=observed_at,
        )
        missing = _missing_starts(
            canonical,
            interval=interval,
            session_date=session_date,
            observed_at=observed_at,
        )

    if missing and interval != "1m" and lower_resolution_fetch is not None:
        lower, attempt = _safe_fetch(
            lower_resolution_fetch,
            stage="lower_resolution_rebuild",
            source=lower_resolution_source or "lower_resolution",
        )
        rebuilt: list[MarketBar] = []
        if attempt.succeeded:
            try:
                rebuilt = resample_final_bars(lower, interval)
                attempt = attempt.model_copy(update={"bar_count": len(rebuilt)})
            except Exception as exc:
                attempt = attempt.model_copy(
                    update={
                        "succeeded": False,
                        "detail": f"{type(exc).__name__}: {exc}",
                    }
                )
        attempts.append(attempt)
        collected.extend(rebuilt)
        canonical = _canonicalize(
            collected,
            interval=interval,
            session_date=session_date,
            observed_at=observed_at,
        )
        missing = _missing_starts(
            canonical,
            interval=interval,
            session_date=session_date,
            observed_at=observed_at,
        )

    confirmed: list[datetime] = []
    unresolved: list[datetime] = []
    step = interval_duration(interval)
    if missing and confirm_nontrading is not None:
        for start in missing:
            try:
                is_nontrading = bool(confirm_nontrading(start, start + step))
            except Exception:
                is_nontrading = False
            if is_nontrading:
                confirmed.append(start)
            else:
                unresolved.append(start)
        attempts.append(
            RecoveryAttempt(
                stage="nontrading_confirmation",
                source="halt_or_no_trade_authority",
                succeeded=bool(confirmed),
                bar_count=len(confirmed),
                detail=None if confirmed else "no_missing_interval_confirmed",
            )
        )
    else:
        unresolved = list(missing)

    if not canonical:
        status: RecoveryStatus = "UNAVAILABLE"
    elif unresolved:
        status = "PARTIAL"
    else:
        status = "COMPLETE"
    providers = tuple(sorted({bar.provider for bar in canonical if bar.provider}))
    return RecoveredBarSeries(
        instrument_id=instrument_id,
        interval=interval,
        session_date=session_date,
        observed_at=observed_at,
        bars=tuple(canonical),
        status=status,
        unresolved_starts=tuple(unresolved),
        confirmed_nontrading_starts=tuple(confirmed),
        attempts=tuple(attempts),
        source_providers=providers,
    )


__all__ = [
    "RecoveredBarSeries",
    "RecoveryAttempt",
    "RecoveryStatus",
    "interval_duration",
    "recover_market_bars",
]
