"""Paper order types, time in force and trailing state against PostgreSQL (TVP-7.1)."""
from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import psycopg
import pytest

from app.apps.trading.execution import ExecutionObservation
from app.apps.trading.order_gateway import OrderGateway
from app.apps.trading.paper import PaperAccountCreate, PaperMarketObservation, PaperOrderRequest
from app.apps.trading.paper_monitor import TradingPaperMonitor
from app.apps.trading.paper_protection import PaperProtectionUpsert
from app.apps.trading.paper_protection_repository import TradingPaperProtectionRepository
from app.apps.trading.paper_repository import TradingPaperRepository
from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.identity_service import ensure_local_identity
from app.persistence.unit_of_work import unit_of_work

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        not os.environ.get("OMNIX_TEST_DATABASE_URL"),
        reason="OMNIX_TEST_DATABASE_URL is required for PostgreSQL integration tests",
    ),
]

STOP_SLIPPAGE = Decimal("0.9975")


class _Clock:
    def __init__(self) -> None:
        self.now: datetime | None = None

    def __call__(self) -> datetime:
        return self.now or datetime.now(timezone.utc)


@pytest.fixture()
def paper():
    database = PostgresDatabase(
        DatabaseSettings(
            url=os.environ["OMNIX_TEST_DATABASE_URL"],
            pool_min=1,
            pool_max=3,
            connect_timeout_seconds=10,
            statement_timeout_ms=30_000,
            application_name="omnix-paper-order-types-tests",
        )
    )
    try:
        context = ensure_local_identity(database)

        def uow():
            return unit_of_work(database)

        clock = _Clock()

        def repository_factory() -> TradingPaperRepository:
            # A new instance is what a restarted process would build.
            return TradingPaperRepository(context=context, uow_factory=uow, clock=clock)

        protections = TradingPaperProtectionRepository(context=context, uow_factory=uow)
        suffix = uuid.uuid4().hex[:10]
        account_id = f"paper-types-{suffix}"
        repository_factory().create_account(
            PaperAccountCreate(account_id=account_id, name="Order types", initial_cash=Decimal("100000"))
        )
        yield SimpleState(
            repository_factory=repository_factory,
            protections=protections,
            account_id=account_id,
            instrument_id=f"equity:NASDAQ:T{suffix[:4].upper()}",
            clock=clock,
        )
    finally:
        database.close()


class SimpleState:
    def __init__(self, **values) -> None:
        self.__dict__.update(values)


def _observation(instrument_id: str, price: str, *, seconds: int = 1) -> PaperMarketObservation:
    moment = datetime.now(timezone.utc) + timedelta(seconds=seconds)
    value = Decimal(price)
    return PaperMarketObservation(
        instrument_id=instrument_id,
        provider="integration",
        price=value,
        bid=value,
        ask=value,
        bid_size=Decimal("100000"),
        ask_size=Decimal("100000"),
        source_time=moment,
        evaluated_at=moment,
        execution_eligible=True,
        freshness_mode="live",
    )


def _request(instrument_id: str, side: str, order_type: str, key: str, **fields) -> PaperOrderRequest:
    return PaperOrderRequest(
        order_id=f"order-{key}",
        instrument_id=instrument_id,
        side=side,
        order_type=order_type,
        quantity=fields.pop("quantity", Decimal("10")),
        idempotency_key=f"idem-{key}",
        **fields,
    )


def _open_long(state, quantity: str = "10", price: str = "10") -> None:
    repository = state.repository_factory()
    OrderGateway(repository).place_manual_entry(
        state.account_id,
        _request(state.instrument_id, "buy", "market", uuid.uuid4().hex, quantity=Decimal(quantity), reference_price=Decimal(price)),
    )
    repository.process_observation(state.account_id, _observation(state.instrument_id, price))


def _cash(state) -> tuple[Decimal, Decimal]:
    balance = state.repository_factory().snapshot(state.account_id).balances[0]
    return balance.available, balance.reserved


def _order(state, order_id: str):
    return next(item for item in state.repository_factory().snapshot(state.account_id).order_history if item.order_id == order_id)


