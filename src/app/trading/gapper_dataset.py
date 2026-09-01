from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class GapperCandidate(BaseModel):
    """Point-in-time candidate evidence used by research/backtests and paper runs.

    `previous_close` is always the split/corporate-action-normalized close in the
    same share basis as `premarket_price`. When raw evidence is available it is
    preserved separately with the adjustment factor so the gap can be audited.

    `observed_at` records when the candidate snapshot itself was observable.
    `evidence_observed_at` can additionally timestamp fields sourced from separate
    requests. Freeze validation rejects any timestamp later than the universe
    evaluation time so historical universes cannot silently absorb future facts.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    instrument_id: str = Field(min_length=3, max_length=200)
    binding_id: str | None = Field(default=None, max_length=240)
    observed_at: datetime | None = None
    evidence_observed_at: dict[str, datetime] = Field(default_factory=dict)
    previous_close: Decimal = Field(gt=0)
    raw_previous_close: Decimal | None = Field(default=None, gt=0)
    split_adjustment_factor: Decimal = Field(default=Decimal("1"), gt=0)
    corporate_action_evidence_ids: tuple[str, ...] = ()
    premarket_price: Decimal = Field(gt=0)
    gap_pct: Decimal
    premarket_volume: Decimal = Field(default=Decimal("0"), ge=0)
    premarket_dollar_volume: Decimal = Field(default=Decimal("0"), ge=0)
    premarket_bar_count: int | None = Field(default=None, ge=0)
    tod_rvol: Decimal | None = Field(default=None, ge=0)
    market_data_complete: bool = True
    data_quality_flags: tuple[str, ...] = ()
    market_cap: Decimal | None = Field(default=None, ge=0)
    float_shares: Decimal | None = Field(default=None, gt=0)
    spread_bps: Decimal | None = Field(default=None, ge=0)
    catalyst_evidence_ids: tuple[str, ...] = ()
    dilution_flags: tuple[str, ...] = ()
    discovery_rank: int | None = Field(default=None, ge=1)

    @field_validator("observed_at")
    @classmethod
    def observed_at_aware(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("candidate observed_at must be timezone-aware")
        return value.astimezone(timezone.utc)

    @field_validator("evidence_observed_at")
    @classmethod
    def evidence_times_aware(cls, value: dict[str, datetime]) -> dict[str, datetime]:
        normalized: dict[str, datetime] = {}
        for key, observed_at in value.items():
            clean = str(key).strip()
            if not clean:
                raise ValueError("evidence_observed_at keys cannot be empty")
            if observed_at.tzinfo is None:
                raise ValueError("candidate evidence timestamps must be timezone-aware")
            normalized[clean] = observed_at.astimezone(timezone.utc)
        return normalized

    @model_validator(mode="after")
    def validate_gap_and_adjustment(self):
        if self.raw_previous_close is not None:
            adjusted = self.raw_previous_close * self.split_adjustment_factor
            tolerance = max(Decimal("0.0001"), self.previous_close * Decimal("0.0001"))
            if abs(adjusted - self.previous_close) > tolerance:
                raise ValueError(
                    "previous_close must equal raw_previous_close * split_adjustment_factor"
                )
            if self.split_adjustment_factor != Decimal("1") and not self.corporate_action_evidence_ids:
                raise ValueError("non-unit split adjustment requires corporate_action_evidence_ids")
        elif self.split_adjustment_factor != Decimal("1"):
            raise ValueError("non-unit split adjustment requires raw_previous_close")
        implied = (self.premarket_price / self.previous_close - Decimal("1")) * Decimal("100")
        if abs(implied - self.gap_pct) > Decimal("0.25"):
            raise ValueError("gap_pct does not match normalized previous_close/premarket_price")
        if self.market_data_complete and self.data_quality_flags:
            raise ValueError("market_data_complete cannot be true when data_quality_flags are present")
        return self


class GapperUniverseSnapshot(BaseModel):
    """Immutable daily candidate universe, including eventual failures/fades.

    An empty candidate tuple is valid only when produced by a trusted archival
    path that explicitly records a completed morning scan with zero qualifying
    names. Interactive/manual freeze endpoints keep requiring at least one name.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    universe_id: str = Field(min_length=1, max_length=200)
    session_date: date
    evaluation_time: datetime
    discovery_source: Literal["manual", "import", "scanner", "provider", "finviz"]
    source_locator: str | None = Field(default=None, max_length=2000)
    source_candidate_symbols: tuple[str, ...] = ()
    candidates: tuple[GapperCandidate, ...]
    source_fingerprint: str = Field(min_length=64, max_length=64)

    @field_validator("evaluation_time")
    @classmethod
    def timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("evaluation_time must be timezone-aware")
        return value.astimezone(timezone.utc)


