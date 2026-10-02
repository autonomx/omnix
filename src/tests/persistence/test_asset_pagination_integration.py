"""Asset cursor pagination (WP-5.5 acceptance)."""
from __future__ import annotations

import os
import uuid

import psycopg
import pytest

from app.assets.paging import iter_assets
from app.persistence.shared_asset_store import PostgresSharedAssetStoreAdapter
from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.identity_service import ensure_local_identity
from app.runtime.pagination import InvalidCursor
from app.runtime.tenant_context import install_process_tenant
from tests.support.database import admin_database_url

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        not os.environ.get("OMNIX_TEST_DATABASE_URL"),
        reason="OMNIX_TEST_DATABASE_URL is required for PostgreSQL integration tests",
    ),
]


@pytest.fixture
def store():
    database = PostgresDatabase(DatabaseSettings(url=os.environ["OMNIX_TEST_DATABASE_URL"], pool_min=1, pool_max=4))
    tenant = ensure_local_identity(database)
    install_process_tenant(tenant)
    module = f"paging-test-{uuid.uuid4().hex[:10]}"
    try:
        yield PostgresSharedAssetStoreAdapter(database=database), tenant, module
    finally:
        with psycopg.connect(admin_database_url(), autocommit=True) as admin:
            admin.execute("DELETE FROM omnix_assets WHERE module = %s", (module,))
        database.close()


def _insert(tenant, module: str, rows: list[tuple[str, str, int]]) -> None:
    """``(id, asset_type, seconds_ago)``; equal ages exercise the id tie-break."""
    with psycopg.connect(admin_database_url(), autocommit=True) as admin:
        with admin.cursor() as cursor:
            cursor.executemany(
                """INSERT INTO omnix_assets (id, workspace_id, module, asset_type, mime_type, byte_size,
                                             checksum_sha256, storage_provider, storage_key, created_at)
                   VALUES (%s, %s, %s, %s, 'application/octet-stream', 1, repeat('a', 64), 'local', %s,
                           TIMESTAMPTZ '2026-10-01T00:00:00Z' - (%s * INTERVAL '1 second'))""",
                [(asset_id, tenant.workspace_id, module, kind, asset_id, age) for asset_id, kind, age in rows],
            )


def test_paging_over_mixed_assets_returns_every_image_once_under_concurrent_inserts(store) -> None:
    adapter, tenant, module = store
    rows = [
        (f"{module}:{index:04d}", "image" if index % 3 == 0 else "audio", index // 4)
        for index in range(1200)
    ]
    _insert(tenant, module, rows)
    expected = {asset_id for asset_id, kind, _ in rows if kind == "image"}

    seen: list[str] = []
    cursor = None
    pages = 0
    while True:
        page = adapter.list_assets(asset_type="image", modules=(module,), limit=37, cursor=cursor)
        seen.extend(asset.id for asset in page.assets)
        pages += 1
        # Newer images arrive while the client pages; they sort before the
        # cursor, so they never shift or repeat the remaining pages.
        _insert(tenant, module, [(f"{module}:new-{pages:03d}", "image", -60 - pages)])
        if not page.has_more:
            assert page.next_cursor is None
            break
        cursor = page.next_cursor

    assert len(seen) == len(set(seen))
    assert set(seen) == expected
    assert all(asset.type.value == "image" for asset in adapter.list_assets(asset_type="image", modules=(module,)).assets)


def test_iter_assets_walks_every_page(store) -> None:
    adapter, tenant, module = store
    _insert(tenant, module, [(f"{module}:{index:04d}", "audio", index) for index in range(450)])

    ids = [asset.id for asset in iter_assets(adapter, modules=(module,))]

    assert len(ids) == 450 == len(set(ids))
    assert ids[0] == f"{module}:0000"  # newest first


def test_a_tampered_cursor_is_rejected(store) -> None:
    adapter, _tenant, _module = store
    with pytest.raises(InvalidCursor):
        adapter.list_assets(cursor="not-a-cursor")


def test_updating_an_asset_keeps_its_provenance(store) -> None:
    """One-statement descriptor update that preserves the source job (WP-8.1)."""
    from app.assets.models import AssetRecord

    adapter, tenant, module = store
    asset_id = f"{module}:provenance"
    _insert(tenant, module, [(asset_id, "image", 0)])

    first = adapter.upsert_asset(AssetRecord(
        id=asset_id, module=module, type="image", mime_type="image/png",
        metadata={"title": "first"}, source_job_id="job:render-1", created_at="2026-10-01T00:00:00Z",
    ))
    second = adapter.upsert_asset(AssetRecord(
        id=asset_id, module=module, type="image", mime_type="image/png",
        metadata={"title": "second"}, created_at="2026-10-01T00:00:00Z",
    ))

    assert first.source_job_id == "job:render-1"
    assert second.metadata == {"title": "second"}
    assert second.source_job_id == "job:render-1"  # not erased by an update without one
