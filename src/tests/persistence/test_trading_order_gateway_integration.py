"""The order gateway's guarantees against PostgreSQL (WP-8.3)."""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.identity_service import ensure_local_identity
from app.persistence.unit_of_work import unit_of_work
from app.trading.kill_switches import TradingKillSwitchRepository
from app.trading.order_gateway import OrderGateway
from app.trading.paper import PaperAccountCreate, PaperMarketObservation, PaperOrderRequest
from app.trading.paper_repository import TradingPaperRepository

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        not os.environ.get("OMNIX_TEST_DATABASE_URL"),
        reason="OMNIX_TEST_DATABASE_URL is required for PostgreSQL integration tests",
    ),
]


class _ApprovingAuthorizer:
    def __init__(self) -> None:
        self.attempts: list[str] = []

    def authorize(self, account_id, request, *, trade_attempt_id):
        self.attempts.append(trade_attempt_id)


@pytest.fixture()
def paper():
    database = PostgresDatabase(
        DatabaseSettings(
            url=os.environ["OMNIX_TEST_DATABASE_URL"],
            pool_min=1,
            pool_max=3,
            connect_timeout_seconds=10,
            statement_timeout_ms=30_000,
            application_name="omnix-order-gateway-tests",
        )
    )
    try:
        context = ensure_local_identity(database)

        def uow():
            return unit_of_work(database)

        repository = TradingPaperRepository(context=context, uow_factory=uow)
        switches = TradingKillSwitchRepository(context=context, uow_factory=uow)
        suffix = uuid.uuid4().hex[:10]
        account_id = f"paper-gateway-{suffix}"
        repository.create_account(
            PaperAccountCreate(account_id=account_id, name="Order gateway", initial_cash=Decimal("100000"))
        )
        yield repository, switches, account_id, f"equity:NASDAQ:G{suffix[:4].upper()}", database
        for scope, scope_id in (("global", ""), ("account", account_id), ("strategy", f"strategy-{suffix}")):
            switches.set(scope, scope_id, engaged=False)
    finally:
        database.close()


def _order(instrument_id: str, side: str, quantity: str, key: str, **prices) -> PaperOrderRequest:
    if not prices:
        prices = {"reference_price": Decimal("10")}
    return PaperOrderRequest(
        order_id=f"order-{key}",
        instrument_id=instrument_id,
        side=side,
        order_type="market" if "reference_price" in prices else "limit",
        quantity=Decimal(quantity),
        idempotency_key=f"idem-{key}",
        **prices,
    )


def _fill(repository, account_id: str, instrument_id: str) -> None:
    now = datetime.now(timezone.utc) + timedelta(seconds=1)
    repository.process_observation(
        account_id,
        PaperMarketObservation(
            instrument_id=instrument_id,
            provider="integration",
            price=Decimal("10"),
            bid=Decimal("9.99"),
            ask=Decimal("10.01"),
            bid_size=Decimal("100000"),
            ask_size=Decimal("100000"),
            source_time=now,
            evaluated_at=now,
            execution_eligible=True,
            freshness_mode="live",
        ),
    )


def _open_long(repository, account_id: str, instrument_id: str, quantity: str = "10") -> None:
    OrderGateway(repository).place_manual_entry(account_id, _order(instrument_id, "buy", quantity, uuid.uuid4().hex))
    _fill(repository, account_id, instrument_id)


def test_an_entry_needs_entry_authority(paper) -> None:
    repository, _, account_id, instrument_id, _ = paper

    with pytest.raises(ValueError, match="paper_order_requires_entry_authority"):
        OrderGateway(repository).place_reducing(account_id, _order(instrument_id, "buy", "1", "reduce-buy"))

    placed = OrderGateway(repository).place_manual_entry(account_id, _order(instrument_id, "buy", "1", "manual-buy"))
    assert placed.status == "open"