def test_the_migration_keeps_existing_orders_gtc(paper) -> None:
    repository = paper.repository_factory()
    placed = OrderGateway(repository).place_manual_entry(
        paper.account_id, _request(paper.instrument_id, "buy", "limit", "plain", limit_price=Decimal("9"))
    )
    assert (placed.time_in_force, placed.expires_at, placed.trail_amount, placed.trail_water_mark) == ("gtc", None, None, None)
    assert repository.expire_orders(paper.account_id, now=datetime(2100, 1, 1, tzinfo=timezone.utc)) == []
    assert _order(paper, placed.order_id).status == "open"


def test_the_database_refuses_inconsistent_order_rows() -> None:
    with psycopg.connect(os.environ["OMNIX_TEST_DATABASE_URL"]) as connection:
        checks = {
            row[0]
            for row in connection.execute(
                "SELECT conname FROM pg_constraint WHERE conrelid = 'omnix_trading_paper_orders'::regclass"
            ).fetchall()
        }
        assert {
            "omnix_trading_paper_orders_time_in_force_check",
            "omnix_trading_paper_orders_trailing_check",
            "omnix_trading_paper_orders_stop_limit_check",
        } <= checks
        definitions = dict(
            connection.execute(
                "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint "
                "WHERE conrelid = 'omnix_trading_paper_orders'::regclass"
            ).fetchall()
        )
        assert "stop_limit" in definitions["omnix_trading_paper_orders_order_type_check"]
        assert "expired" in definitions["omnix_trading_paper_orders_status_check"]
        column = connection.execute(
            "SELECT column_default FROM information_schema.columns "
            "WHERE table_name = 'omnix_trading_paper_orders' AND column_name = 'time_in_force'"
        ).fetchone()
        assert column is not None and "gtc" in column[0]


def test_stop_limit_gap_through_rests_then_fills_at_the_limit(paper) -> None:
    repository = paper.repository_factory()
    placed = OrderGateway(repository).place_manual_entry(
        paper.account_id,
        _request(paper.instrument_id, "buy", "stop_limit", "stop-limit", stop_price=Decimal("10"), limit_price=Decimal("10.5")),
    )
    assert placed.reserved_cash == Decimal("105")
    assert repository.process_observation(paper.account_id, _observation(paper.instrument_id, "9.5")) == []
    assert _order(paper, placed.order_id).stop_triggered_at is None

    # The market gaps through both the stop and the limit: triggered, not filled.
    assert repository.process_observation(paper.account_id, _observation(paper.instrument_id, "11", seconds=2)) == []
    triggered = _order(paper, placed.order_id)
    assert triggered.status == "open" and triggered.stop_triggered_at is not None

    # A restarted repository sees a resting limit order, filled back below the stop.
    fills = paper.repository_factory().process_observation(
        paper.account_id, _observation(paper.instrument_id, "9.8", seconds=3)
    )
    assert [(fill.price, fill.quantity) for fill in fills] == [(Decimal("9.8"), Decimal("10"))]
    assert _order(paper, placed.order_id).status == "filled"
    assert _cash(paper) == (Decimal("100000") - Decimal("98"), Decimal("0"))


def test_trailing_stop_state_survives_a_restart(paper) -> None:
    _open_long(paper)
    request = _request(paper.instrument_id, "sell", "trailing_stop", "trail", trail_amount=Decimal("1"))
    placed = OrderGateway(paper.repository_factory()).place_reducing(paper.account_id, request)
    assert placed.stop_price is None and placed.trail_water_mark is None

    paper.repository_factory().process_observation(paper.account_id, _observation(paper.instrument_id, "10"))
    armed = _order(paper, placed.order_id)
    assert (armed.trail_water_mark, armed.stop_price) == (Decimal("10"), Decimal("9"))
    paper.repository_factory().process_observation(paper.account_id, _observation(paper.instrument_id, "12", seconds=2))
    paper.repository_factory().process_observation(paper.account_id, _observation(paper.instrument_id, "11.5", seconds=3))

    restarted = paper.repository_factory()
    resumed = _order(paper, placed.order_id)
    assert (resumed.trail_water_mark, resumed.stop_price, resumed.status) == (Decimal("12"), Decimal("11"), "open")
    # An idempotent retry after the trail moved returns the same order.
    assert OrderGateway(restarted).place_reducing(paper.account_id, request).order_id == placed.order_id

    fills = restarted.process_observation(paper.account_id, _observation(paper.instrument_id, "10.9", seconds=4))
    assert [fill.price for fill in fills] == [Decimal("10.9") * STOP_SLIPPAGE]
    assert _order(paper, placed.order_id).status == "filled"


