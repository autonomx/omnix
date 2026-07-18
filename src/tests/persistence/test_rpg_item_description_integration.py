from __future__ import annotations

import os

import pytest

from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.identity_service import bootstrap_local_tenant
from app.persistence.migrations import apply_migrations
from app.persistence.rpg_item_description_repository import (
    PostgresRpgItemDescriptionRepository,
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
            pool_max=3,
            connect_timeout_seconds=10,
            statement_timeout_ms=30_000,
            application_name="omnix-rpg-item-description-tests",
        )
    )


def _reset(database: PostgresDatabase) -> None:
    apply_migrations(database)
    with database.transaction() as connection:
        connection.execute(
            "TRUNCATE omnix_rpg_item_descriptions, omnix_audit_events, "
            "omnix_workspace_memberships, omnix_workspaces, omnix_users CASCADE"
        )


def test_item_descriptions_are_upserted_and_reused_by_context_key() -> None:
    database = _database()
    try:
        _reset(database)
        context = bootstrap_local_tenant(database)
        key = "a" * 64
        context_hash = "b" * 64

        with database.transaction() as connection:
            repository = PostgresRpgItemDescriptionRepository(connection)
            first = repository.put(
                context,
                description_key=key,
                item_key="trail_rations",
                item_name="Trail Rations",
                genre="classic_fantasy",
                context_hash=context_hash,
                summary="Hard-baked travel cakes prepared for long roads.",
                metadata={"prompt_version": "rpg_item_detail_v1"},
            )

        assert first["summary"] == "Hard-baked travel cakes prepared for long roads."
        assert first["metadata"]["prompt_version"] == "rpg_item_detail_v1"

        with database.transaction() as connection:
            repository = PostgresRpgItemDescriptionRepository(connection)
            cached = repository.get(context, key)
            updated = repository.put(
                context,
                description_key=key,
                item_key="trail_rations",
                item_name="Trail Rations",
                genre="classic_fantasy",
                context_hash=context_hash,
                summary="The persisted description is reused and may be refreshed explicitly.",
                metadata={"prompt_version": "rpg_item_detail_v1"},
            )

        assert cached is not None
        assert cached["summary"] == "Hard-baked travel cakes prepared for long roads."
        assert updated["summary"] == "The persisted description is reused and may be refreshed explicitly."
        assert updated["description_key"] == key
    finally:
        database.close()
