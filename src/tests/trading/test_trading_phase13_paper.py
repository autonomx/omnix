from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.persistence.errors import RevisionConflict
from app.trading.paper import (
    PaperAccount,
    PaperAccountCreate,
    PaperAccountSnapshot,
    PaperBalance,
    PaperFill,
    PaperLedgerEntry,
    PaperMarketObservation,
    PaperOrder,
    PaperOrderRequest,
    PaperPosition,
    paper_commission,
    paper_fill_decision,
    paper_fill_key,
    paper_realized_pnl,
    paper_unrealized_pnl,
)
from app.trading.paper_api import create_trading_paper_router
from app.trading.paper_monitor import TradingPaperMonitor, trading_paper_monitor_enabled


NOW = datetime(2026, 8, 5, tzinfo=timezone.utc)
INSTRUMENT = "crypto:BINANCE:spot:BTC-USDT"
BINDING = "binance:BTCUSDT"


def order(order_type="market", side="buy", **overrides) -> PaperOrder:
    payload = {
        "account_id": "paper-1",
        "order_id": f"{side}-{order_type}",
        "instrument_id": INSTRUMENT,
        "binding_id": BINDING,
        "side": side,
        "order_type": order_type,
        "quantity": Decimal("2"),
        "limit_price": Decimal("100") if order_type == "limit" else None,
        "stop_price": Decimal("100") if order_type == "stop" else None,
        "idempotency_key": f"key-{side}-{order_type}",
    }
    payload.update(overrides)
    return PaperOrder(**payload)


def observation(price: str) -> PaperMarketObservation:
    return PaperMarketObservation(
        instrument_id=INSTRUMENT,
        binding_id=BINDING,
        provider="binance",
        price=Decimal(price),
        source_time=NOW,
        evaluated_at=NOW,
    )


def snapshot(*, revision=1, enabled=True, open_orders=()) -> PaperAccountSnapshot:
    return PaperAccountSnapshot(
        account=PaperAccount(
            account_id="paper-1",
            name="Paper Account",
            base_currency="USD",
            commission_bps=Decimal("10"),
            enabled=enabled,
            revision=revision,
        ),
        balances=[PaperBalance(currency="USD", available=Decimal("10000"))],
        positions=[],
        open_orders=list(open_orders),
        recent_fills=[],
        recent_ledger=[
            PaperLedgerEntry(
                ledger_id="deposit",
                entry_type="deposit",
                currency="USD",
                amount=Decimal("10000"),
                idempotency_key="deposit",
            )
        ],
    )


def test_order_contract_and_fill_conditions_are_explicit() -> None:
    with pytest.raises(ValidationError):
        PaperOrderRequest(
            order_id="bad-limit",
            instrument_id=INSTRUMENT,
            side="buy",
            order_type="limit",
            quantity="1",
            idempotency_key="bad-limit",
        )
    with pytest.raises(ValidationError):
        PaperOrderRequest(
            order_id="bad-market",
            instrument_id=INSTRUMENT,
            side="buy",
            order_type="market",
            quantity="1",
            limit_price="100",
            idempotency_key="bad-market",
        )

    assert paper_fill_decision(order("market"), observation("101")).should_fill
    assert paper_fill_decision(order("limit", "buy"), observation("99")).should_fill
    assert not paper_fill_decision(order("limit", "buy"), observation("101")).should_fill
    assert paper_fill_decision(order("limit", "sell"), observation("101")).should_fill
    assert paper_fill_decision(order("stop", "buy"), observation("101")).should_fill
    assert paper_fill_decision(order("stop", "sell"), observation("99")).should_fill
    mismatch = observation("100").model_copy(update={"binding_id": "other"})
    assert paper_fill_decision(order("market"), mismatch).reason == "binding_mismatch"


def test_paper_accounting_math_and_fill_idempotency_are_reproducible() -> None:
    assert paper_commission(Decimal("1000"), Decimal("10")) == Decimal("1")
    assert paper_unrealized_pnl(Decimal("2"), Decimal("100"), Decimal("110")) == Decimal("20")
    assert paper_realized_pnl(Decimal("2"), Decimal("100"), Decimal("90")) == Decimal("-20")
    key = paper_fill_key("paper-1", "order-1", observation("101"))
    assert key == paper_fill_key("paper-1", "order-1", observation("101"))
    assert key != paper_fill_key("paper-1", "order-1", observation("102"))


class FakePaperRepository:
    def __init__(self) -> None:
        self.current = snapshot(open_orders=[order("market")])
        self.observations: list[tuple[str, PaperMarketObservation]] = []

    def list_accounts(self, limit=100):
        return [self.current.account]

    def create_account(self, request: PaperAccountCreate):
        self.current = PaperAccountSnapshot(
            account=PaperAccount(
                account_id=request.account_id,
                name=request.name,
                base_currency=request.base_currency,
                commission_bps=request.commission_bps,
                revision=1,
            ),
            balances=[PaperBalance(currency=request.base_currency, available=request.initial_cash)],
            positions=[],
            open_orders=[],
            recent_fills=[],
            recent_ledger=[],
        )
        return self.current

    def snapshot(self, account_id):
        if account_id != self.current.account.account_id:
            raise ValueError("paper_account_not_found")
        return self.current

    def place_order(self, account_id, request):
        value = PaperOrder(account_id=account_id, **request.model_dump())
        self.current = self.current.model_copy(
            update={"open_orders": [*self.current.open_orders, value]}
        )
        return value

    def cancel_order(self, account_id, order_id):
        current = next(item for item in self.current.open_orders if item.order_id == order_id)
        cancelled = current.model_copy(update={"status": "cancelled"})
        self.current = self.current.model_copy(
            update={"open_orders": [item for item in self.current.open_orders if item.order_id != order_id]}
        )
        return cancelled

    def process_observation(self, account_id, value):
        self.observations.append((account_id, value))
        fill = PaperFill(
            fill_id="fill-1",
            order_id=self.current.open_orders[0].order_id,
            instrument_id=value.instrument_id,
            side="buy",
            quantity=Decimal("2"),
            price=value.price,
            commission=Decimal("0"),
            source_time=value.source_time,
            evaluated_at=value.evaluated_at,
            idempotency_key="fill-key",
        )
        return [fill]


