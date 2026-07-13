from __future__ import annotations

import hashlib
import os

import pytest

from app.persistence.blob_store import LocalBlobStore
from app.persistence.config import DatabaseSettings
from app.persistence.coordinated_recovery import CoordinatedRecoveryRepository
from app.persistence.database import PostgresDatabase
from app.persistence.identity_service import bootstrap_local_tenant
from app.persistence.migrations import apply_migrations
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
            pool_max=3,
            connect_timeout_seconds=10,
            statement_timeout_ms=30_000,
            application_name="omnix-coordinated-recovery-tests",
        )
    )


def _create_asset(work, context, *, asset_id: str, blob_store: LocalBlobStore, storage_key: str, content: bytes) -> None:
    blob = blob_store.put_bytes(storage_key, content)
    work.assets.create(
        context,
        {
            "id": asset_id,
            "module": "test",
            "asset_type": "binary",
            "mime_type": "application/octet-stream",
            "byte_size": len(content),
            "checksum_sha256": hashlib.sha256(content).hexdigest(),
            "storage_provider": blob_store.provider,
            "storage_key": blob["storage_key"],
        },
    )


def _restore_store(source: LocalBlobStore, destination: LocalBlobStore) -> None:
    for path in source.root.rglob("*"):
        if path.is_file():
            key = path.relative_to(source.root).as_posix()
            destination.put_bytes(key, path.read_bytes())


def test_backup_generation_captures_and_verifies_blob_authority(tmp_path) -> None:
    database = _database()
    blob_store = LocalBlobStore(tmp_path / "blobs")
    backup_store = LocalBlobStore(tmp_path / "backup-blobs")
    restored_store = LocalBlobStore(tmp_path / "restored-blobs")
    try:
        apply_migrations(database)
        context = bootstrap_local_tenant(database)
        with unit_of_work(database) as work:
            _create_asset(
                work,
                context,
                asset_id="asset:recovery",
                blob_store=blob_store,
                storage_key="assets/recovery.bin",
                content=b"coordinated-backup-content",
            )
            work.commit()

        with database.transaction() as connection:
            recovery = CoordinatedRecoveryRepository(connection)
            generation_id = recovery.create_generation(
                software_revision="test-head",
                schema_version="0013_coordinated_recovery",
                blob_root=blob_store.root,
                operator_note="integration recovery rehearsal",
            )
            manifest = recovery.capture_manifest(generation_id)
            recovery.copy_manifested_blobs(
                generation_id,
                source=blob_store,
                destination=backup_store,
            )
            recovery.record_database_backup(generation_id, "backup:test.dump")
        _restore_store(backup_store, restored_store)
        with database.transaction() as connection:
            verified = CoordinatedRecoveryRepository(connection).verify_blobs(
                generation_id,
                restored_store,
                database_restore_verified=True,
                migrations_verified=True,
                smoke_checks_verified=True,
            )

        assert manifest["asset_count"] >= 1
        assert verified["ok"] is True
        assert verified["missing"] == []
        assert verified["mismatched"] == []
        assert verified["checked"] == manifest["asset_count"]
        with database.connection() as connection:
            row = connection.execute(
                "SELECT status, database_backup_reference, manifest_hash "
                "FROM omnix_backup_generations WHERE id = %s",
                (generation_id,),
            ).fetchone()
        assert row is not None
        assert str(row[0]) == "verified"
        assert str(row[1]) == "backup:test.dump"
        assert len(str(row[2])) == 64
    finally:
        database.close()


def test_backup_verification_reports_missing_blob(tmp_path) -> None:
    database = _database()
    blob_store = LocalBlobStore(tmp_path / "missing-blobs")
    backup_store = LocalBlobStore(tmp_path / "missing-backup-blobs")
    restored_store = LocalBlobStore(tmp_path / "missing-restored-blobs")
    try:
        apply_migrations(database)
        context = bootstrap_local_tenant(database)
        with unit_of_work(database) as work:
            _create_asset(
                work,
                context,
                asset_id="asset:missing-recovery",
                blob_store=blob_store,
                storage_key="assets/missing.bin",
                content=b"will-be-missing",
            )
            work.commit()
        with database.transaction() as connection:
            recovery = CoordinatedRecoveryRepository(connection)
            generation_id = recovery.create_generation(
                software_revision="test-head",
                schema_version="0013_coordinated_recovery",
                blob_root=blob_store.root,
                operator_note="integration missing-blob rehearsal",
            )
            recovery.capture_manifest(generation_id)
            recovery.copy_manifested_blobs(
                generation_id,
                source=blob_store,
                destination=backup_store,
            )
            recovery.record_database_backup(generation_id, "backup:missing.dump")
        _restore_store(backup_store, restored_store)
        restored_store.delete("assets/missing.bin")
        with database.transaction() as connection:
            result = CoordinatedRecoveryRepository(connection).verify_blobs(
                generation_id,
                restored_store,
                database_restore_verified=True,
                migrations_verified=True,
                smoke_checks_verified=True,
            )
        assert result["ok"] is False
        assert "asset:missing-recovery" in result["missing"]
    finally:
        database.close()
