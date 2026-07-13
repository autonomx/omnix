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


def test_backup_generation_captures_and_verifies_blob_authority(tmp_path) -> None:
    database = _database()
    blob_store = LocalBlobStore(tmp_path / "blobs")
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
            )
            manifest = recovery.capture_manifest(generation_id)
            recovery.record_database_backup(generation_id, "backup:test.dump")
            verified = recovery.verify_blobs(generation_id, blob_store)

        assert manifest["asset_count"] >= 1
        assert verified == {
            "ok": True,
            "missing": [],
            "mismatched": [],
            "checked": manifest["asset_count"],
        }
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
            )
            recovery.capture_manifest(generation_id)
            recovery.record_database_backup(generation_id, "backup:missing.dump")
        blob_store.delete("assets/missing.bin")
        with database.transaction() as connection:
            result = CoordinatedRecoveryRepository(connection).verify_blobs(generation_id, blob_store)
        assert result["ok"] is False
        assert "asset:missing-recovery" in result["missing"]
    finally:
        database.close()