def test_day_orders_expire_at_the_session_close_and_release_their_holds(paper) -> None:
    _open_long(paper)
    paper.clock.now = datetime(2026, 10, 7, 18, 0, tzinfo=timezone.utc)  # Wednesday 14:00 ET
    close = datetime(2026, 10, 7, 20, 0, tzinfo=timezone.utc)
    repository = paper.repository_factory()
    gateway = OrderGateway(repository)
    buy = gateway.place_manual_entry(
        paper.account_id,
        _request(paper.instrument_id, "buy", "limit", "day-buy", limit_price=Decimal("5"), time_in_force="day"),
    )
    sell = gateway.place_reducing(
        paper.account_id,
        _request(paper.instrument_id, "sell", "limit", "day-sell", quantity=Decimal("4"), limit_price=Decimal("50"), time_in_force="day"),
    )
    assert buy.expires_at == close and sell.expires_at == close
    available_before, _ = _cash(paper)

    assert repository.expire_orders(paper.account_id, now=close - timedelta(seconds=1)) == []
    expired = repository.expire_orders(paper.account_id, now=close)
    assert {item.order_id for item in expired} == {buy.order_id, sell.order_id}
    assert {item.status for item in expired} == {"expired"}
    assert {item.rejection_reason for item in expired} == {"time_in_force_expired"}
    available, reserved = _cash(paper)
    assert available == available_before + Decimal("50") and reserved == Decimal("0")
    position = paper.repository_factory().snapshot(paper.account_id).positions[0]
    assert position.reserved_quantity == Decimal("0")


def test_gtd_orders_expire_before_an_observation_can_fill_them(paper) -> None:
    now = datetime.now(timezone.utc)
    repository = paper.repository_factory()
    with pytest.raises(ValueError, match="paper_order_expiry_in_past"):
        OrderGateway(repository).place_manual_entry(
            paper.account_id,
            _request(paper.instrument_id, "buy", "limit", "gtd-past", limit_price=Decimal("10"), time_in_force="gtd", expires_at=now),
        )
    placed = OrderGateway(repository).place_manual_entry(
        paper.account_id,
        _request(
            paper.instrument_id, "buy", "limit", "gtd", limit_price=Decimal("10"),
            time_in_force="gtd", expires_at=now + timedelta(hours=1),
        ),
    )
    assert _cash(paper)[1] == Decimal("100")
    paper.clock.now = now + timedelta(hours=2)
    assert paper.repository_factory().process_observation(paper.account_id, _observation(paper.instrument_id, "9")) == []
    assert _order(paper, placed.order_id).status == "expired"
    assert _cash(paper) == (Decimal("100000"), Decimal("0"))


