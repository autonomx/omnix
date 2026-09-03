from __future__ import annotations

import asyncio
import hashlib
import json
import os
import uuid
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.identity_service import bootstrap_local_tenant
from app.persistence.unit_of_work import unit_of_work
from app.trading import strategy_monitor as strategy_monitor_module
from app.trading.execution import ExecutionObservation
from app.trading.gapper_dataset import GapperCandidate, freeze_gapper_universe
from app.trading.models import MarketBar
from app.trading.paper import PaperAccountCreate, PaperMarketObservation
from app.trading.paper_repository import TradingPaperRepository
from app.trading.strategies.gap_pullback import evaluate_gap_pullback
from app.trading.strategies.models import StrategyRiskProfile
from app.trading.strategy_data_integrity import finviz_atomic_source_locator
from app.trading.strategy_monitor import TradingStrategyMonitor
from app.trading.strategy_repository import (
    StrategyEvent,
    TradingStrategyConfigDocument,
    TradingStrategyRepository,
)
from app.trading.strategy_universe_archiver import _archive_universe_id
from app.trading.strategy_v2_qualification import (
    PROSPECTIVE_ECONOMIC_POLICY_VERSION,
    V2_PROSPECTIVE_START,
    V2_QUALIFICATION_VERSION,
    V2_REPLAY_VERSION,
    evaluate_v2_prospective_qualification,
    managed_finviz_v2_config,
    v2_profile_fingerprint,
)


pytestmark = pytest.mark.skipif(
    not os.environ.get("OMNIX_TEST_DATABASE_URL"),
    reason="OMNIX_TEST_DATABASE_URL is required for PostgreSQL integration tests",
)

FIXTURE_PATH = (
    Path(__file__).parent.parent
    / "trading"
    / "fixtures"
    / "2026-09-03-auto-paper-e2e.json"
)
REPLAY_SESSION_DATE = date(2026, 10, 1)
REPLAY_CAPTURE_UTC = datetime(2026, 10, 1, 13, 16, 18, tzinfo=timezone.utc)
REPLAY_OPEN_UTC = datetime(2026, 10, 1, 13, 30, tzinfo=timezone.utc)
REPLAY_RUNTIME_NOW = datetime(2026, 10, 1, 14, 0, tzinfo=timezone.utc)
_ET = ZoneInfo("America/New_York")


def _database() -> PostgresDatabase:
    return PostgresDatabase(
        DatabaseSettings(
            url=os.environ["OMNIX_TEST_DATABASE_URL"],
            pool_min=1,
            pool_max=4,
            connect_timeout_seconds=10,
            statement_timeout_ms=30_000,
            application_name="omnix-auto-paper-e2e-tests",
        )
    )


def _frozen_datetime(now: datetime):
    class FrozenRuntimeDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return now.replace(tzinfo=None)
            return now.astimezone(tz)

    return FrozenRuntimeDateTime


def _event(
    *,
    strategy_id: str,
    event_type: str,
    instrument_id: str,
    observed_at: datetime,
    reason_code: str,
    payload: dict[str, object],
    suffix: str,
) -> StrategyEvent:
    raw = (
        f"{strategy_id}|{event_type}|{instrument_id}|"
        f"{observed_at.isoformat()}|{suffix}"
    )
    idem = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return StrategyEvent(
        strategy_id=strategy_id,
        event_id=idem[:32],
        instrument_id=instrument_id,
        event_type=event_type,
        state="entry_ready",
        reason_code=reason_code,
        observed_at=observed_at,
        idempotency_key=idem,
        payload=payload,
    )


