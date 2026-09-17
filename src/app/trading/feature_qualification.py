from __future__ import annotations

"""Feature-local causal market-data qualification.

Recovery answers "what raw evidence can we obtain?"  This module answers the
separate strategy-facing question: "is this particular feature trustworthy for
this decision right now?"  Requirements declare their temporal dependency so an
old gap can heal for a rolling feature without silently healing session-wide or
recursive features.
"""

import hashlib
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any, Generic, Literal, TypeVar
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


_ET = ZoneInfo("America/New_York")
_REGULAR_OPEN = time(9, 30)
_REGULAR_CLOSE = time(16, 0)

FeatureDependencyClass = Literal[
    "POINT_IN_TIME",
    "ROLLING_WINDOW",
    "SESSION_CUMULATIVE",
    "SESSION_EXTREMA",
    "BASELINE_DEPENDENT",
    "RECURSIVE",
    "EVENT_SEQUENCE",
]
QualificationStatus = Literal["VALID", "DEGRADED", "INVALID"]

T = TypeVar("T")


class CoverageRange(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    start: datetime
    end: datetime
    source: str | None = None

    @field_validator("start", "end")
    @classmethod
    def _aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("coverage timestamps must be timezone-aware")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def _ordered(self):
        if self.end <= self.start:
            raise ValueError("coverage range end must be after start")
        return self


class FeatureRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    requirement_id: str
    feature_name: str
    interval: str = "1m"
    dependency_class: FeatureDependencyClass
    lookback_bars: int | None = Field(default=None, ge=1)
    max_staleness_seconds: int = Field(default=90, ge=0)
    source_policy: tuple[str, ...] = ()
    seed_at: datetime | None = None
    baseline_ready_required: bool = False
    allow_approximate_reseed: bool = False
    reseed_after_clean_bars: int | None = Field(default=None, ge=2)

    @field_validator("seed_at")
    @classmethod
    def _seed_aware(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("feature seed_at must be timezone-aware")
        return value.astimezone(timezone.utc) if value is not None else None

    @model_validator(mode="after")
    def _dependency_contract(self):
        if self.dependency_class == "ROLLING_WINDOW" and self.lookback_bars is None:
            raise ValueError("rolling requirements need lookback_bars")
        if self.allow_approximate_reseed and self.dependency_class != "RECURSIVE":
            raise ValueError("approximate reseed is only valid for recursive requirements")
        if self.allow_approximate_reseed and self.reseed_after_clean_bars is None:
            raise ValueError("approximate recursive reseed needs reseed_after_clean_bars")
        return self


class CoverageCertificate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    certificate_id: str
    requirement_id: str
    feature_name: str
    instrument_id: str
    interval: str
    dependency_class: FeatureDependencyClass
    evaluated_as_of: datetime
    required_start: datetime | None = None
    required_end: datetime | None = None
    coverage_start: datetime | None = None
    coverage_end: datetime | None = None
    unresolved_gaps: tuple[datetime, ...] = ()
    recovered_ranges: tuple[CoverageRange, ...] = ()
    confirmed_nontrading_ranges: tuple[CoverageRange, ...] = ()
    provider_set: tuple[str, ...] = ()
    status: QualificationStatus
    exact: bool = True
    reason_codes: tuple[str, ...] = ()

    @field_validator(
        "evaluated_as_of",
        "required_start",
        "required_end",
        "coverage_start",
        "coverage_end",
    )
    @classmethod
    def _aware_optional(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("certificate timestamps must be timezone-aware")
        return value.astimezone(timezone.utc)


class QualifiedValue(BaseModel, Generic[T]):
    model_config = ConfigDict(extra="forbid", frozen=True)

    feature_name: str
    value: T | None = None
    certificate_id: str
    status: QualificationStatus
    exact: bool = True
    computed_as_of: datetime
    reason_codes: tuple[str, ...] = ()

    @field_validator("computed_as_of")
    @classmethod
    def _computed_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("qualified value timestamp must be timezone-aware")
        return value.astimezone(timezone.utc)


def interval_duration(interval: str) -> timedelta:
    raw = interval.strip().lower()
    if raw.endswith("m") and raw[:-1].isdigit():
        return timedelta(minutes=int(raw[:-1]))
    if raw.endswith("h") and raw[:-1].isdigit():
        return timedelta(hours=int(raw[:-1]))
    raise ValueError(f"unsupported_feature_interval:{interval}")


def _floor_to_interval(value: datetime, step: timedelta) -> datetime:
    utc = value.astimezone(timezone.utc)
    seconds = int(step.total_seconds())
    epoch = int(utc.timestamp())
    return datetime.fromtimestamp(epoch - (epoch % seconds), tz=timezone.utc)


def _session_bounds(session_date: date) -> tuple[datetime, datetime]:
    start = datetime.combine(session_date, _REGULAR_OPEN, tzinfo=_ET).astimezone(timezone.utc)
    end = datetime.combine(session_date, _REGULAR_CLOSE, tzinfo=_ET).astimezone(timezone.utc)
    return start, end


def _latest_completed_start(
    observed_at: datetime,
    *,
    session_date: date,
    step: timedelta,
) -> datetime | None:
    start, end = _session_bounds(session_date)
    observed = observed_at.astimezone(timezone.utc)
    if observed <= start:
        return None
    bounded = min(observed, end)
    floored = _floor_to_interval(bounded, step)
    latest = floored - step
    return max(start, min(latest, end - step))


def _required_window(
    requirement: FeatureRequirement,
    *,
    session_date: date,
    observed_at: datetime,
) -> tuple[datetime | None, datetime | None]:
    step = interval_duration(requirement.interval)
    latest = _latest_completed_start(observed_at, session_date=session_date, step=step)
    if latest is None:
        return None, None
    session_start, _ = _session_bounds(session_date)

    if requirement.dependency_class == "POINT_IN_TIME":
        return latest, latest
    if requirement.dependency_class == "ROLLING_WINDOW":
        assert requirement.lookback_bars is not None
        start = latest - step * (requirement.lookback_bars - 1)
        return max(session_start, start), latest
    if requirement.dependency_class in {
        "SESSION_CUMULATIVE",
        "SESSION_EXTREMA",
        "BASELINE_DEPENDENT",
    }:
        return session_start, latest
    if requirement.dependency_class == "RECURSIVE":
        seed = requirement.seed_at or session_start
        return max(session_start, seed), latest
    if requirement.dependency_class == "EVENT_SEQUENCE":
        if requirement.lookback_bars is not None:
            start = latest - step * (requirement.lookback_bars - 1)
            return max(session_start, start), latest
        return session_start, latest
    raise ValueError(f"unsupported_feature_dependency:{requirement.dependency_class}")


def _certificate_id(
    requirement: FeatureRequirement,
    instrument_id: str,
    observed_at: datetime,
    status: QualificationStatus,
    gaps: tuple[datetime, ...],
    confirmed_nontrading: tuple[datetime, ...] = (),
) -> str:
    raw = "|".join(
        (
            requirement.requirement_id,
            instrument_id,
            observed_at.astimezone(timezone.utc).isoformat(),
            status,
            ",".join(item.isoformat() for item in gaps),
            ",".join(item.isoformat() for item in confirmed_nontrading),
        )
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def qualify_bar_feature(
    bars: list[Any] | tuple[Any, ...],
    requirement: FeatureRequirement,
    *,
    instrument_id: str,
    session_date: date,
    observed_at: datetime,
    recovered_ranges: tuple[CoverageRange, ...] = (),
    confirmed_nontrading_starts: tuple[datetime, ...] = (),
    baseline_ready: bool | None = None,
) -> CoverageCertificate:
    """Build a feature-specific coverage certificate from finalized bars.

    The function never turns a recovered or missing interval into synthetic data.
    A rolling requirement can become valid once an old gap leaves its declared
    window. Session-wide requirements cannot. Recursive requirements require
    continuous evidence from their seed unless an explicit approximate reseed
    policy is declared, in which case the certificate is DEGRADED rather than
    silently exact.
    """

    if observed_at.tzinfo is None:
        raise ValueError("feature qualification clock must be timezone-aware")
    step = interval_duration(requirement.interval)
    required_start, required_latest = _required_window(
        requirement,
        session_date=session_date,
        observed_at=observed_at,
    )

    filtered = sorted(
        [
            bar
            for bar in bars
            if getattr(bar, "is_final", False)
            and getattr(bar, "interval", requirement.interval) == requirement.interval
            and getattr(bar, "start_time", None) is not None
            and getattr(bar, "end_time", None) is not None
            and bar.end_time.astimezone(timezone.utc) <= observed_at.astimezone(timezone.utc)
            and bar.start_time.astimezone(_ET).date() == session_date
            and getattr(bar, "session", "regular") == "regular"
        ],
        key=lambda item: item.start_time,
    )
    starts = {bar.start_time.astimezone(timezone.utc) for bar in filtered}
    provider_set = tuple(
        sorted(
            {
                str(getattr(bar, "provider", "") or "")
                for bar in filtered
                if str(getattr(bar, "provider", "") or "")
            }
        )
    )

    reasons: list[str] = []
    exact = True
    gaps: list[datetime] = []
    confirmed_nontrading = {
        value.astimezone(timezone.utc)
        for value in confirmed_nontrading_starts
    }
    confirmed_in_window: list[datetime] = []

    if required_start is None or required_latest is None:
        reasons.append("FEATURE_WINDOW_NOT_STARTED")
    elif requirement.dependency_class == "POINT_IN_TIME":
        latest_bar = filtered[-1] if filtered else None
        if latest_bar is None:
            reasons.append("POINT_IN_TIME_OBSERVATION_MISSING")
        else:
            age = (
                observed_at.astimezone(timezone.utc)
                - latest_bar.end_time.astimezone(timezone.utc)
            ).total_seconds()
            if age > requirement.max_staleness_seconds:
                reasons.append("POINT_IN_TIME_OBSERVATION_STALE")
    else:
        cursor = required_start
        while cursor <= required_latest:
            if cursor not in starts:
                if cursor in confirmed_nontrading:
                    confirmed_in_window.append(cursor)
                else:
                    gaps.append(cursor)
            cursor += step
        if confirmed_in_window:
            reasons.append("FEATURE_WINDOW_CONFIRMED_NONTRADING")

    if requirement.source_policy and provider_set:
        if any(provider not in requirement.source_policy for provider in provider_set):
            reasons.append("FEATURE_SOURCE_POLICY_MISMATCH")

    if requirement.baseline_ready_required and baseline_ready is not True:
        reasons.append("FEATURE_BASELINE_UNAVAILABLE")

    if gaps and requirement.dependency_class == "RECURSIVE":
        if requirement.allow_approximate_reseed and requirement.reseed_after_clean_bars:
            clean_needed = requirement.reseed_after_clean_bars
            clean_start = required_latest - step * (clean_needed - 1)
            clean = True
            cursor = clean_start
            while cursor <= required_latest:
                if cursor not in starts:
                    clean = False
                    break
                cursor += step
            if clean:
                exact = False
                reasons.append("RECURSIVE_RESEEDED_APPROXIMATE")
                gaps = []
            else:
                reasons.append("RECURSIVE_SEED_CONTINUITY_BROKEN")
        else:
            reasons.append("RECURSIVE_SEED_CONTINUITY_BROKEN")
    elif gaps:
        reasons.append("FEATURE_WINDOW_HAS_GAPS")

    informational_reasons = {"FEATURE_WINDOW_CONFIRMED_NONTRADING"}
    invalid_reasons = [
        reason
        for reason in reasons
        if reason not in informational_reasons
        and reason != "RECURSIVE_RESEEDED_APPROXIMATE"
    ]
    if invalid_reasons:
        status: QualificationStatus = "INVALID"
    elif "RECURSIVE_RESEEDED_APPROXIMATE" in reasons:
        status = "DEGRADED"
    else:
        status = "VALID"

    coverage_start = filtered[0].start_time if filtered else None
    coverage_end = filtered[-1].end_time if filtered else None
    unresolved = tuple(gaps)
    return CoverageCertificate(
        certificate_id=_certificate_id(
            requirement,
            instrument_id,
            observed_at,
            status,
            unresolved,
            tuple(confirmed_in_window),
        ),
        requirement_id=requirement.requirement_id,
        feature_name=requirement.feature_name,
        instrument_id=instrument_id,
        interval=requirement.interval,
        dependency_class=requirement.dependency_class,
        evaluated_as_of=observed_at,
        required_start=required_start,
        required_end=(
            required_latest + step if required_latest is not None else None
        ),
        coverage_start=coverage_start,
        coverage_end=coverage_end,
        unresolved_gaps=unresolved,
        recovered_ranges=recovered_ranges,
        confirmed_nontrading_ranges=tuple(
            CoverageRange(
                start=start,
                end=start + step,
                source="confirmed_nontrading",
            )
            for start in confirmed_in_window
        ),
        provider_set=provider_set,
        status=status,
        exact=exact,
        reason_codes=tuple(dict.fromkeys(reasons)),
    )


def qualify_value(
    value: T | None,
    certificate: CoverageCertificate,
    *,
    computed_as_of: datetime,
) -> QualifiedValue[T]:
    if certificate.status == "INVALID":
        value = None
    return QualifiedValue[T](
        feature_name=certificate.feature_name,
        value=value,
        certificate_id=certificate.certificate_id,
        status=certificate.status,
        exact=certificate.exact,
        computed_as_of=computed_as_of,
        reason_codes=certificate.reason_codes,
    )


def certificates_authorize(
    certificates: list[CoverageCertificate] | tuple[CoverageCertificate, ...],
    *,
    allow_degraded: bool = False,
) -> tuple[bool, tuple[str, ...]]:
    allowed = {"VALID", "DEGRADED"} if allow_degraded else {"VALID"}
    failed = [
        certificate
        for certificate in certificates
        if certificate.status not in allowed
    ]
    reasons = tuple(
        dict.fromkeys(
            reason
            for certificate in failed
            for reason in certificate.reason_codes
        )
    )
    return not failed, reasons


__all__ = [
    "CoverageCertificate",
    "CoverageRange",
    "FeatureDependencyClass",
    "FeatureRequirement",
    "QualifiedValue",
    "QualificationStatus",
    "certificates_authorize",
    "interval_duration",
    "qualify_bar_feature",
    "qualify_value",
]
