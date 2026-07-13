from __future__ import annotations

import os

import pytest

from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.identity_service import bootstrap_local_tenant
from app.persistence.migrations import apply_migrations
from app.persistence.outbox_repository import OutboxDeliveryConflict
from app.persistence.unit_of_work import unit_of_work


pytestmark = pytest.mark.skipif(
    not os.environ.get("OMNIX_TEST_DATABASE_URL"),
    reason="OMNIX_TEST_DATABASE_URL is required for PostgreSQL integration tests",
)


def _database() -> PostgresDatabase:
    return PostgresDatabase(
        DatabaseSettings(
            url=os.environ["OMNIX_TEST_DATABASE_URL"],
            pool_min=1,
            pool_max=6,
            connect_timeout_seconds=10,
            statement_timeout_ms=30_000,
            application_name="omnix-outbox-delivery-tests",
        )
    )


def _reset(database: PostgresDatabase) -> None:
    apply_migrations(database)
    with database.transaction() as connection:
        connection.execute(
            "TRUNCATE omnix_side_effect_receipts, omnix_outbox_dead_letters, "
            "omnix_outbox_consumer_inbox, omnix_outbox_sequences, "
            "omnix_outbox_events, omnix_workspace_memberships, omnix_workspaces, "
            "omnix_users CASCADE"
        )


def test_ordering_key_claims_one_unpublished_event_at_a_time() -> None:
    database = _database()
    try:
        _reset(database)
        context = bootstrap_local_tenant(database)
        with unit_of_work(database) as work:
            first_id = work.outbox.append(
                context,
                aggregate_type="campaign",
                aggregate_id="campaign:1",
                event_type="campaign.turn.committed",
                payload={"revision": 1},
                ordering_key="campaign:1",
                correlation_id="request:1",
            )
            second_id = work.outbox.append(
                context,
                aggregate_type="campaign",
                aggregate_id="campaign:1",
                event_type="campaign.turn.committed",
                payload={"revision": 2},
                ordering_key="campaign:1",
                correlation_id="request:2",
            )
            work.commit()

        with unit_of_work(database) as work:
            first_batch = work.outbox.claim_batch(consumer_id="publisher:a", limit=10)
            assert [event["id"] for event in first_batch] == [first_id]
            assert first_batch[0]["aggregate_sequence"] == 1
            assert first_batch[0]["schema_version"] == 1
            assert work.outbox.mark_published(
                event_id=first_id,
                claim_token=first_batch[0]["claim_token"],
            )
            work.commit()

        with unit_of_work(database) as work:
            second_batch = work.outbox.claim_batch(consumer_id="publisher:b", limit=10)
            assert [event["id"] for event in second_batch] == [second_id]
            assert second_batch[0]["aggregate_sequence"] == 2
            assert work.outbox.mark_published(
                event_id=second_id,
                claim_token=second_batch[0]["claim_token"],
            )
            work.commit()
    finally:
        database.close()


def test_consumer_inbox_deduplicates_completed_delivery_and_allows_replay() -> None:
    database = _database()
    try:
        _reset(database)
        context = bootstrap_local_tenant(database)
        with unit_of_work(database) as work:
            event_id = work.outbox.append(
                context,
                aggregate_type="asset",
                aggregate_id="asset:1",
                event_type="asset.created",
                payload={"kind": "image"},
                event_key="event:asset:1",
            )
            work.commit()
        assert event_id > 0

        with unit_of_work(database) as work:
            claim = work.outbox_consumers.begin(
                consumer_id="search-index",
                event_key="event:asset:1",
            )
            assert claim["state"] == "claimed"
            assert work.outbox_consumers.complete(
                consumer_id="search-index",
                event_key="event:asset:1",
                claim_token=claim["claim_token"],
                result={"indexed": True},
            )
            work.commit()

        with unit_of_work(database) as work:
            duplicate = work.outbox_consumers.begin(
                consumer_id="search-index",
                event_key="event:asset:1",
            )
            assert duplicate["state"] == "duplicate_completed"
            assert duplicate["result"] == {"indexed": True}
            assert work.outbox_consumers.reset_for_replay(
                consumer_id="search-index",
                event_key="event:asset:1",
            )
            work.commit()

        with unit_of_work(database) as work:
            replay = work.outbox_consumers.begin(
                consumer_id="search-index",
                event_key="event:asset:1",
            )
            assert replay["state"] == "claimed"
            assert replay["attempt_count"] == 1
            work.rollback()
    finally:
        database.close()


def test_consumer_poison_event_is_quarantined() -> None:
    database = _database()
    try:
        _reset(database)
        context = bootstrap_local_tenant(database)
        with unit_of_work(database) as work:
            work.outbox.append(
                context,
                aggregate_type="job",
                aggregate_id="job:poison",
                event_type="job.completed",
                payload={"bad": True},
                event_key="event:poison",
            )
            claim = work.outbox_consumers.begin(
                consumer_id="projection",
                event_key="event:poison",
            )
            status = work.outbox_consumers.fail(
                consumer_id="projection",
                event_key="event:poison",
                claim_token=claim["claim_token"],
                error="unsupported schema",
                max_attempts=1,
            )
            work.commit()
        assert status == "dead_letter"

        with database.connection() as connection:
            row = connection.execute(
                "SELECT reason, attempt_count FROM omnix_outbox_dead_letters "
                "WHERE consumer_id = 'projection' AND event_key = 'event:poison'"
            ).fetchone()
        assert row is not None
        assert str(row[0]) == "unsupported schema"
        assert int(row[1]) == 1
    finally:
        database.close()


def test_side_effect_receipt_reuses_result_and_rejects_key_mismatch() -> None:
    database = _database()
    try:
        _reset(database)
        context = bootstrap_local_tenant(database)
        with unit_of_work(database) as work:
            reserved = work.side_effects.reserve(
                context,
                effect_scope="webhook",
                idempotency_key="delivery:1",
                request={"event": "asset.created"},
            )
            assert reserved["owner"] is True
            assert work.side_effects.complete(
                context,
                effect_scope="webhook",
                idempotency_key="delivery:1",
                result={"status": 202},
            )
            work.commit()

        with unit_of_work(database) as work:
            reused = work.side_effects.reserve(
                context,
                effect_scope="webhook",
                idempotency_key="delivery:1",
                request={"event": "asset.created"},
            )
            assert reused == {
                "owner": False,
                "status": "completed",
                "result": {"status": 202},
                "error": None,
            }
            with pytest.raises(OutboxDeliveryConflict, match="different"):
                work.side_effects.reserve(
                    context,
                    effect_scope="webhook",
                    idempotency_key="delivery:1",
                    request={"event": "different"},
                )
            work.rollback()
    finally:
        database.close()