def time_of_day_relative_volume(
    current_cumulative_volume: Decimal | int | str,
    historical_cumulative_volumes: list[Decimal | int | str] | tuple[Decimal | int | str, ...],
) -> Decimal | None:
    """Current cumulative volume / historical mean at the same clock minute."""
    current = Decimal(str(current_cumulative_volume))
    samples = [Decimal(str(value)) for value in historical_cumulative_volumes]
    samples = [value for value in samples if value >= 0]
    if current < 0:
        raise ValueError("current cumulative volume cannot be negative")
    if not samples:
        return None
    baseline = sum(samples, Decimal("0")) / Decimal(len(samples))
    if baseline <= 0:
        return None
    return current / baseline


def _validate_point_in_time_candidate(
    candidate: GapperCandidate,
    *,
    evaluation_time: datetime,
    discovery_source: str,
) -> None:
    evaluation = evaluation_time.astimezone(timezone.utc)
    if candidate.observed_at is not None and candidate.observed_at > evaluation:
        raise ValueError(f"candidate observation occurs after universe freeze: {candidate.instrument_id}")
    if discovery_source in {"scanner", "provider", "finviz"} and candidate.observed_at is None:
        raise ValueError(
            f"provider/scanner candidate requires observed_at: {candidate.instrument_id}"
        )
    for field, observed_at in candidate.evidence_observed_at.items():
        if observed_at > evaluation:
            raise ValueError(
                f"candidate evidence occurs after universe freeze: {candidate.instrument_id}:{field}"
            )


def gapper_universe_fingerprint(
    *,
    universe_id: str,
    session_date: date,
    evaluation_time: datetime,
    discovery_source: str,
    candidates: tuple[GapperCandidate, ...] | list[GapperCandidate],
    source_locator: str | None = None,
    source_candidate_symbols: tuple[str, ...] | list[str] = (),
) -> str:
    ordered = sorted(candidates, key=lambda item: (item.discovery_rank or 10**9, item.instrument_id))
    payload = {
        "universe_id": universe_id,
        "session_date": session_date.isoformat(),
        "evaluation_time": evaluation_time.astimezone(timezone.utc).isoformat(),
        "discovery_source": discovery_source,
        "candidates": [candidate.model_dump(mode="json") for candidate in ordered],
    }
    # Keep fingerprints for pre-0049 universes stable. Discovery provenance only
    # participates in the fingerprint when it was actually captured.
    if source_locator is not None or source_candidate_symbols:
        payload["source_locator"] = source_locator
        payload["source_candidate_symbols"] = list(source_candidate_symbols)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def freeze_gapper_universe(
    *,
    universe_id: str,
    session_date: date,
    evaluation_time: datetime,
    discovery_source: Literal["manual", "import", "scanner", "provider", "finviz"],
    candidates: list[GapperCandidate] | tuple[GapperCandidate, ...],
    source_locator: str | None = None,
    source_candidate_symbols: list[str] | tuple[str, ...] = (),
    allow_empty: bool = False,
) -> GapperUniverseSnapshot:
    if not candidates and not allow_empty:
        raise ValueError("gapper universe requires at least one candidate")
    if evaluation_time.tzinfo is None:
        raise ValueError("evaluation_time must be timezone-aware")
    for candidate in candidates:
        _validate_point_in_time_candidate(
            candidate,
            evaluation_time=evaluation_time,
            discovery_source=discovery_source,
        )
    ordered = tuple(sorted(candidates, key=lambda item: (item.discovery_rank or 10**9, item.instrument_id)))
    fingerprint = gapper_universe_fingerprint(
        universe_id=universe_id,
        session_date=session_date,
        evaluation_time=evaluation_time,
        discovery_source=discovery_source,
        candidates=ordered,
        source_locator=source_locator,
        source_candidate_symbols=source_candidate_symbols,
    )
    return GapperUniverseSnapshot(
        universe_id=universe_id,
        session_date=session_date,
        evaluation_time=evaluation_time,
        discovery_source=discovery_source,
        source_locator=source_locator,
        source_candidate_symbols=tuple(source_candidate_symbols),
        candidates=ordered,
        source_fingerprint=fingerprint,
    )
