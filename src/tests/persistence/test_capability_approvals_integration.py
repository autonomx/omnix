from __future__ import annotations

import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Barrier
from urllib.parse import urlsplit

import pytest

from app.persistence.capability_approval_repository import (
    CapabilityApprovalConflict,
    PostgresCapabilityApprovalRepository,
    proposal_digest,
)
from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase, PostgresConstraintError
from app.persistence.identity_service import bootstrap_local_tenant

pytestmark = pytest.mark.skipif(
    not os.environ.get("OMNIX_TEST_DATABASE_URL"),
    reason="OMNIX_TEST_DATABASE_URL is required for PostgreSQL integration tests",
)


@pytest.fixture
def database():
    url = os.environ["OMNIX_TEST_DATABASE_URL"]
    assert urlsplit(url).path in {"/omnix_test", "/omnix_refactor_baseline"}
    database = PostgresDatabase(DatabaseSettings(url=url, pool_min=1, pool_max=4))
    context = bootstrap_local_tenant(database)
    try:
        yield database, context
    finally:
        database.close()


def _payload():
    return {"capability_id": "gmail.send_email", "action": "gmail.send_email", "input": {"body": "Hello"}, "session": "chat:test"}


def _ledger(identifier):
    return {"execution_id": uuid.uuid4().hex, "proposal_id": identifier, "tool_id": "gmail", "action_id": "gmail.send_email", "state_changed": False, "error": "execution_reserved"}


def _create(database, *, required=True):
    db, context = database
    with db.transaction() as connection:
        return PostgresCapabilityApprovalRepository(connection).create(
            context, capability_id="gmail.send_email", payload=_payload(), approval_required=required,
        )


def _decide(database, identifier, *, approve=True):
    db, context = database
    with db.transaction() as connection:
        return PostgresCapabilityApprovalRepository(connection).decide(context, identifier, approve=approve)


def _consume(database, identifier, *, payload=None, ledger=None):
    db, context = database
    with db.transaction() as connection:
        return PostgresCapabilityApprovalRepository(connection).consume(
            context, identifier, expected_payload=payload or _payload(), ledger_payload=ledger or _ledger(identifier),
        )


def _expire(database, identifier):
    db, context = database
    with db.transaction() as connection:
        connection.execute(
            "UPDATE omnix_capability_approvals SET created_at = CURRENT_TIMESTAMP - INTERVAL '1 day', expires_at = CURRENT_TIMESTAMP - INTERVAL '1 second' WHERE workspace_id = %s AND id = %s",
            (context.workspace_id, identifier),
        )


def test_required_approval_cannot_be_consumed_without_decision(database):
    proposal = _create(database)
    with pytest.raises(CapabilityApprovalConflict, match="not_approved"):
        _consume(database, proposal.id)


def test_approval_consumption_and_ledger_reservation_are_atomic(database):
    proposal = _create(database)
    _decide(database, proposal.id)
    ledger = _ledger(proposal.id)
    assert _consume(database, proposal.id, ledger=ledger).decision == "consumed"
    db, context = database
    with db.connection() as connection:
        row = connection.execute("SELECT payload FROM omnix_module_records WHERE workspace_id = %s AND module = 'assistant-tools' AND record_type = 'execution-ledger' AND record_id = %s", (context.workspace_id, ledger["execution_id"])).fetchone()
        assert row[0] == ledger
    with pytest.raises(CapabilityApprovalConflict, match="consumed"):
        _consume(database, proposal.id)


@pytest.mark.parametrize("field", ["input", "session", "capability_id", "action"])
def test_changed_input_or_subject_is_rejected(database, field):
    proposal = _create(database)
    _decide(database, proposal.id)
    payload = _payload()
    payload[field] = {"body": "Other"} if field == "input" else "changed"
    with pytest.raises(CapabilityApprovalConflict, match="digest_mismatch"):
        _consume(database, proposal.id, payload=payload)