def _seed_qualification(
    repository: TradingStrategyRepository,
    config: TradingStrategyConfigDocument,
) -> None:
    profile = v2_profile_fingerprint(config.config)
    sessions: list[date] = []
    cursor = V2_PROSPECTIVE_START
    while len(sessions) < 20:
        if cursor.weekday() < 5:
            sessions.append(cursor)
        cursor += timedelta(days=1)

    for index, session in enumerate(sessions):
        instrument = f"equity:QUAL{index % 10}"
        live_at = datetime.combine(session, time(14, 0), tzinfo=timezone.utc)
        entry_at = live_at + timedelta(minutes=1)
        universe_id = f"qualification-{session.isoformat()}-{index}"
        repository.append_event(
            _event(
                strategy_id=config.strategy_id,
                event_type="shadow_execution",
                instrument_id=instrument,
                observed_at=live_at,
                reason_code="SHADOW_EXECUTION_OBSERVED",
                suffix=f"live-{index}",
                payload={
                    "universe_source": "auto_archive_shadow",
                    "profile_fingerprint": profile,
                    "execution_authority": False,
                    "execution": {"execution_eligible": True},
                },
            )
        )
        repository.append_event(
            _event(
                strategy_id=config.strategy_id,
                event_type="v2_shadow_replay_trade",
                instrument_id=instrument,
                observed_at=entry_at + timedelta(hours=2),
                reason_code="V2_SHADOW_REPLAY_TRADE",
                suffix=f"replay-{index}",
                payload={
                    "qualification_version": V2_QUALIFICATION_VERSION,
                    "replay_version": V2_REPLAY_VERSION,
                    "session_date": session.isoformat(),
                    "universe_id": universe_id,
                    "universe_source": "auto_archive_shadow",
                    "profile_fingerprint": profile,
                    "entry_time": entry_at.isoformat(),
                    "r_result": "0.50",
                    "execution_authority": False,
                },
            )
        )

    review_at = max(
        event.observed_at
        for event in repository.events_by_types_between(
            config.strategy_id,
            event_types=(
                "shadow_execution",
                "v2_shadow_replay_trade",
            ),
            start_time=datetime.combine(
                V2_PROSPECTIVE_START,
                time.min,
                tzinfo=timezone.utc,
            ),
            end_time=REPLAY_RUNTIME_NOW,
            limit=20_000,
        )
    ) + timedelta(minutes=1)
    repository.append_event(
        _event(
            strategy_id=config.strategy_id,
            event_type="prospective_economic_auto_paper_review",
            instrument_id=f"strategy:{config.strategy_id}",
            observed_at=review_at,
            reason_code="PROSPECTIVE_ECONOMIC_AUTO_PAPER_REVIEW_APPROVED",
            suffix="economic-review",
            payload={
                "policy_version": PROSPECTIVE_ECONOMIC_POLICY_VERSION,
                "v2_profile_fingerprint": profile,
                "pipeline_evidence_fingerprint": "postgres-e2e-reviewed-pipeline",
                "approved": True,
                "review_note": "Reviewed synthetic qualification state for PostgreSQL E2E.",
                "execution_authority": False,
            },
        )
    )

    events = repository.events_by_types_between(
        config.strategy_id,
        event_types=(
            "shadow_execution",
            "v2_shadow_replay_trade",
            "v2_shadow_replay_session",
            "v2_promotion_review",
            "prospective_economic_auto_paper_review",
        ),
        start_time=datetime.combine(
            V2_PROSPECTIVE_START,
            time.min,
            tzinfo=timezone.utc,
        ),
        end_time=REPLAY_RUNTIME_NOW,
        limit=20_000,
    )
    before = evaluate_v2_prospective_qualification(config, events)
    assert before.qualified is True
    assert before.reviewed is False

    repository.append_event(
        _event(
            strategy_id=config.strategy_id,
            event_type="v2_promotion_review",
            instrument_id=f"strategy:{config.strategy_id}",
            observed_at=review_at + timedelta(minutes=1),
            reason_code="V2_PROMOTION_REVIEW_APPROVED",
            suffix="operator-review",
            payload={
                "qualification_version": V2_QUALIFICATION_VERSION,
                "profile_fingerprint": profile,
                "evidence_fingerprint": before.evidence_fingerprint,
                "approved": True,
                "review_note": "Exact Finviz evidence reviewed for PostgreSQL E2E.",
                "execution_authority": False,
            },
        )
    )


