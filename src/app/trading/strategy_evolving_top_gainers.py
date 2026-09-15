from __future__ import annotations

"""Causal replay primitives for an evolving intraday Top-Gainers universe.

The live interday discovery loop refreshes market leadership throughout the
session. Historical research therefore must not freeze candidate membership at
a single morning timestamp. This module reconstructs a changing Top-N ranking
from evidence available at each observation time and records when symbols first
become discoverable.

Outcome labels (for example, end-of-day Top-5 membership) intentionally do not
appear in these contracts. They belong downstream, after the causal ranking
stream has been frozen and fingerprinted.
"""

import hashlib
import json
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Literal, Mapping, Sequence
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .models import MarketBar
from . import strategy_leader_momentum_continuation as leader


_ET = ZoneInfo("America/New_York")


class EvolvingTopGainersConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    top_n: int = Field(default=20, ge=5, le=100)
    cadence_minutes: int = Field(default=5, ge=1, le=30)
    first_evaluation_et: time = time(9, 35)
    last_evaluation_et: time = time(15, 30)
    minimum_price: Decimal = Field(default=Decimal("0.10"), gt=0)
    maximum_price: Decimal = Field(default=Decimal("250"), gt=0)
    minimum_gain_pct: Decimal = Decimal("0")
    # None matches a leaderboard that retains the latest printed price through
    # halts/no-print intervals. Set a finite value only when the source itself
    # has an explicit freshness contract.
    max_staleness_minutes: int | None = Field(default=None, ge=1, le=390)

    @model_validator(mode="after")
    def validate_bounds(self):
        if self.maximum_price < self.minimum_price:
            raise ValueError("top_gainers_maximum_price_below_minimum")
        if self.last_evaluation_et < self.first_evaluation_et:
            raise ValueError("top_gainers_evaluation_window_invalid")
        return self


class TopGainerObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    instrument_id: str = Field(min_length=3, max_length=200)
    observed_at: datetime
    price: Decimal = Field(gt=0)
    previous_close: Decimal = Field(gt=0)
    cumulative_dollar_volume: Decimal = Field(default=Decimal("0"), ge=0)
    source: str = Field(default="historical_bar_reconstruction", min_length=1)

    @field_validator("observed_at")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("top_gainer_observation_requires_timezone")
        return value.astimezone(timezone.utc)

    @property
    def gain_pct(self) -> Decimal:
        return (self.price / self.previous_close - Decimal("1")) * Decimal("100")