def test_trailing_stop_loss_leg_is_persisted_and_resumed(paper) -> None:
    _open_long(paper)
    protections = paper.protections
    protection = protections.upsert(
        paper.account_id,
        PaperProtectionUpsert(instrument_id=paper.instrument_id, stop_loss=Decimal("9"), trail_amount=Decimal("1")),
    )
    assert protection.status == "active" and protection.trail_amount == Decimal("1")
    assert protection.trail_water_mark is None

    moved = protections.trail_stop(
        paper.account_id, paper.instrument_id,
        water_mark=Decimal("12"), stop_loss=Decimal("11"), expected_revision=protection.revision,
    )
    assert moved is not None and (moved.trail_water_mark, moved.stop_loss, moved.revision) == (
        Decimal("12"), Decimal("11"), protection.revision,
    )
    stale = protections.trail_stop(
        paper.account_id, paper.instrument_id,
        water_mark=Decimal("13"), stop_loss=Decimal("12"), expected_revision=protection.revision + 5,
    )
    assert stale is None

    # Editing the bracket starts a fresh trail from the new initial stop.
    rearmed = protections.upsert(
        paper.account_id,
        PaperProtectionUpsert(instrument_id=paper.instrument_id, stop_loss=Decimal("8"), trail_percent=Decimal("5")),
    )
    assert (rearmed.trail_water_mark, rearmed.stop_loss, rearmed.trail_amount, rearmed.trail_percent) == (
        None, Decimal("8"), None, Decimal("5"),
    )
    protections.trail_stop(
        paper.account_id, paper.instrument_id,
        water_mark=Decimal("12"), stop_loss=Decimal("11.4"), expected_revision=rearmed.revision,
    )
    resumed = protections.get(paper.account_id, paper.instrument_id)
    assert (resumed.trail_water_mark, resumed.stop_loss) == (Decimal("12"), Decimal("11.4"))

    # The monitor exits at the trailed stop, not the initial one.
    now = datetime.now(timezone.utc) + timedelta(seconds=1)

    class _Market:
        def execution_observation(self, instrument_id, binding_id=None):
            return ExecutionObservation(
                instrument_id=instrument_id, binding_id="alpaca-paper:test", provider="integration",
                bid=Decimal("10.9"), ask=Decimal("10.9"), last=Decimal("10.9"),
                source_time=now, received_at=now, session="regular", freshness_mode="live",
                execution_eligible=True,
            )

    repository = paper.repository_factory()
    monitor = TradingPaperMonitor(
        repository_factory=lambda: repository,
        protection_repository_factory=lambda: protections,
        market_service_factory=_Market,
        interval_seconds=5,
    )
    asyncio.run(
        monitor._reconcile_protection(
            account_id=paper.account_id,
            instrument_id=paper.instrument_id,
            execution=_Market().execution_observation(paper.instrument_id),
            repository=repository,
            protections=protections,
        )
    )
    exited = protections.get(paper.account_id, paper.instrument_id)
    assert (exited.status, exited.trigger_reason) == ("exit_submitted", "stop_loss")
    exit_order = _order(paper, exited.exit_order_id)
    assert (exit_order.side, exit_order.order_type, exit_order.quantity) == ("sell", "market", Decimal("10"))


def test_a_pending_bracket_is_cancelled_when_its_day_entry_expires(paper) -> None:
    paper.clock.now = datetime(2026, 10, 7, 18, 0, tzinfo=timezone.utc)
    repository = paper.repository_factory()
    protections = paper.protections
    order_id = f"order-day-entry-{uuid.uuid4().hex[:6]}"
    protections.arm_pending_entry(
        paper.account_id,
        PaperProtectionUpsert(
            instrument_id=paper.instrument_id, entry_order_id=order_id,
            stop_loss=Decimal("4"), trail_amount=Decimal("1"),
        ),
    )
    OrderGateway(repository).place_manual_entry(
        paper.account_id,
        PaperOrderRequest(
            order_id=order_id, instrument_id=paper.instrument_id, side="buy", order_type="limit",
            quantity=Decimal("1"), limit_price=Decimal("5"), idempotency_key=order_id, time_in_force="day",
        ),
    )
    repository.expire_orders(paper.account_id, now=datetime(2026, 10, 7, 20, 0, tzinfo=timezone.utc))
    pending = protections.get(paper.account_id, paper.instrument_id)
    assert pending.status == "pending_entry" and pending.trail_amount == Decimal("1")

    now = datetime.now(timezone.utc)
    execution = ExecutionObservation(
        instrument_id=paper.instrument_id, binding_id="alpaca-paper:test", provider="integration",
        bid=Decimal("5"), ask=Decimal("5"), last=Decimal("5"), source_time=now, received_at=now,
        session="regular", freshness_mode="live", execution_eligible=True,
    )
    monitor = TradingPaperMonitor(
        repository_factory=lambda: repository,
        protection_repository_factory=lambda: protections,
        interval_seconds=5,
    )
    asyncio.run(
        monitor._reconcile_protection(
            account_id=paper.account_id, instrument_id=paper.instrument_id, execution=execution,
            repository=repository, protections=protections,
        )
    )
    cancelled = protections.get(paper.account_id, paper.instrument_id)
    assert (cancelled.status, cancelled.trigger_reason) == ("cancelled", "entry_expired")
