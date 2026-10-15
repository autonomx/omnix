"""One cutover authority read serves a short request inside a snapshot scope (WP-5.6)."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.persistence.authority import (
    AuthorityOperation,
    PostgresAuthorityError,
    authority_snapshot_scope,
    require_authority_operation,
)


class _Connection:
    def __init__(self, dbname: str, state: str = "postgresql_open_for_writes") -> None:
        self.info = SimpleNamespace(host="127.0.0.1", port=5432, dbname=dbname)
        self.state = state
        self.reads = 0

    def execute(self, query, *args):
        assert "omnix_persistence_cutover" in query
        self.reads += 1
        return SimpleNamespace(fetchone=lambda: ("postgresql", self.state))


def test_inside_the_scope_each_database_is_read_once() -> None:
    first, other = _Connection("omnix"), _Connection("omnix_other")
    with authority_snapshot_scope():
        for _ in range(5):
            require_authority_operation(first, AuthorityOperation.RUNTIME_MUTATION)
        require_authority_operation(other, AuthorityOperation.RUNTIME_MUTATION)
    assert (first.reads, other.reads) == (1, 1)


def test_outside_the_scope_every_check_reads_and_a_closed_authority_still_refuses() -> None:
    connection = _Connection("omnix")
    require_authority_operation(connection, AuthorityOperation.RUNTIME_MUTATION)
    require_authority_operation(connection, AuthorityOperation.RUNTIME_MUTATION)
    assert connection.reads == 2

    frozen = _Connection("omnix", state="postgresql_activated_frozen")
    with authority_snapshot_scope():
        for _ in range(2):
            with pytest.raises(PostgresAuthorityError):
                require_authority_operation(frozen, AuthorityOperation.RUNTIME_MUTATION)
        assert require_authority_operation(frozen, AuthorityOperation.DIAGNOSTIC_READ).mode == "postgresql"
    assert frozen.reads == 1