class TopGainerMember(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    instrument_id: str
    rank: int = Field(ge=1)
    gain_pct: Decimal
    price: Decimal = Field(gt=0)
    previous_close: Decimal = Field(gt=0)
    cumulative_dollar_volume: Decimal = Field(ge=0)
    evidence_at: datetime


class TopGainerSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    observed_at: datetime
    members: tuple[TopGainerMember, ...] = ()


MembershipTransitionKind = Literal["entered", "reentered", "exited"]


class TopGainerMembershipTransition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    instrument_id: str
    observed_at: datetime
    kind: MembershipTransitionKind
    rank: int | None = Field(default=None, ge=1)
    gain_pct: Decimal | None = None


class TopGainerMembershipSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    instrument_id: str
    first_top_n_at: datetime
    first_top_10_at: datetime | None = None
    first_top_5_at: datetime | None = None
    best_rank: int = Field(ge=1)
    entry_count: int = Field(default=1, ge=1)
    last_seen_at: datetime


class EvolvingTopGainersReplay(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    session_date: date
    config: EvolvingTopGainersConfig
    observation_count: int = Field(ge=0)
    snapshots: tuple[TopGainerSnapshot, ...] = ()
    membership: tuple[TopGainerMembershipSummary, ...] = ()
    transitions: tuple[TopGainerMembershipTransition, ...] = ()
    union_instrument_ids: tuple[str, ...] = ()
    fingerprint: str
    execution_authority: Literal[False] = False

    def membership_for(self, instrument_id: str) -> TopGainerMembershipSummary | None:
        return next(
            (row for row in self.membership if row.instrument_id == instrument_id),
            None,
        )


def _fingerprint(
    *,
    session_date: date,
    observations: Sequence[TopGainerObservation],
    config: EvolvingTopGainersConfig,
) -> str:
    payload = {
        "session_date": session_date.isoformat(),
        "config": config.model_dump(mode="json"),
        "observations": [row.model_dump(mode="json") for row in observations],
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def replay_evolving_top_gainers(
    *,
    session_date: date,
    observations: Sequence[TopGainerObservation],
    config: EvolvingTopGainersConfig = EvolvingTopGainersConfig(),
) -> EvolvingTopGainersReplay:
    """Replay changing Top-N membership without any end-of-day outcome input."""

    ordered = sorted(
        observations,
        key=lambda row: (row.observed_at, row.instrument_id, row.source),
    )
    grouped: dict[datetime, list[TopGainerObservation]] = defaultdict(list)
    for row in ordered:
        if row.observed_at.astimezone(_ET).date() != session_date:
            raise ValueError("top_gainer_observation_outside_exchange_session")
        grouped[row.observed_at].append(row)

    latest: dict[str, TopGainerObservation] = {}
    snapshots: list[TopGainerSnapshot] = []
    transitions: list[TopGainerMembershipTransition] = []
    previous_members: set[str] = set()
    ever_members: set[str] = set()
    summary: dict[str, dict[str, object]] = {}

    for observed_at in sorted(grouped):
        for row in grouped[observed_at]:
            latest[row.instrument_id] = row

        eligible: list[TopGainerObservation] = []
        for row in latest.values():
            if not (config.minimum_price <= row.price <= config.maximum_price):
                continue
            if row.gain_pct < config.minimum_gain_pct:
                continue
            if config.max_staleness_minutes is not None:
                age = observed_at - row.observed_at
                if age > timedelta(minutes=config.max_staleness_minutes):
                    continue
            eligible.append(row)

        eligible.sort(
            key=lambda row: (
                -row.gain_pct,
                -row.cumulative_dollar_volume,
                row.instrument_id,
            )
        )
        selected = eligible[: config.top_n]
        members = tuple(
            TopGainerMember(
                instrument_id=row.instrument_id,
                rank=index,
                gain_pct=row.gain_pct,
                price=row.price,
                previous_close=row.previous_close,
                cumulative_dollar_volume=row.cumulative_dollar_volume,
                evidence_at=row.observed_at,
            )
            for index, row in enumerate(selected, start=1)
        )
        snapshots.append(TopGainerSnapshot(observed_at=observed_at, members=members))

        current_members = {row.instrument_id for row in members}
        member_by_id = {row.instrument_id: row for row in members}
        for instrument_id in sorted(current_members - previous_members):
            member = member_by_id[instrument_id]
            kind: MembershipTransitionKind = (
                "reentered" if instrument_id in ever_members else "entered"
            )
            transitions.append(
                TopGainerMembershipTransition(
                    instrument_id=instrument_id,
                    observed_at=observed_at,
                    kind=kind,
                    rank=member.rank,
                    gain_pct=member.gain_pct,
                )
            )
            if instrument_id not in summary:
                summary[instrument_id] = {
                    "first_top_n_at": observed_at,
                    "first_top_10_at": observed_at if member.rank <= 10 else None,
                    "first_top_5_at": observed_at if member.rank <= 5 else None,
                    "best_rank": member.rank,
                    "entry_count": 1,
                    "last_seen_at": observed_at,
                }
            else:
                summary[instrument_id]["entry_count"] = int(
                    summary[instrument_id]["entry_count"]
                ) + 1
        for instrument_id in sorted(previous_members - current_members):
            transitions.append(
                TopGainerMembershipTransition(
                    instrument_id=instrument_id,
                    observed_at=observed_at,
                    kind="exited",
                )
            )
        for member in members:
            state = summary[member.instrument_id]
            state["last_seen_at"] = observed_at
            state["best_rank"] = min(int(state["best_rank"]), member.rank)
            if member.rank <= 10 and state["first_top_10_at"] is None:
                state["first_top_10_at"] = observed_at
            if member.rank <= 5 and state["first_top_5_at"] is None:
                state["first_top_5_at"] = observed_at

        ever_members.update(current_members)
        previous_members = current_members

    membership = tuple(
        TopGainerMembershipSummary(instrument_id=instrument_id, **values)
        for instrument_id, values in sorted(
            summary.items(),
            key=lambda item: (item[1]["first_top_n_at"], item[0]),
        )
    )
    return EvolvingTopGainersReplay(
        session_date=session_date,
        config=config,
        observation_count=len(ordered),
        snapshots=tuple(snapshots),
        membership=membership,
        transitions=tuple(transitions),
        union_instrument_ids=tuple(sorted(summary)),
        fingerprint=_fingerprint(
            session_date=session_date,
            observations=ordered,
            config=config,
        ),
    )


def observations_from_market_bars(
    *,
    session_date: date,
    bars_by_instrument: Mapping[str, Sequence[MarketBar]],
    previous_close_by_instrument: Mapping[str, Decimal],
    config: EvolvingTopGainersConfig = EvolvingTopGainersConfig(),
    source: str = "alpaca_sip_historical_rank_reconstruction",
) -> tuple[TopGainerObservation, ...]:
    """Build a 5m-by-default ranking tape from finalized causal intraday bars.

    ``bars_by_instrument`` must come from a population selected independently of
    end-of-day winner labels. Outcome-conditioned symbols must not be injected
    into this mapping merely because they later became winners.
    """

    prepared: dict[str, list[MarketBar]] = {}
    for instrument_id, bars in bars_by_instrument.items():
        previous_close = previous_close_by_instrument.get(instrument_id)
        if previous_close is None or previous_close <= 0:
            continue
        prepared[instrument_id] = sorted(
            (
                bar
                for bar in bars
                if bar.is_final
                and bar.session == "regular"
                and bar.end_time.astimezone(_ET).date() == session_date
            ),
            key=lambda bar: bar.end_time,
        )

    current = datetime.combine(
        session_date,
        config.first_evaluation_et,
        tzinfo=_ET,
    )
    last = datetime.combine(
        session_date,
        config.last_evaluation_et,
        tzinfo=_ET,
    )
    step = timedelta(minutes=config.cadence_minutes)
    observations: list[TopGainerObservation] = []
    while current <= last:
        observed_at = current.astimezone(timezone.utc)
        for instrument_id, bars in prepared.items():
            available = [bar for bar in bars if bar.end_time <= observed_at]
            if not available:
                continue
            latest = available[-1]
            cumulative_dollar_volume = sum(
                (bar.close * bar.volume for bar in available),
                Decimal("0"),
            )
            observations.append(
                TopGainerObservation(
                    instrument_id=instrument_id,
                    observed_at=observed_at,
                    price=latest.close,
                    previous_close=previous_close_by_instrument[instrument_id],
                    cumulative_dollar_volume=cumulative_dollar_volume,
                    source=source,
                )
            )
        current += step
    return tuple(observations)


def replay_evolving_top_gainers_from_bars(
    *,
    session_date: date,
    bars_by_instrument: Mapping[str, Sequence[MarketBar]],
    previous_close_by_instrument: Mapping[str, Decimal],
    config: EvolvingTopGainersConfig = EvolvingTopGainersConfig(),
) -> EvolvingTopGainersReplay:
    observations = observations_from_market_bars(
        session_date=session_date,
        bars_by_instrument=bars_by_instrument,
        previous_close_by_instrument=previous_close_by_instrument,
        config=config,
    )
    return replay_evolving_top_gainers(
        session_date=session_date,
        observations=observations,
        config=config,
    )


def evaluate_leader_momentum_after_discovery(
    bars: Sequence[MarketBar],
    *,
    discovered_at: datetime,
    context: leader.LeaderMomentumContext | None = None,
    last_entry_et: time = time(15, 30),
    force_flat_et: time = time(15, 55),
) -> leader.LeaderMomentumSnapshot:
    """Evaluate frozen Leader Momentum without allowing pre-discovery signals.

    Historical bars before discovery remain visible as causal indicator history;
    only trading authority is delayed until the symbol actually enters the
    evolving leaderboard.
    """

    if discovered_at.tzinfo is None:
        raise ValueError("leader_discovery_time_requires_timezone")
    local = discovered_at.astimezone(_ET)
    entry_start = max(time(9, 35), local.time().replace(tzinfo=None))
    snapshot = leader.evaluate_leader_momentum_continuation(
        list(bars),
        context=context,
        entry_start_et=entry_start,
        last_entry_et=last_entry_et,
        force_flat_et=force_flat_et,
    )
    for trade in snapshot.trades:
        if trade.signal_time < discovered_at:
            raise RuntimeError("leader_momentum_signal_preceded_dynamic_discovery")
    return snapshot


__all__ = [
    "EvolvingTopGainersConfig",
    "EvolvingTopGainersReplay",
    "TopGainerMember",
    "TopGainerMembershipSummary",
    "TopGainerMembershipTransition",
    "TopGainerObservation",
    "TopGainerSnapshot",
    "evaluate_leader_momentum_after_discovery",
    "observations_from_market_bars",
    "replay_evolving_top_gainers",
    "replay_evolving_top_gainers_from_bars",
]
