from __future__ import annotations

from decimal import Decimal

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.trading.paper import PaperAccount, PaperAccountSnapshot, PaperBalance, PaperOrder
from app.trading.paper_api import create_trading_paper_router


INSTRUMENT = "equity:NYSE:TEST"
HEADERS = {"X-Omnix-Paper-Order-Management": "v2"}


class Repo:
    def __init__(self) -> None:
        self.account = PaperAccount(
            account_id="paper-1",
            name="Paper",
            base_currency="USD",
            commission_bps=Decimal("0"),
        )
        self.orders: dict[str, PaperOrder] = {
            "old": PaperOrder(
                account_id="paper-1",
                order_id="old",
                instrument_id=INSTRUMENT,
                binding_id=None,
                side="buy",
                order_type="limit",
                quantity=Decimal("1"),
                limit_price=Decimal("10"),
                idempotency_key="old",
            )
        }
        self.fail_replacement = False

    def list_accounts(self, limit=100):
        return [self.account]

    def snapshot(self, account_id):
        history = list(self.orders.values())
        return PaperAccountSnapshot(
            account=self.account,
            balances=[PaperBalance(currency="USD", available=Decimal("1000"))],
            positions=[],
            open_orders=[order for order in history if order.status == "open"],
            order_history=history,
            recent_fills=[],
            recent_ledger=[],
        )

    def cancel_order(self, account_id, order_id):
        order = self.orders.get(order_id)
        if order is None or order.status != "open":
            raise ValueError("paper_order_not_open")
        cancelled = order.model_copy(update={"status": "cancelled"})
        self.orders[order_id] = cancelled
        return cancelled

    def place_order(self, account_id, request):
        if self.fail_replacement:
            raise ValueError("insufficient_paper_cash")
        order = PaperOrder(account_id=account_id, **request.model_dump())
        self.orders[order.order_id] = order
        return order


class Lifecycle:
    pass


class Protections:
    def list(self, *args, **kwargs):
        return []


def _client(repo: Repo) -> TestClient:
    app = FastAPI()
    app.include_router(
        create_trading_paper_router(
            repository_factory=lambda: repo,
            lifecycle_factory=lambda: Lifecycle(),
            protection_repository_factory=lambda: Protections(),
        )
    )
    return TestClient(app)


def test_cancel_order_is_server_authoritative() -> None:
    repo = Repo()
    response = _client(repo).delete(
        "/api/trading/paper/accounts/paper-1/orders/old",
        headers=HEADERS,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"
    assert repo.orders["old"].status == "cancelled"


def test_replace_cancels_old_before_submitting_new_identity() -> None:
    repo = Repo()
    response = _client(repo).post(
        "/api/trading/paper/accounts/paper-1/orders/old/replace",
        headers=HEADERS,
        json={
            "replacement": {
                "order_id": "new",
                "instrument_id": INSTRUMENT,
                "binding_id": None,
                "side": "buy",
                "order_type": "limit",
                "quantity": "2",
                "limit_price": "9.5",
                "stop_price": None,
                "reference_price": None,
                "idempotency_key": "new",
            }
        },
    )
    assert response.status_code == 200
    assert response.json()["cancelled"]["order_id"] == "old"
    assert response.json()["replacement"]["order_id"] == "new"
    assert repo.orders["old"].status == "cancelled"
    assert repo.orders["new"].status == "open"


def test_replace_failure_never_resurrects_cancelled_order() -> None:
    repo = Repo()
    repo.fail_replacement = True
    response = _client(repo).post(
        "/api/trading/paper/accounts/paper-1/orders/old/replace",
        headers=HEADERS,
        json={
            "replacement": {
                "order_id": "new",
                "instrument_id": INSTRUMENT,
                "binding_id": None,
                "side": "buy",
                "order_type": "limit",
                "quantity": "1000",
                "limit_price": "50",
                "stop_price": None,
                "reference_price": None,
                "idempotency_key": "new",
            }
        },
    )
    assert response.status_code == 409
    assert "replacement_failed_after_cancel" in response.json()["detail"]
    assert repo.orders["old"].status == "cancelled"
    assert "new" not in repo.orders
