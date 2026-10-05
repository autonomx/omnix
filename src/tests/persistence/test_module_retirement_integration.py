"""Retiring a module ends its in-flight work through the kernel repositories (PA-4.3)."""
from __future__ import annotations

import json
import os
import uuid

import pytest

from app.jobs.models import CreateJobRequest
from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.job_store import PostgresJobStoreAdapter
from app.persistence.module_retirement import (
    InFlightWork,
    OutboxSubscription,
    RetirementSubject,
    cancel_remaining,
    fail_unfinished_jobs,
    in_flight_work,
    reactivate,
    set_state,
)
from app.persistence.module_states import read_module_state
from app.persistence.unit_of_work import unit_of_work
from app.runtime.tenant_context import current_tenant

pytestmark = [
    pytest.mark.postgres,
    # The outbox relay tests claim every pending event.
    pytest.mark.xdist_group("outbox"),
    pytest.mark.skipif(not os.environ.get("OMNIX_TEST_DATABASE_URL"), reason="OMNIX_TEST_DATABASE_URL is required"),
]


@pytest.fixture
def database():
    database = PostgresDatabase(DatabaseSettings(url=os.environ["OMNIX_TEST_DATABASE_URL"], pool_min=1, pool_max=4))
    try:
        yield database
    finally:
        database.close()


def _approval(connection, workspace_id: str, user_id: str, capability_id: str, decision: str) -> str:
    identifier = uuid.uuid4().hex
    connection.execute(
        """INSERT INTO omnix_capability_approvals (id, workspace_id, subject_type, subject_id, capability_id,
               proposal_digest, proposal_payload, approval_required, requested_by, decision, expires_at)
           VALUES (%s, %s, 'tool_proposal', %s, %s, %s, '{}'::jsonb, TRUE, %s, %s,
                   CURRENT_TIMESTAMP + INTERVAL '1 hour')""",
        (identifier, workspace_id, identifier, capability_id, "0" * 64, user_id, decision),
    )
    return identifier


def test_retirement_cancels_jobs_dead_letters_deliveries_and_expires_approvals(database) -> None:
    suffix = uuid.uuid4().hex[:8]
    module_id, job_type, aggregate = f"gone-{suffix}", f"gone_{suffix}.work", f"gone-{suffix}-item"
    capability = f"gone_{suffix}.act"
    subject = RetirementSubject(
        module_id, job_types=(job_type,),
        subscriptions=(OutboxSubscription(f"gone-{suffix}.consumer", (aggregate,), "item.*"),),
        capability_ids=(capability,),
    )
    context = current_tenant()
    store = PostgresJobStoreAdapter(database)
    request = lambda kind: CreateJobRequest(module="retire-test", type=kind, resource_class="cpu")  # noqa: E731
    queued, running = store.create_job(request(job_type)).id, store.create_job(request(job_type)).id
    other = store.create_job(request(f"kept_{suffix}.work")).id
    with unit_of_work(database) as work:
        work.connection.execute(
            """UPDATE omnix_jobs SET status = 'running', lease_owner = 'worker', lease_token = 'token',
                      lease_expires_at = clock_timestamp() + INTERVAL '1 minute' WHERE id = %s""",
            (running,),
        )
        events = {
            name: work.outbox.append(context, aggregate_type=aggregate, aggregate_id="a", event_type=event_type,
                                     payload={"name": name}, event_key=f"{suffix}-{name}")
            for name, event_type in (("undelivered", "item.created"), ("delivered", "item.created"),
                                     ("unmatched", "other.created"))
        }
        work.connection.execute(
            """INSERT INTO omnix_outbox_consumer_inbox (consumer_id, event_key, status, completed_at)
               VALUES (%s, %s, 'completed', CURRENT_TIMESTAMP)""",
            (f"gone-{suffix}.consumer", f"{suffix}-delivered"),
        )
        pending = _approval(work.connection, context.workspace_id, context.user_id, capability, "pending")
        approved = _approval(work.connection, context.workspace_id, context.user_id, capability, "approved")
        denied = _approval(work.connection, context.workspace_id, context.user_id, capability, "denied")
        work.commit()
    assert set(events) == {"undelivered", "delivered", "unmatched"}

    before = in_flight_work(database, subject)
    report = cancel_remaining(database, subject)
    asked = in_flight_work(database, subject)
    failed = fail_unfinished_jobs(database, subject)
    after = in_flight_work(database, subject)

    assert before == InFlightWork(active_jobs=1, waiting_jobs=1, undelivered_events=1, open_approvals=2)
    assert not before.drained
    assert (report.canceled_jobs, report.cancel_requested_jobs) == (1, 1)
    assert (report.dead_lettered_deliveries, report.expired_approvals) == (1, 2)
    assert asked == InFlightWork(active_jobs=1)
    assert failed == 1 and after.empty
    with unit_of_work(database) as work:
        connection = work.connection
        jobs = dict(connection.execute(
            "SELECT id, status || ':' || COALESCE(error->>'code', '') FROM omnix_jobs WHERE id = ANY(%s)",
            ([queued, running, other],),
        ).fetchall())
        decisions = dict(connection.execute(
            "SELECT id, decision || ':' || COALESCE(reason, '') FROM omnix_capability_approvals WHERE id = ANY(%s)",
            ([pending, approved, denied],),
        ).fetchall())
        dead = connection.execute(
            "SELECT event_key, reason FROM omnix_outbox_dead_letters WHERE consumer_id = %s",
            (f"gone-{suffix}.consumer",),
        ).fetchall()
        # The relay treats the dead-lettered delivery as final instead of retrying it.
        reservation = work.outbox_consumers.begin(consumer_id=f"gone-{suffix}.consumer", event_key=f"{suffix}-undelivered")
        work.rollback()
    assert jobs == {queued: "canceled:module_retired", running: "failed:module_retired", other: "queued:"}
    assert decisions == {pending: "expired:module_retired", approved: "expired:module_retired", denied: "denied:"}
    assert dead == [(f"{suffix}-undelivered", "module_retired")]
    assert reservation["state"] == "dead_lettered"
    assert json.dumps(report.skipped_deliveries) == "[]"


def test_the_module_state_moves_to_retired(database) -> None:
    module_id = f"gone-{uuid.uuid4().hex[:8]}"

    set_state(database, module_id, "draining")
    set_state(database, module_id, "retired")

    with database.connection() as connection:
        state = read_module_state(connection, module_id)
    assert state.state == "retired" and not state.accepts_follow_up()


def test_a_stopped_retirement_can_be_undone_but_a_finished_one_cannot(database) -> None:
    module_id = f"gone-{uuid.uuid4().hex[:8]}"
    set_state(database, module_id, "draining")

    assert reactivate(database, module_id).accepts_new_work
    set_state(database, module_id, "retired")
    with pytest.raises(ValueError, match="already retired"):
        reactivate(database, module_id)
