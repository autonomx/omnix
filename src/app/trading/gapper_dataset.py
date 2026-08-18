from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class GapperCandidate(BaseModel):
    """Point-in-time candidate evidence used by research/backtests and paper runs."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    instrument_id: str = Field(min_length=3, max_length=200)
    binding_id: str | None = Field(default=None, max_length=240)
    previous_close: Decimal = Field(gt=0)
    premarket_price: Decimal = Field(gt=0)
    gap_pct: Decimal
    premarket_volume: Decimal = Field(default=Decimal("0"), ge=0)
    premarket_dollar_volume: Decimal = Field(default=Decimal("0"), ge=0)
    tod_rvol: Decimal | None = Field(default=None, ge=0)
    market_cap: Decimal | None = Field(default=None, ge=0)
    float_shares: Decimal | None = Field(default=None, gt=0)
    spread_bps: Decimal | None = Field(default=None, ge=0)
    catalyst_evidence_ids: tuple[str, ...] = ()
    dilution_flags: tuple[str, ...] = ()
    discovery_rank: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_gap(self):
        implied = (self.premarket_price / self.previous_close - Decimal("1")) * Decimal("100")
        if abs(implied - self.gap_pct) > Decimal("0.25"):
            raise ValueError("gap_pct does not match point-in-time previous_close/premarket_price")
        return self


class GapperUniverseSnapshot(BaseModel):
    """Immutable daily candidate universe, including eventual failures/fades."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    universe_id: str = Field(min_length=1, max_length=200)
    session_date: date
    evaluation_time: datetime
    discovery_source: Literal["manual", "import", "scanner", "provider"]
    candidates: tuple[GapperCandidate, ...]
    source_fingerprint: str = Field(min_length=64, max_length=64)

    @field_validator("evaluation_time")
    @classmethod
    def timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("evaluation_time must be timezone-aware")
        return value.astimezone(timezone.utc)


def gapper_universe_fingerprint(
    *,
    universe_id: str,
    session_date: date,
    evaluation_time: datetime,
    discovery_source: str,
    candidates: tuple[GapperCandidate, ...] | list[GapperCandidate],
) -> str:
    ordered = sorted(candidates, key=lambda item: (item.discovery_rank or 10**9, item.instrument_id))
    payload = {
        "universe_id": universe_id,
        "session_date": session_date.isoformat(),
        "evaluation_time": evaluation_time.astimezone(timezone.utc).isoformat(),
        "discovery_source": discovery_source,
        "candidates": [candidate.model_dump(mode="json") for candidate in ordered],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def freeze_gapper_universe(
    *,
    universe_id: str,
    session_date: date,
    evaluation_time: datetime,
    discovery_source: Literal["manual", "import", "scanner", "provider"],
    candidates: list[GapperCandidate] | tuple[GapperCandidate, ...],
) -> GapperUniverseSnapshot:
    ordered = tuple(sorted(candidates, key=lambda item: (item.discovery_rank or 10**9, item.instrument_id)))
    fingerprint = gapper_universe_fingerprint(
        universe_id=universe_id,
        session_date=session_date,
        evaluation_time=evaluation_time,
        discovery_source=discovery_source,
        candidates=ordered,
    )
    return GapperUniverseSnapshot(
        universe_id=universe_id,
        session_date=session_date,
        evaluation_time=evaluation_time,
        discovery_source=discovery_source,
        candidates=ordered,
        source_fingerprint=fingerprint,
    )
