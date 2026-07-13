from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from app.persistence.asset_service import (
    create_asset,
    delete_asset,
    import_legacy_asset_manifest,
    put_setting,
    read_asset,
    register_secret_reference,
)
from app.persistence.blob_store import LocalBlobStore
from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.errors import RevisionConflict
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
            pool_max=4,
            connect_timeout_seconds=10,
            statement_timeout_ms=30_000,
            application_name="omnix-asset-tests",
        )
    )


def _reset(database: PostgresDatabase) -> None:
    apply_migrations(database)
    with database.transaction() as connection:
        connection.execute(
            "TRUNCATE omnix_asset_versions, omnix_assets, omnix_settings, "
            "omnix_secret_references, omnix_audit_events, omnix_idempotency_keys, "
            "omnix_workspace_memberships, omnix_workspaces, omnix_users CASCADE"
        )


def test_asset_metadata_and_blob_lifecycle(tmp_path: Path) -> None:
    database = _database()
    store = LocalBlobStore(tmp_path / "blobs")
    try:
        _reset(database)
        context = bootstrap_local_tenant(database)
        asset = create_asset(
            database,
            store,
            context,
            asset_id="asset:test-image",
            module="image",
            asset_type="image",
            mime_type="image/png",
            storage_key="image/test.png",
            content=b"png-content",
            metadata={"prompt_redacted": True},
        )
        assert asset["revision"] == 1
        assert asset["byte_size"] == len(b"png-content")
        loaded, content = read_asset(database, store, context, asset["id"])
        assert loaded["checksum_sha256"] == asset["checksum_sha256"]
        assert content == b"png-content"

        deleted = delete_asset(
            database,
            store,
            context,
            asset_id=asset["id"],
            expected_revision=1,
        )
        assert deleted["lifecycle_status"] == "deleted"
        assert deleted["revision"] == 2
        assert store.exists("image/test.png") is False
        with pytest.raises(KeyError):
            read_asset(database, store, context, asset["id"])
    finally:
        database.close()


def test_asset_queries_are_tenant_scoped(tmp_path: Path) -> None:
    database = _database()
    store = LocalBlobStore(tmp_path / "blobs")
    try:
        _reset(database)
        local = bootstrap_local_tenant(database)
        create_asset(
            database,
            store,
            local,
            asset_id="asset:private",
            module="voice",
            asset_type="audio",
            mime_type="audio/wav",
            storage_key="voice/private.wav",
            content=b"private",
        )
        with database.transaction() as connection:
            connection.execute(
                "INSERT INTO omnix_users (id, display_name) VALUES ('user:other', 'Other')"
            )
            connection.execute(
                "INSERT INTO omnix_workspaces (id, name, created_by) "
                "VALUES ('workspace:other', 'Other', 'user:other')"
            )
            connection.execute(
                "INSERT INTO omnix_workspace_memberships "
                "(id, workspace_id, user_id, roles) "
                "VALUES ('membership:other', 'workspace:other', 'user:other', ARRAY['owner'])"
            )
        with unit_of_work(database) as work:
            other = work.identities.load_context(
                user_id="user:other", workspace_id="workspace:other"
            )
            assert work.assets.get_asset(other, "asset:private") is None
            work.rollback()
    finally:
        database.close()


def test_settings_are_revisioned_and_secret_values_are_not_stored() -> None:
    database = _database()
    try:
        _reset(database)
        context = bootstrap_local_tenant(database)
        created = put_setting(
            database,
            context,
            scope="provider",
            key="lmstudio",
            value={"base_url": "http://127.0.0.1:1234/v1"},
        )
        updated = put_setting(
            database,
            context,
            scope="provider",
            key="lmstudio",
            value={"base_url": "http://127.0.0.1:1234/v1", "enabled": True},
            expected_revision=created["revision"],
        )
        assert updated["revision"] == 2
        with pytest.raises(RevisionConflict):
            put_setting(
                database,
                context,
                scope="provider",
                key="lmstudio",
                value={},
                expected_revision=1,
            )
        reference = register_secret_reference(
            database,
            context,
            reference="secret:provider:openai",
            provider="os-credential-store",
            purpose="provider-api-key",
            metadata={"configured": True},
        )
        assert reference["reference"] == "secret:provider:openai"
        with database.connection() as connection:
            columns = {
                str(row[0])
                for row in connection.execute(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'omnix_secret_references'"
                ).fetchall()
            }
        assert not {"secret", "value", "token", "credential"}.intersection(columns)
    finally:
        database.close()


def test_legacy_manifest_import_is_idempotent_and_reports_missing(tmp_path: Path) -> None:
    database = _database()
    store = LocalBlobStore(tmp_path / "blobs")
    source = tmp_path / "legacy.wav"
    source.write_bytes(b"legacy-audio")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "assets": {
                    "audio:legacy": {
                        "module": "voice",
                        "type": "audio",
                        "mime_type": "audio/wav",
                        "storage_path": str(source),
                        "metadata": {"legacy": True},
                    },
                    "audio:missing": {
                        "module": "voice",
                        "type": "audio",
                        "mime_type": "audio/wav",
                        "storage_path": str(tmp_path / "missing.wav"),
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    try:
        _reset(database)
        context = bootstrap_local_tenant(database)
        preview = import_legacy_asset_manifest(
            database, store, context, manifest, dry_run=True
        )
        assert preview["imported"] == 1
        assert len(preview["missing"]) == 1

        first = import_legacy_asset_manifest(database, store, context, manifest)
        second = import_legacy_asset_manifest(database, store, context, manifest)
        assert first["ok"] is True
        assert first["imported"] == 1
        assert second["existing"] == 1
        with unit_of_work(database) as work:
            asset = work.assets.get_asset(context, "audio:legacy")
            work.rollback()
        assert asset is not None
        assert asset["compat"]["legacy_storage_path"] == str(source)
    finally:
        database.close()
