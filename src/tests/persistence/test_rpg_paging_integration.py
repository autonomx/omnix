"""RPG lists page with keyset cursors instead of stopping at 500 rows (WP-5.5)."""
from __future__ import annotations

import os
import uuid

import psycopg
import pytest

from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.identity_service import ensure_local_identity
from app.persistence.unit_of_work import unit_of_work
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
def rpg():
    database = PostgresDatabase(DatabaseSettings(url=os.environ["OMNIX_TEST_DATABASE_URL"], pool_min=1, pool_max=4))
    tenant = ensure_local_identity(database)
    install_process_tenant(tenant)
    prefix = f"paging-{uuid.uuid4().hex[:8]}"
    try:
        yield database, tenant, prefix
    finally:
        with psycopg.connect(admin_database_url(), autocommit=True) as admin:
            admin.execute("DELETE FROM omnix_rpg_campaigns WHERE id LIKE %s", (f"{prefix}%",))
            admin.execute("DELETE FROM omnix_rpg_scenarios WHERE world_id LIKE %s", (f"{prefix}%",))
            admin.execute("DELETE FROM omnix_rpg_worlds WHERE id LIKE %s", (f"{prefix}%",))
        database.close()


def test_every_campaign_is_listed_past_one_page(rpg) -> None:
    database, tenant, prefix = rpg
    with unit_of_work(database) as work:
        for index in range(450):
            work.rpg.create_campaign(
                tenant, campaign_id=f"{prefix}-{index:04d}", title=f"campaign {index}",
                state={"manifest": {"session_id": f"{prefix}-{index:04d}"}},
                engine_version="test", schema_version="test", seed="seed",
            )
        work.commit()
    # Equal timestamps for many rows: the keyset must still visit each once.
    with psycopg.connect(admin_database_url(), autocommit=True) as admin:
        admin.execute("UPDATE omnix_rpg_campaigns SET updated_at = '2026-10-04T00:00:00Z' WHERE id LIKE %s", (f"{prefix}%",))

    with unit_of_work(database) as work:
        listed = [row["id"] for row in work.rpg.iter_campaigns(tenant) if row["id"].startswith(prefix)]
        first_page = work.rpg.list_campaigns(tenant, limit=1_000)
        work.rollback()

    assert sorted(listed) == [f"{prefix}-{index:04d}" for index in range(450)]
    assert len(listed) == len(set(listed))
    assert len(first_page) == 200  # a page is at most 200 rows


def test_world_scenarios_are_complete_and_library_counts_come_from_the_database(rpg) -> None:
    from app.apps.rpg.worlds.library_service import read_world_library, read_world_detail

    database, tenant, prefix = rpg
    big_world, small_world = f"{prefix}-big", f"{prefix}-small"
    with unit_of_work(database) as work:
        for world_id in (small_world, big_world):
            work.world_scenarios.create_world(tenant, world_id=world_id, title=world_id)
        for index in range(230):
            work.world_scenarios.create_scenario(tenant, scenario_id=f"{prefix}-s{index:04d}", world_id=big_world, title=f"s{index}")
        work.world_scenarios.create_scenario(tenant, scenario_id=f"{prefix}-only", world_id=small_world, title="only")
        work.commit()
    with psycopg.connect(admin_database_url(), autocommit=True) as admin:
        admin.execute("UPDATE omnix_rpg_scenarios SET status = 'published' WHERE world_id LIKE %s", (f"{prefix}%",))
        # The small world's scenario is the oldest: outside the library's newest scenario page.
        admin.execute("UPDATE omnix_rpg_scenarios SET updated_at = '2020-01-01T00:00:00Z' WHERE id = %s", (f"{prefix}-only",))

    with unit_of_work(database) as work:
        scenarios = list(work.world_library.iter_scenarios(tenant, world_id=big_world))
        work.rollback()
    assert len({row["id"] for row in scenarios}) == 230

    library = read_world_library(database=database, limit=100)
    counts = {world["id"]: world["scenario_count"] for world in library["worlds"]}
    assert counts[big_world] == 230
    assert counts[small_world] == 1

    detail = read_world_detail(big_world, database=database)
    assert len(detail["scenarios"]) == 230