class ReplayMarketService:
    def __init__(
        self,
        *,
        instrument_id: str,
        binding_id: str,
        bars: list[MarketBar],
        assumptions: dict[str, object],
    ) -> None:
        self.instrument_id = instrument_id
        self.binding_id = binding_id
        self._bars = bars
        self.execution = ExecutionObservation(
            instrument_id=instrument_id,
            binding_id=binding_id,
            provider="sep3-postgres-e2e",
            bid=Decimal(str(assumptions["execution_bid"])),
            ask=Decimal(str(assumptions["execution_ask"])),
            bid_size=Decimal(str(assumptions["displayed_size"])),
            ask_size=Decimal(str(assumptions["displayed_size"])),
            last=Decimal(str(assumptions["execution_last"])),
            high=Decimal(str(assumptions["execution_ask"])),
            low=Decimal(str(assumptions["execution_bid"])),
            bar_volume=Decimal("100000"),
            bar_start_time=REPLAY_RUNTIME_NOW,
            cumulative_volume=Decimal("2500000"),
            source_time=REPLAY_RUNTIME_NOW,
            received_at=REPLAY_RUNTIME_NOW,
            session="regular",
            freshness_mode="polled",
            halted=False,
            execution_eligible=True,
        )

    def bars(self, instrument_id, interval, limit, binding_id):
        assert instrument_id == self.instrument_id
        assert interval == "1m"
        assert binding_id == self.binding_id
        return SimpleNamespace(bars=list(self._bars))

    def execution_observation(self, instrument_id, binding_id=None):
        assert instrument_id == self.instrument_id
        assert binding_id in {None, self.binding_id}
        return self.execution


