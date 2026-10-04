"""Background owners fence their transactions instead of probing one shared connection (WP-8.3)."""
from __future__ import annotations

from app.persistence.background_authority import background_execution, require_background_owner


class _Owner:
    def __init__(self, *, fences: bool = True) -> None:
        self.calls: list[object] = []
        if fences:
            self.fence = lambda connection: self.calls.append(("fence", connection))

    def require_live(self) -> None:
        self.calls.append("require_live")


class _Connection:
    def __init__(self) -> None:
        self.rolled_back = 0

    def rollback(self) -> None:
        self.rolled_back += 1


def test_a_checkout_fences_on_its_own_connection_and_hands_it_back_idle() -> None:
    owner, connection = _Owner(), _Connection()
    with background_execution(owner):
        owner.calls.clear()
        require_background_owner(connection)

    assert owner.calls == [("fence", connection)]
    assert connection.rolled_back == 1


def test_a_transaction_keeps_the_fencing_lock() -> None:
    owner, connection = _Owner(), _Connection()
    with background_execution(owner):
        owner.calls.clear()
        require_background_owner(connection, hold=True)

    assert owner.calls == [("fence", connection)]
    assert connection.rolled_back == 0


def test_an_owner_without_fencing_proves_liveness() -> None:
    owner = _Owner(fences=False)
    with background_execution(owner):
        owner.calls.clear()
        require_background_owner(_Connection())

    assert owner.calls == ["require_live"]


def test_foreground_code_is_not_checked() -> None:
    connection = _Connection()
    require_background_owner(connection)
    assert connection.rolled_back == 0