def test_server_payload_tampering_is_rejected(database):
    proposal = _create(database)
    _decide(database, proposal.id)
    db, context = database
    with db.transaction() as connection:
        connection.execute("UPDATE omnix_capability_approvals SET proposal_payload = '{}'::jsonb WHERE workspace_id = %s AND id = %s", (context.workspace_id, proposal.id))
    with pytest.raises(CapabilityApprovalConflict, match="digest_mismatch"):
        _consume(database, proposal.id)


@pytest.mark.parametrize("operation", ["decide", "consume"])
def test_expiry_is_checked_by_database_time(database, operation):
    proposal = _create(database, required=False)
    _expire(database, proposal.id)
    with pytest.raises(CapabilityApprovalConflict, match="expired"):
        (_decide if operation == "decide" else _consume)(database, proposal.id)


def test_denied_proposal_cannot_execute_or_be_reapproved(database):
    proposal = _create(database, required=False)
    _decide(database, proposal.id, approve=False)
    with pytest.raises(CapabilityApprovalConflict):
        _consume(database, proposal.id)
    with pytest.raises(CapabilityApprovalConflict):
        _decide(database, proposal.id)


def test_server_automatic_policy_still_uses_single_use_proposal(database):
    proposal = _create(database, required=False)
    assert _consume(database, proposal.id).decision == "consumed"
    with pytest.raises(CapabilityApprovalConflict):
        _consume(database, proposal.id)


def test_proposals_are_scoped_to_workspace(database):
    proposal = _create(database)
    db, context = database
    other = replace(context, workspace_id="workspace:not-this-tenant")
    with db.transaction() as connection:
        repository = PostgresCapabilityApprovalRepository(connection)
        assert repository.get(other, proposal.id) is None
        with pytest.raises(CapabilityApprovalConflict):
            repository.decide(other, proposal.id, approve=True)
        with pytest.raises(CapabilityApprovalConflict, match="not_found"):
            repository.consume(other, proposal.id, expected_payload=_payload(), ledger_payload=_ledger(proposal.id))


def test_concurrent_execute_consumes_once(database):
    proposal = _create(database)
    _decide(database, proposal.id)
    barrier = Barrier(2)

    def attempt():
        barrier.wait(timeout=10)
        try:
            _consume(database, proposal.id)
            return "consumed"
        except CapabilityApprovalConflict:
            return "rejected"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(lambda _: attempt(), range(2)))
    assert sorted(outcomes) == ["consumed", "rejected"]
    db, context = database
    with db.connection() as connection:
        row = connection.execute("SELECT count(*) FROM omnix_module_records WHERE workspace_id = %s AND module = 'assistant-tools' AND record_type = 'execution-ledger' AND payload->>'proposal_id' = %s", (context.workspace_id, proposal.id)).fetchone()
        assert row[0] == 1


def test_ledger_failure_rolls_back_consumption(database):
    proposal = _create(database, required=False)
    ledger = _ledger(proposal.id)
    # A duplicate execution key violates the ledger key; consumption must roll back.
    ledger["execution_id"] = "duplicate-" + uuid.uuid4().hex
    db, context = database
    with db.transaction() as connection:
        connection.execute("INSERT INTO omnix_module_records (workspace_id, module, record_type, record_id, owner_user_id, payload) VALUES (%s, 'assistant-tools', 'execution-ledger', %s, %s, '{}'::jsonb)", (context.workspace_id, ledger["execution_id"], context.user_id))
    with pytest.raises(PostgresConstraintError):
        _consume(database, proposal.id, ledger=ledger)
    with db.connection() as connection:
        stored = PostgresCapabilityApprovalRepository(connection).get(context, proposal.id)
        assert stored.decision == "pending"


def test_proposal_ids_are_random_even_for_identical_inputs(database):
    proposals = [_create(database) for _ in range(3)]
    assert len({proposal.id for proposal in proposals}) == 3
    assert all(len(proposal.id) == 32 for proposal in proposals)
    assert len({proposal.proposal_digest for proposal in proposals}) == 1


def test_canonical_digest_ignores_key_order():
    assert proposal_digest({"input": {"a": 1, "b": 2}, "session": None}) == proposal_digest({"session": None, "input": {"b": 2, "a": 1}})
    with pytest.raises(ValueError):
        proposal_digest({"input": float("nan")})