def test_postgres_auto_paper_monitor_persists_order_fill_and_position(
    monkeypatch,
) -> None:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    selected = fixture["selected"]
    assumptions = fixture["execution_assumptions"]
    assert isinstance(selected, dict)
    assert isinstance(assumptions, dict)

    suffix = uuid.uuid4().hex[:10]
    strategy_id = f"sep3-postgres-e2e-{suffix}"
    account_id = f"paper-postgres-e2e-{suffix}"
    instrument_id = f"equity:TLYS:{suffix}"
    binding_id = f"replay:TLYS:{suffix}"

    config_value = managed_finviz_v2_config()
    config = TradingStrategyConfigDocument(
        strategy_id=strategy_id,
        account_id=account_id,
        strategy_kind="gap_pullback_v1",
        strategy_version="2.0.0",
        mode="auto_paper",
        active_universe_id=None,
        config=config_value,
        risk=StrategyRiskProfile(),
        enabled=True,
    )

    candidate = GapperCandidate(
        instrument_id=instrument_id,
        binding_id=binding_id,
        observed_at=REPLAY_CAPTURE_UTC,
        previous_close=Decimal(str(selected["previous_close"])),
        premarket_price=Decimal(str(selected["premarket_price"])),
        gap_pct=Decimal(str(selected["gap_pct"])),
        premarket_volume=Decimal(str(assumptions["premarket_volume"])),
        premarket_dollar_volume=Decimal(
            str(assumptions["premarket_dollar_volume"])
        ),
        premarket_bar_count=8,
        tod_rvol=Decimal(str(assumptions["tod_rvol"])),
        market_data_complete=True,
        market_cap=Decimal(str(selected["market_cap"])),
        spread_bps=Decimal(str(assumptions["candidate_spread_bps"])),
        discovery_rank=1,
    )

    bars: list[MarketBar] = []
    for row in fixture["replay_bars"]:
        start = REPLAY_OPEN_UTC + timedelta(minutes=int(row["minute"]))
        bars.append(
            MarketBar(
                instrument_id=instrument_id,
                interval="1m",
                start_time=start,
                end_time=start + timedelta(minutes=1),
                open=Decimal(str(row["open"])),
                high=Decimal(str(row["high"])),
                low=Decimal(str(row["low"])),
                close=Decimal(str(row["close"])),
                volume=Decimal(str(row["volume"])),
                is_final=True,
                session="regular",
                provider="sep3-postgres-e2e",
                received_at=start + timedelta(minutes=1),
            )
        )
    assert evaluate_gap_pullback(candidate, bars, config.config).state == "entry_ready"

    marker = datetime.combine(
        REPLAY_SESSION_DATE,
        config.config.universe_scan_time_et,
        tzinfo=_ET,
    )
    universe = freeze_gapper_universe(
        universe_id=_archive_universe_id(config, marker),
        session_date=REPLAY_SESSION_DATE,
        evaluation_time=REPLAY_CAPTURE_UTC,
        discovery_source="finviz",
        source_locator=finviz_atomic_source_locator(str(fixture["source_url"])),
        source_candidate_symbols=tuple(fixture["source_candidate_symbols"]),
        candidates=[candidate],
    )

    database = _database()
    try:
        context = bootstrap_local_tenant(database)
        uow_factory = lambda: unit_of_work(database)
        strategy_repository = TradingStrategyRepository(
            context=context,
            uow_factory=uow_factory,
        )
        paper_repository = TradingPaperRepository(
            context=context,
            uow_factory=uow_factory,
        )
        paper_repository.create_account(
            PaperAccountCreate(
                account_id=account_id,
                name="AUTO PAPER PostgreSQL E2E",
                initial_cash=Decimal("10000"),
            )
        )
        strategy_repository.create_config(config)
        strategy_repository.save_universe(universe)
        _seed_qualification(strategy_repository, config)

        authorized_events = strategy_repository.events_by_types_between(
            strategy_id,
            event_types=(
                "shadow_execution",
                "v2_shadow_replay_trade",
                "v2_promotion_review",
                "prospective_economic_auto_paper_review",
            ),
            start_time=datetime.combine(
                V2_PROSPECTIVE_START,
                time.min,
                tzinfo=timezone.utc,
            ),
            end_time=REPLAY_RUNTIME_NOW,
            limit=20_000,
        )
        qualification = evaluate_v2_prospective_qualification(
            config,
            authorized_events,
        )
        assert qualification.auto_paper_authorized is True

        market_service = ReplayMarketService(
            instrument_id=instrument_id,
            binding_id=binding_id,
            bars=bars,
            assumptions=assumptions,
        )
        monkeypatch.setattr(
            strategy_monitor_module,
            "datetime",
            _frozen_datetime(REPLAY_RUNTIME_NOW),
        )
        monitor = TradingStrategyMonitor(
            strategy_repository_factory=lambda: strategy_repository,
            paper_repository_factory=lambda: paper_repository,
            market_service_factory=lambda: market_service,
            interval_seconds=5,
        )

        submitted = asyncio.run(monitor.run_once())
        assert submitted == 1
        assert monitor.paper_order_count == 1
        assert monitor.auto_paper_ready_strategy_count == 1

        before_fill = paper_repository.snapshot(account_id)
        assert len(before_fill.open_orders) == 1
        order = before_fill.open_orders[0]
        assert order.instrument_id == instrument_id
        assert order.side == "buy"

        execution = market_service.execution
        assert order.created_at is not None
        fill_time = max(
            REPLAY_RUNTIME_NOW,
            order.created_at.astimezone(timezone.utc) + timedelta(seconds=1),
        )
        observation = PaperMarketObservation(
            instrument_id=instrument_id,
            binding_id=binding_id,
            provider=execution.provider,
            price=execution.last or execution.ask or execution.bid,
            bid=execution.bid,
            ask=execution.ask,
            bid_size=execution.bid_size,
            ask_size=execution.ask_size,
            high=execution.high,
            low=execution.low,
            volume=execution.bar_volume,
            bar_start_time=execution.bar_start_time,
            source_time=fill_time,
            evaluated_at=fill_time,
            execution_eligible=True,
            freshness_mode="live",
            halted=False,
        )
        fills = paper_repository.process_observation(account_id, observation)
        assert len(fills) == 1
        assert fills[0].order_id == order.order_id

        persisted = paper_repository.snapshot(account_id)
        filled_order = next(
            item for item in persisted.order_history
            if item.order_id == order.order_id
        )
        assert filled_order.status == "filled"
        assert filled_order.filled_quantity == filled_order.quantity
        position = next(
            item for item in persisted.positions
            if item.instrument_id == instrument_id
        )
        assert position.quantity == fills[0].quantity
        assert position.average_cost == fills[0].price

        protections = strategy_repository.list_protections(
            strategy_id,
            active_only=True,
        )
        assert len(protections) == 1
        assert protections[0].status == "pending_entry"
        assert protections[0].entry_order_id == order.order_id

        print(
            "POSTGRES AUTO PAPER E2E PASS "
            f"strategy={strategy_id} order={order.order_id} "
            f"qty={fills[0].quantity} fill={fills[0].price} "
            f"position={position.quantity}"
        )
    finally:
        database.close()
