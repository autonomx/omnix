from __future__ import annotations

import os

import pytest

from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.migrations import apply_migrations
from app.persistence.runtime_coordination import (
    PostgresRuntimeCoordinationRepository,
    RuntimeNodeConflict,
)


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
            application_name="omnix-runtime-coordination-tests",
        )
    )


def test_multiple_gateways_and_workers_are_visible_without_process_local_authority() -> None:
    database = _database()
    try:
        apply_migrations(database)
        with database.transaction() as connection:
            connection.execute("TRUNCATE omnix_runtime_failure_evidence, omnix_runtime_nodes")
            coordination = PostgresRuntimeCoordinationRepository(connection)
            coordination.register(
                node_id="gateway:a",
                node_type="gateway",
                software_version="test",
                lease_seconds=60,
            )
            coordination.register(
                node_id="gateway:b",
                node_type="gateway",
                software_version="test",
                lease_seconds=60,
            )
            coordination.register(
                node_id="worker:a",
                node_type="worker",
                software_version="test",
                resource_classes=["gpu:image"],
                lease_seconds=60,
            )
            coordination.register(
                node_id="worker:b",
                node_type="worker",
                software_version="test",
                resource_classes=["cpu"],
                lease_seconds=60,
            )
            assert [node["id"] for node in coordination.live_nodes(node_type="gateway")] == [
                "gateway:a",
                "gateway:b",
            ]
            assert [node["id"] for node in coordination.live_nodes(node_type="worker")] == [
                "worker:a",
                "worker:b",
            ]
    finally:
        database.close()


def test_expired_node_is_marked_stale_and_can_be_reclaimed() -> None:
    database = _database()
    try:
        apply_migrations(database)
        with database.transaction() as connection:
            connection.execute("TRUNCATE omnix_runtime_failure_evidence, omnix_runtime_nodes")
            coordination = PostgresRuntimeCoordinationRepository(connection)
            coordination.register(
                node_id="worker:crashed",
                node_type="worker",
                software_version="test",
                lease_seconds=60,
            )
            with pytest.raises(RuntimeNodeConflict):
                coordination.register(
                    node_id="worker:crashed",
                    node_type="worker",
                    software_version="test",
                    lease_seconds=60,
                )
            connection.execute(
                "UPDATE omnix_runtime_nodes SET lease_expires_at = CURRENT_TIMESTAMP - INTERVAL '1 second' "
                "WHERE id = 'worker:crashed'"
            )
            assert coordination.mark_stale_nodes() == ["worker:crashed"]
            reclaimed = coordination.register(
                node_id="worker:crashed",
                node_type="worker",
                software_version="test:new",
                lease_seconds=60,
            )
            assert reclaimed["status"] == "active"
            assert reclaimed["software_version"] == "test:new"
            evidence_id = coordination.record_failure_evidence(
                scenario="worker_crash_before_lease_expiry",
                node_id="worker:crashed",
                outcome="recovered",
                evidence={"claim_reused": False},
            )
            assert evidence_id > 0
    finally:
        database.close()


def test_draining_node_remains_heartbeat_capable_then_stops() -> None:
    database = _database()
    try:
        apply_migrations(database)
        with database.transaction() as connection:
            connection.execute("TRUNCATE omnix_runtime_failure_evidence, omnix_runtime_nodes")
            coordination = PostgresRuntimeCoordinationRepository(connection)
            coordination.register(
                node_id="gateway:drain",
                node_type="gateway",
                software_version="test",
                lease_seconds=60,
            )
            assert coordination.begin_draining("gateway:drain") is True
            heartbeat = coordination.heartbeat(node_id="gateway:drain", lease_seconds=60)
            assert heartbeat["status"] == "draining"
            assert coordination.stop("gateway:drain") is True
            assert coordination.live_nodes(node_type="gateway") == []
    finally:
        database.close()