class FakeLifecycle:
    def __init__(self, repository: FakePaperRepository) -> None:
        self.repository = repository

    def reset_account(self, account_id, *, initial_cash, expected_revision):
        if expected_revision != self.repository.current.account.revision:
            raise RevisionConflict("stale paper account")
        self.repository.current = snapshot(revision=expected_revision + 1)
        self.repository.current.balances[0].available = initial_cash
        return self.repository.current

    def archive_account(self, account_id, *, expected_revision):
        if expected_revision != self.repository.current.account.revision:
            raise RevisionConflict("stale paper account")
        self.repository.current = snapshot(revision=expected_revision + 1, enabled=False)
        return self.repository.current


class FakeMarketService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None]] = []

    def quote(self, instrument_id, binding_id=None):
        self.calls.append((instrument_id, binding_id))
        return {
            "instrument_id": instrument_id,
            "binding_id": binding_id or BINDING,
            "provider": "fixture",
            "price": "101",
            "received_at": NOW.isoformat(),
        }


def test_paper_monitor_groups_quotes_and_runs_without_browser() -> None:
    repository = FakePaperRepository()
    duplicate = order("limit", order_id="second-order", idempotency_key="second-key")
    repository.current = snapshot(open_orders=[order("market"), duplicate])
    market = FakeMarketService()
    monitor = TradingPaperMonitor(
        repository_factory=lambda: repository,
        market_service_factory=lambda: market,
        interval_seconds=5,
    )
    assert asyncio.run(monitor.run_once()) == 1
    assert market.calls == [(INSTRUMENT, BINDING)]
    assert len(repository.observations) == 1
    assert monitor.diagnostics()["quote_count"] == 1


def test_paper_monitor_is_disabled_in_legacy_tests_by_default(monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_PERSISTENCE_MODE", "legacy_test")
    monkeypatch.delenv("OMNIX_TRADING_PAPER_MONITOR_IN_TESTS", raising=False)
    assert trading_paper_monitor_enabled() is False


def test_paper_routes_support_orders_reset_archive_and_revision_conflicts() -> None:
    repository = FakePaperRepository()
    lifecycle = FakeLifecycle(repository)
    app = FastAPI()
    app.include_router(
        create_trading_paper_router(
            repository_factory=lambda: repository,
            lifecycle_factory=lambda: lifecycle,
        )
    )
    client = TestClient(app)

    assert client.get("/api/trading/paper/accounts").status_code == 200
    placed = client.post(
        "/api/trading/paper/accounts/paper-1/orders",
        json={
            "order_id": "api-order",
            "instrument_id": INSTRUMENT,
            "binding_id": BINDING,
            "side": "buy",
            "order_type": "limit",
            "quantity": "1",
            "limit_price": "100",
            "idempotency_key": "api-order",
        },
    )
    assert placed.status_code == 201
    assert placed.json()["status"] == "open"

    reset = client.post(
        "/api/trading/paper/accounts/paper-1/reset",
        headers={"If-Match": "1"},
        json={"initial_cash": "25000"},
    )
    assert reset.status_code == 200
    assert reset.json()["balances"][0]["available"] == "25000"
    assert reset.json()["account"]["revision"] == 2

    stale = client.delete(
        "/api/trading/paper/accounts/paper-1",
        headers={"If-Match": "1"},
    )
    assert stale.status_code == 409
    archived = client.delete(
        "/api/trading/paper/accounts/paper-1",
        headers={"If-Match": "2"},
    )
    assert archived.status_code == 200
    assert archived.json()["account"]["enabled"] is False


def test_paper_authority_is_relational_and_no_live_execution_path_exists() -> None:
    migration = Path("src/app/persistence/migrations/0023_trading_paper.sql").read_text()
    for table in (
        "omnix_trading_paper_accounts",
        "omnix_trading_paper_balances",
        "omnix_trading_paper_positions",
        "omnix_trading_paper_orders",
        "omnix_trading_paper_fills",
        "omnix_trading_paper_ledger",
    ):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in migration
    assert "idempotency_key" in migration

    backend = "\n".join(
        path.read_text()
        for path in Path("src/app/trading").glob("paper*.py")
    ).lower()
    for forbidden in (
        "alpaca",
        "interactive_brokers",
        "submit_live_order",
        "broker_credentials",
    ):
        assert forbidden not in backend

    gateway = Path("src/app/gateway/trading_routes.py").read_text()
    assert "create_trading_paper_router" in gateway
    assert "register_trading_paper_monitor" in gateway
