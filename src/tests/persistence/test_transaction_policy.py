from __future__ import annotations

from contextlib import contextmanager

import pytest

from app.persistence.transaction_policy import (
    TransactionContractError,
    TransactionPolicy,
    in_transaction,
    is_retryable_transaction_error,
    require_outside_transaction,
    run_transaction,
    transaction_scope,
)


class _Database:
    def __init__(self, failures: list[BaseException]) -> None:
        self.failures = list(failures)
        self.attempts = 0

    @contextmanager
    def transaction(self):
        self.attempts += 1
        if self.failures:
            raise self.failures.pop(0)
        yield object()


class _PostgresError(RuntimeError):
    def __init__(self, sqlstate: str) -> None:
        super().__init__(sqlstate)
        self.sqlstate = sqlstate


def test_retryable_sqlstates_are_bounded_to_transient_failures() -> None:
    assert is_retryable_transaction_error(_PostgresError("40001")) is True
    assert is_retryable_transaction_error(_PostgresError("40P01")) is True
    assert is_retryable_transaction_error(_PostgresError("57P03")) is True
    assert is_retryable_transaction_error(_PostgresError("23505")) is False


def test_nested_wrapped_sqlstate_is_detected() -> None:
    inner = _PostgresError("40001")
    outer = RuntimeError("wrapped")
    outer.__cause__ = inner

    assert is_retryable_transaction_error(outer) is True


def test_run_transaction_retries_transient_failure_with_backoff() -> None:
    database = _Database([_PostgresError("40001"), _PostgresError("40P01")])
    delays: list[float] = []

    result = run_transaction(
        database,
        lambda _connection: "committed",
        policy=TransactionPolicy(max_attempts=3, retry_base_seconds=0.01),
        sleep=delays.append,
    )

    assert result == "committed"
    assert database.attempts == 3
    assert delays == [0.01, 0.02]


def test_run_transaction_does_not_retry_non_transient_failure() -> None:
    database = _Database([_PostgresError("23505")])

    with pytest.raises(_PostgresError):
        run_transaction(database, lambda _connection: None)

    assert database.attempts == 1


def test_external_side_effect_guard_rejects_transaction_scope() -> None:
    assert in_transaction() is False
    require_outside_transaction("provider request")

    with transaction_scope():
        assert in_transaction() is True
        with pytest.raises(TransactionContractError, match="provider request"):
            require_outside_transaction("provider request")

    assert in_transaction() is False
