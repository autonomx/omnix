from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .models import BarsResponse, MarketBar


GapPolicy = Literal["fail", "skip"]


class FrozenBar(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    instrument_id: str
    interval: str
    start_time: datetime
    end_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    is_final: bool
    adjustment_mode: str
    session: str
    provider: str
    provider_event_id: str | None = None
    provider_sequence: int | None = None
    ingestion_revision: int = 1
    received_at: datetime

    @classmethod
    def from_market_bar(cls, bar: MarketBar) -> "FrozenBar":
        return cls.model_validate(bar.model_dump())


class FrozenDatasetSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    dataset_id: str
    instrument_id: str
    requested_binding_id: str | None = None
    resolved_binding_id: str
    provider: str
    interval: str
    adjustment_mode: str
    session_calendar: str
    exchange_timezone: str
    gap_policy: GapPolicy
    dataset_fingerprint: str
    source_as_of: datetime
    bars: tuple[FrozenBar, ...] = Field(min_length=1, max_length=5_000)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @model_validator(mode="after")
    def validate_snapshot(self):
        if any(not bar.is_final for bar in self.bars):
            raise ValueError("frozen datasets require finalized bars")
        if any(bar.instrument_id != self.instrument_id for bar in self.bars):
            raise ValueError("frozen dataset bars must share one canonical instrument")
        if any(bar.interval != self.interval for bar in self.bars):
            raise ValueError("frozen dataset bars must share one interval")
        if tuple(sorted(self.bars, key=lambda bar: bar.start_time)) != self.bars:
            raise ValueError("frozen dataset bars must be ordered")
        gaps = dataset_gaps(self.bars, self.interval)
        if gaps and self.gap_policy == "fail":
            raise ValueError(f"frozen dataset contains {len(gaps)} gap(s)")
        expected = frozen_dataset_fingerprint(
            instrument_id=self.instrument_id,
            resolved_binding_id=self.resolved_binding_id,
            provider=self.provider,
            interval=self.interval,
            adjustment_mode=self.adjustment_mode,
            session_calendar=self.session_calendar,
            exchange_timezone=self.exchange_timezone,
            gap_policy=self.gap_policy,
            bars=self.bars,
        )
        if self.dataset_fingerprint != expected:
            raise ValueError("frozen dataset fingerprint mismatch")
        return self


class ReplayEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    sequence: int
    replay_time: datetime
    bar: FrozenBar


_INTERVAL_SECONDS = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "1h": 3_600,
    "4h": 14_400,
    "1d": 86_400,
    "1mo": 2_592_000,
}


def interval_seconds(interval: str) -> int:
    try:
        return _INTERVAL_SECONDS[interval]
    except KeyError as exc:
        raise ValueError(f"unsupported replay interval: {interval}") from exc


def dataset_gaps(
    bars: tuple[FrozenBar, ...] | list[FrozenBar],
    interval: str,
) -> list[tuple[datetime, datetime]]:
    expected = timedelta(seconds=interval_seconds(interval))
    return [
        (previous.end_time, current.start_time)
        for previous, current in zip(bars, bars[1:])
        if current.start_time - previous.start_time != expected
    ]


def frozen_dataset_fingerprint(
    *,
    instrument_id: str,
    resolved_binding_id: str,
    provider: str,
    interval: str,
    adjustment_mode: str,
    session_calendar: str,
    exchange_timezone: str,
    gap_policy: GapPolicy,
    bars: tuple[FrozenBar, ...] | list[FrozenBar],
) -> str:
    payload = {
        "instrument_id": instrument_id,
        "resolved_binding_id": resolved_binding_id,
        "provider": provider,
        "interval": interval,
        "adjustment_mode": adjustment_mode,
        "session_calendar": session_calendar,
        "exchange_timezone": exchange_timezone,
        "gap_policy": gap_policy,
        "bars": [bar.model_dump(mode="json") for bar in bars],
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def freeze_bars_response(
    *,
    dataset_id: str,
    response: BarsResponse,
    requested_binding_id: str | None,
    gap_policy: GapPolicy,
) -> FrozenDatasetSnapshot:
    bars = tuple(
        FrozenBar.from_market_bar(bar)
        for bar in response.bars
        if bar.is_final
    )
    if not bars:
        raise ValueError("cannot freeze an empty finalized dataset")
    fingerprint = frozen_dataset_fingerprint(
        instrument_id=response.instrument.instrument_id,
        resolved_binding_id=response.binding.binding_id,
        provider=response.binding.provider,
        interval=response.interval,
        adjustment_mode=bars[0].adjustment_mode,
        session_calendar=response.instrument.session_calendar,
        exchange_timezone=response.instrument.exchange_timezone,
        gap_policy=gap_policy,
        bars=bars,
    )
    return FrozenDatasetSnapshot(
        dataset_id=dataset_id,
        instrument_id=response.instrument.instrument_id,
        requested_binding_id=requested_binding_id,
        resolved_binding_id=response.binding.binding_id,
        provider=response.binding.provider,
        interval=response.interval,
        adjustment_mode=bars[0].adjustment_mode,
        session_calendar=response.instrument.session_calendar,
        exchange_timezone=response.instrument.exchange_timezone,
        gap_policy=gap_policy,
        dataset_fingerprint=fingerprint,
        source_as_of=response.provenance.as_of,
        bars=bars,
    )


class ReplayClock:
    def __init__(self, snapshot: FrozenDatasetSnapshot) -> None:
        self.snapshot = snapshot
        self.index = -1
        self.paused = True
        self.speed = Decimal("1")

    def set_speed(self, speed: Decimal | int | float | str) -> None:
        value = Decimal(str(speed))
        if value <= 0 or value > 100:
            raise ValueError("replay speed must be greater than zero and at most 100")
        self.speed = value

    def play(self) -> None:
        self.paused = False

    def pause(self) -> None:
        self.paused = True

    def reset(self) -> None:
        self.index = -1
        self.paused = True

    def step(self, count: int = 1) -> list[ReplayEvent]:
        if count < 1 or count > 1_000:
            raise ValueError("replay step count must be between 1 and 1000")
        events: list[ReplayEvent] = []
        for _ in range(count):
            if self.index + 1 >= len(self.snapshot.bars):
                break
            self.index += 1
            bar = self.snapshot.bars[self.index]
            events.append(
                ReplayEvent(
                    sequence=self.index,
                    replay_time=bar.end_time,
                    bar=bar,
                )
            )
        return events

    def tick(self) -> ReplayEvent | None:
        if self.paused:
            return None
        events = self.step(1)
        if not events:
            self.pause()
            return None
        return events[0]

    @property
    def finished(self) -> bool:
        return self.index >= len(self.snapshot.bars) - 1
