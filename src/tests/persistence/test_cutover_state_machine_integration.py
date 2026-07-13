from __future__ import annotations

import os

import pytest

from app.persistence.config import DatabaseSettings
from app.persistence.cutover_state import CutoverTransitionError, PostgresCutoverStateRepository
from app.persistence.database import PostgresDatabase
from app.persistence.migrations import apply_migrations


pytestmark = pytest.mark.skipif(
    not os.environ.get("OMNIX_TEST_DATABASE_URL"),
    reason="OMNIX_TEST_DATABASE_URL is required for PostgreSQL integration tests",
)


def _database() -> PostgresDatabase:
    return PostgresDatabase(
        DatabaseSettings(
            url=os.environ["OMNIX_TEST_DATABASE_URL"],
            pool_min=1,
            pool_max=3,
            connect_timeout_seconds=10,
            statement_timeout_ms=30_000,
            application_name="omnix-cutover-state-tests",
        )
    )


def _reset(connection) -> None:
    connection.execute("DELETE FROM omnix_cutover_transitions")
    connection.execute("DELETE FROM omnix_backup_blob_manifest")
    connection.execute("DELETE FROM omnix_backup_generations")
    connection.execute("DELETE FROM omnix_legacy_import_items")
    connection.execute("DELETE FROM omnix_legacy_import_runs")
    connection.execute(
        """
        UPDATE omnix_persistence_cutover
           SET mode = 'legacy_preflight', authority_state = 'legacy_preflight',
               import_run_id = NULL, source_hash = NULL,
               backup_generation_id = NULL, activated_at = NULL,
               opened_for_writes_at = NULL, stabilized_at = NULL,
               rollback_recorded_at = NULL, latest_authoritative_revision = NULL,
               destructive_override_at = NULL, metadata = '{}'::jsonb
         WHERE singleton = TRUE
        """
    )


def _restore_runtime_authority(database: PostgresDatabase) -> None:
    with database.transaction() as connection:
        connection.execute(
            """
            UPDATE omnix_persistence_cutover
               SET mode = 'postgresql', authority_state = 'postgresql_stabilized',
                   updated_at = CURRENT_TIMESTAMP
             WHERE singleton = TRUE
            """
        )


def _seed_verified_import_and_backup(connection) -> tuple[str, str]:
    run_id = "legacy-import:state-machine"
    backup_id = "backup:state-machine"
    connection.execute(
        """
        INSERT INTO omnix_legacy_import_runs (
            id, source_id, source_hash, format_version, status,
            discovered_counts, imported_counts, verification, completed_at
        ) VALUES (
            %s, 'state-machine-source', repeat('a', 64), 'omnix_legacy_bundle_v1',
            'completed', '{}'::jsonb, '{}'::jsonb, '{"ok": true}'::jsonb,
            CURRENT_TIMESTAMP
        )
        """,
        (run_id,),
    )
    connection.execute(
        """
        INSERT INTO omnix_backup_generations (
            id, status, software_revision, schema_version, blob_root,
            database_backup_reference, manifest_hash, verified_at
        ) VALUES (
            %s, 'verified', 'test-head', '0015_cutover_state_machine', '/tmp/blobs',
            'backup:test.dump', repeat('b', 64), CURRENT_TIMESTAMP
        )
        """,
        (backup_id,),
    )
    return run_id, backup_id


def test_cutover_requires_verified_import_backup_and_write_acknowledgement() -> None:
    database = _database()
    try:
        apply_migrations(database)
        with database.transaction() as connection:
            _reset(connection)
            run_id, backup_id = _seed_verified_import_and_backup(connection)
            state = PostgresCutoverStateRepository(connection)
            state.transition(
                to_state="imported_unverified",
                software_revision="test-head",
                schema_version="0015_cutover_state_machine",
                import_run_id=run_id,
            )
            state.transition(
                to_state="imported_verified",
                software_revision="test-head",
                schema_version="0015_cutover_state_machine",
            )
            activated = state.transition(
                to_state="postgresql_activated_frozen",
                software_revision="test-head",
                schema_version="0015_cutover_state_machine",
                backup_generation_id=backup_id,
                operator_note="verified backup captured before activation",
            )
            assert activated["mode"] == "postgresql"
            with pytest.raises(CutoverTransitionError, match="acknowledgement"):
                state.transition(
                    to_state="postgresql_open_for_writes",
                    software_revision="test-head",
                    schema_version="0015_cutover_state_machine",
                    operator_note="write reopening acknowledgement test",
                )
            opened = state.transition(
                to_state="postgresql_open_for_writes",
                software_revision="test-head",
                schema_version="0015_cutover_state_machine",
                write_reopen_acknowledged=True,
                latest_authoritative_revision="campaign:1@42",
                operator_note="operator accepts PostgreSQL write authority",
            )
            assert opened["authority_state"] == "postgresql_open_for_writes"
            stabilized = state.transition(
                to_state="postgresql_stabilized",
                software_revision="test-head",
                schema_version="0015_cutover_state_machine",
                operator_note="stabilization window healthy",
                latest_authoritative_revision="campaign:1@42",
            )
            assert stabilized["authority_state"] == "postgresql_stabilized"
    finally:
        _restore_runtime_authority(database)
        database.close()


def test_post_write_legacy_rollback_requires_destructive_acknowledgement() -> None:
    database = _database()
    try:
        apply_migrations(database)
        with database.transaction() as connection:
            _reset(connection)
            run_id, backup_id = _seed_verified_import_and_backup(connection)
            state = PostgresCutoverStateRepository(connection)
            for target, kwargs in (
                ("imported_unverified", {"import_run_id": run_id}),
                ("imported_verified", {}),
                ("postgresql_activated_frozen", {"backup_generation_id": backup_id}),
                ("postgresql_open_for_writes", {"write_reopen_acknowledged": True}),
            ):
                state.transition(
                    to_state=target,
                    software_revision="test-head",
                    schema_version="0015_cutover_state_machine",
                    operator_note=f"integration transition to {target}",
                    **kwargs,
                )
            with pytest.raises(CutoverTransitionError, match="destructive acknowledgement"):
                state.transition(
                    to_state="rollback_recorded",
                    software_revision="test-head",
                    schema_version="0015_cutover_state_machine",
                    operator_note="rollback acknowledgement validation",
                )
            rolled_back = state.transition(
                to_state="rollback_recorded",
                software_revision="test-head",
                schema_version="0015_cutover_state_machine",
                destructive_acknowledgement=True,
                operator_note="operator accepts loss of post-cutover writes",
            )
            assert rolled_back["mode"] == "rollback_recorded"
            row = connection.execute(
                "SELECT destructive_acknowledgement FROM omnix_cutover_transitions "
                "ORDER BY id DESC LIMIT 1"
            ).fetchone()
            assert bool(row[0]) is True
    finally:
        _restore_runtime_authority(database)
        database.close()