@pytest.mark.parametrize("scope", ["global", "account", "strategy"])
def test_an_engaged_kill_switch_stops_entries_but_not_exits(paper, scope) -> None:
    repository, switches, account_id, instrument_id, _ = paper
    strategy_id = f"strategy-{account_id.rsplit('-', 1)[1]}"
    _open_long(repository, account_id, instrument_id)
    scope_id = {"global": "", "account": account_id, "strategy": strategy_id}[scope]
    switches.set(scope, scope_id, engaged=True, reason="integration test")
    gateway = OrderGateway(repository, entry_authorizer=_ApprovingAuthorizer())

    with pytest.raises(ValueError, match=f"trading_kill_switch_engaged:{scope}"):
        gateway.place_strategy_entry(
            account_id,
            _order(instrument_id, "buy", "1", f"entry-{scope}"),
            strategy_id=strategy_id,
            trade_attempt_id="attempt-1",
        )
    exit_order = gateway.place_reducing(account_id, _order(instrument_id, "sell", "10", f"exit-{scope}"))
    assert exit_order.status == "open"

    switches.set(scope, scope_id, engaged=False)
    entry = gateway.place_strategy_entry(
        account_id,
        _order(instrument_id, "buy", "1", f"entry-after-{scope}"),
        strategy_id=strategy_id,
        trade_attempt_id="attempt-2",
    )
    assert entry.status == "open"


def test_accounts_are_long_only_unless_they_allow_shorting(paper) -> None:
    repository, _, account_id, instrument_id, database = paper

    with pytest.raises(ValueError, match="paper_short_not_allowed"):
        OrderGateway(repository).place_reducing(account_id, _order(instrument_id, "sell", "1", "naked-sell"))

    with unit_of_work(database) as uow:
        uow.connection.execute(
            "UPDATE omnix_trading_paper_accounts SET allow_short = TRUE WHERE workspace_id = %s AND account_id = %s",
            (repository.context.workspace_id, account_id),
        )
        uow.commit()
    # A short opens exposure: it needs entry authority, as a buy does.
    with pytest.raises(ValueError, match="paper_order_requires_entry_authority"):
        OrderGateway(repository).place_reducing(account_id, _order(instrument_id, "sell", "1", "short-reduce"))
    short = OrderGateway(repository).place_manual_entry(account_id, _order(instrument_id, "sell", "1", "short-entry"))
    assert short.status == "open"


def test_a_sell_beyond_the_unreserved_position_is_rejected(paper) -> None:
    repository, _, account_id, instrument_id, _ = paper
    _open_long(repository, account_id, instrument_id, quantity="5")

    with pytest.raises(ValueError, match="insufficient_paper_position"):
        OrderGateway(repository).place_reducing(account_id, _order(instrument_id, "sell", "6", "oversell"))


def test_a_rejected_replacement_leaves_the_original_order_open(paper) -> None:
    repository, _, account_id, instrument_id, _ = paper
    _open_long(repository, account_id, instrument_id, quantity="5")
    gateway = OrderGateway(repository)
    original = gateway.place_reducing(
        account_id, _order(instrument_id, "sell", "5", "original", limit_price=Decimal("12"))
    )

    with pytest.raises(ValueError, match="insufficient_paper_position"):
        gateway.replace_reducing(
            account_id,
            original.order_id,
            _order(instrument_id, "sell", "6", "too-large", limit_price=Decimal("12")),
        )
    snapshot = repository.snapshot(account_id)
    assert [order.order_id for order in snapshot.open_orders] == [original.order_id]
    position = next(item for item in snapshot.positions if item.instrument_id == instrument_id)
    assert position.reserved_quantity == Decimal("5")

    cancelled, replacement = gateway.replace_reducing(
        account_id,
        original.order_id,
        _order(instrument_id, "sell", "5", "replacement", limit_price=Decimal("11")),
    )
    assert cancelled.status == "cancelled"
    assert replacement.status == "open"


def test_an_idempotent_retry_returns_the_placed_order_even_after_a_kill_switch(paper) -> None:
    repository, switches, account_id, instrument_id, _ = paper
    gateway = OrderGateway(repository)
    request = _order(instrument_id, "buy", "1", "retry")
    first = gateway.place_manual_entry(account_id, request)
    switches.set("account", account_id, engaged=True)

    assert gateway.place_manual_entry(account_id, request) == first
