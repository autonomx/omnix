from __future__ import annotations

"""Provider-neutral causal acquisition contracts for dynamic discovery."""

from datetime import date, datetime, timezone
from decimal import Decimal
from threading import RLock
from typing import Protocol

from pydantic import BaseModel, ConfigDict, field_validator

from .finviz_gapper_discovery import discover_finviz_gappers
from .strategy_dynamic_discovery import MarketAnomalyFeatures


class CausalMarketObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    instrument_id: str
    session_date: date
    observed_at: datetime
    source: str
    source_locator: str | None = None
    market: MarketAnomalyFeatures | None = None
    catalyst_payload: dict[str, object] | None = None
    candidate_payload: dict[str, object] | None = None
    catalyst_known: bool = False

    @field_validator("observed_at")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("causal_observation_requires_timezone")
        return value.astimezone(timezone.utc)


class DiscoveryAcquisitionSource(Protocol):
    name: str

    def capture(self, *, observed_at: datetime) -> tuple[CausalMarketObservation, ...]: ...


class FinvizLiveLeaderSource:
    name = "finviz_live_leaders"

    def __init__(self, *, count: int = 20) -> None:
        self.count = max(5, min(20, int(count)))

    def capture(self, *, observed_at: datetime) -> tuple[CausalMarketObservation, ...]:
        snapshot = discover_finviz_gappers(
            universe_id=f"dynamic-{observed_at.astimezone(timezone.utc).strftime('%Y%m%dT%H%M%S')}",
            evaluation_time=observed_at,
            count=self.count,
            minimum_gap_pct=Decimal("0"),
            minimum_price=Decimal("0.10"),
            maximum_price=Decimal("250"),
            membership_only=True,
        )
        rows: list[CausalMarketObservation] = []
        for candidate in snapshot.candidates:
            observed = candidate.observed_at or snapshot.evaluation_time
            volume_to_float = None
            if candidate.float_shares is not None and candidate.float_shares > 0:
                volume_to_float = float(candidate.premarket_volume / candidate.float_shares)
            rows.append(
                CausalMarketObservation(
                    instrument_id=candidate.instrument_id,
                    session_date=snapshot.session_date,
                    observed_at=observed,
                    source=self.name,
                    source_locator=snapshot.source_locator,
                    market=MarketAnomalyFeatures(
                        observed_at=observed,
                        gap_pct=float(candidate.gap_pct),
                        tod_rvol=float(candidate.tod_rvol) if candidate.tod_rvol is not None else None,
                        volume_to_float=volume_to_float,
                        dollar_volume=float(candidate.premarket_dollar_volume),
                        spread_bps=float(candidate.spread_bps) if candidate.spread_bps is not None else None,
                    ),
                    candidate_payload=candidate.model_dump(mode="json"),
                    catalyst_known=bool(candidate.catalyst_evidence_ids),
                )
            )
        return tuple(rows)


_SOURCE_LOCK = RLock()
_REGISTERED_SOURCES: dict[str, DiscoveryAcquisitionSource] = {}


def register_discovery_acquisition_source(source: DiscoveryAcquisitionSource) -> None:
    name = str(getattr(source, "name", "")).strip()
    if not name:
        raise ValueError("discovery_source_requires_name")
    with _SOURCE_LOCK:
        _REGISTERED_SOURCES[name] = source


def unregister_discovery_acquisition_source(name: str) -> None:
    with _SOURCE_LOCK:
        _REGISTERED_SOURCES.pop(str(name), None)


def registered_discovery_sources() -> tuple[DiscoveryAcquisitionSource, ...]:
    with _SOURCE_LOCK:
        return tuple(_REGISTERED_SOURCES[key] for key in sorted(_REGISTERED_SOURCES))


def install_default_discovery_sources() -> None:
    with _SOURCE_LOCK:
        if FinvizLiveLeaderSource.name not in _REGISTERED_SOURCES:
            _REGISTERED_SOURCES[FinvizLiveLeaderSource.name] = FinvizLiveLeaderSource()


def capture_discovery_observations(*, observed_at: datetime) -> tuple[CausalMarketObservation, ...]:
    rows: list[CausalMarketObservation] = []
    for source in registered_discovery_sources():
        rows.extend(source.capture(observed_at=observed_at))
    rows.sort(key=lambda row: (row.observed_at, row.source, row.instrument_id))
    return tuple(rows)


__all__ = [
    "CausalMarketObservation",
    "DiscoveryAcquisitionSource",
    "FinvizLiveLeaderSource",
    "capture_discovery_observations",
    "install_default_discovery_sources",
    "register_discovery_acquisition_source",
    "registered_discovery_sources",
    "unregister_discovery_acquisition_source",
]
