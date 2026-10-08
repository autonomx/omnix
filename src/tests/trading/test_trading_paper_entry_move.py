"""Moving a working risk entry from the chart (TVP-7.3)."""
from __future__ import annotations

from decimal import Decimal

from app.apps.trading.paper import PaperBalance, PaperOrder
from app.apps.trading.paper_entry_move import snapshot_without_order
from app.apps.trading.paper_protection import PaperPositionProtection

from .test_trading_paper_risk_authority import (
    BINDING,
    INSTRUMENT,
    DailyPnl,
    Protections,
    Repo,
    _client,
    snapshot,
)

HEADERS = {"X-Omnix-Paper-Order-Management": "v2"}
URL = "/api/trading/paper/accounts/paper-1/risk-orders/entry-1/move"


class MoveRepo(Repo):
    def __init__(self, events: list[str]) -> None:
        super().__init__(events)
        self.fail_replace: str | None = None
        self.replaced = []
        entry = PaperOrder(
            account_id="paper-1",
            order_id="entry-1",
            instrument_id=INSTRUMENT,
            binding_id=BINDING,
            side="buy",
            order_type="limit",
            quantity=Decimal("100"),
            limit_price=Decimal("10"),
            idempotency_key="entry-1",
            reserved_cash=Decimal("1000"),
            time_in_force="day",
        )
        self.current = snapshot(open_orders=[entry]).model_copy(
            update={"balances": [PaperBalance(currency="USD", available=Decimal("99000"), reserved=Decimal("1000"))]}
        )

    def replace_order(self, account_id, order_id, replacement, *, authority):
        self.events.append(f"replace:{authority.kind}")
        if self.fail_replace:
            raise ValueError(self.fail_replace)
        self.replaced.append((order_id, replacement))
        cancelled = self.current.open_orders[0].model_copy(update={"status": "cancelled"})
        return cancelled, PaperOrder(account_id=account_id, **replacement.model_dump())


def _protections(events: list[str], *, entry_order_id: str = "entry-1") -> Protections:
    protections = Protections(events)
    protections.values = [
        PaperPositionProtection(
            account_id="paper-1",
            instrument_id=INSTRUMENT,
            binding_id=BINDING,
            entry_order_id=entry_order_id,
            take_profit=Decimal("12"),
            stop_loss=Decimal("9"),
            status="pending_entry",
            trigger_reason="entry_armed",
        )
    ]
    return protections


def _move(**overrides) -> dict[str, object]:
    return {"order_id": "entry-2", "idempotency_key": "entry-2", "trigger_price": "9.5", **overrides}


def test_a_moved_entry_is_resized_to_the_same_risk_and_replaced_atomically() -> None:
    events: list[str] = []
    repo = MoveRepo(events)
    protections = _protections(events)
    response = _client(repo, protections, DailyPnl()).post(URL, json=_move(), headers=HEADERS)
    assert response.status_code == 200, response.text
    body = response.json()
    # The original risks (10 - 9) x 100 = 100 USD; at 9.5 the same risk is 200 shares.
    assert body["order"]["quantity"] == "200"
    assert body["order"]["limit_price"] == "9.5"
    assert body["order"]["time_in_force"] == "day"
    assert body["cancelled"]["order_id"] == "entry-1"
    assert body["protection"]["entry_order_id"] == "entry-2"
    assert body["protection"]["stop_loss"] == "9"
    assert body["protection"]["take_profit"] == "12"
    assert events == ["arm", "replace:manual_risk"]
    assert repo.replaced[0][0] == "entry-1"


def test_a_failed_replacement_puts_the_stop_back_on_the_working_entry() -> None:
    events: list[str] = []
    repo = MoveRepo(events)
    repo.fail_replace = "paper_order_not_open: entry-1"
    protections = _protections(events)
    response = _client(repo, protections).post(URL, json=_move(), headers=HEADERS)
    assert response.status_code == 409, response.text
    assert events == ["arm", "replace:manual_risk", "arm"]
    assert protections.values[0].entry_order_id == "entry-1"
    assert protections.values[0].stop_loss == Decimal("9")


def test_only_risk_entries_with_a_pending_stop_move() -> None:
    events: list[str] = []
    response = _client(MoveRepo(events), _protections(events, entry_order_id="other")).post(URL, json=_move(), headers=HEADERS)
    assert response.status_code == 409
    assert response.json()["detail"] == "paper_risk_entry_not_movable"
    assert events == []


def test_an_entry_moved_below_its_stop_is_rejected_by_the_risk_rules() -> None:
    events: list[str] = []
    response = _client(MoveRepo(events), _protections(events)).post(URL, json=_move(trigger_price="8.9"), headers=HEADERS)
    assert response.status_code == 409
    assert "STOP_NOT_BELOW_ENTRY" in response.json()["detail"]["reason_codes"]
    assert events == []


def test_moving_needs_the_order_management_header() -> None:
    events: list[str] = []
    response = _client(MoveRepo(events), _protections(events)).post(URL, json=_move())
    assert response.status_code == 409
    assert response.json()["detail"] == "paper_order_cancellation_disabled"


def test_sizing_treats_the_working_entry_as_cancelled() -> None:
    repo = MoveRepo([])
    freed = snapshot_without_order(repo.current, repo.current.open_orders[0])
    assert freed.open_orders == []
    assert freed.balances[0].available == Decimal("100000")
    assert freed.balances[0].reserved == Decimal("0")
