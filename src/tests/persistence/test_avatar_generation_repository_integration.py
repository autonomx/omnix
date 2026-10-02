from __future__ import annotations

import os
import uuid

import pytest

from app.characters.avatar_generation_models import CreateCharacterAvatarGenerationRequest
from app.characters.persistence.avatar_generation_repository import (
    PostgresCharacterAvatarGenerationRepositoryAdapter,
    PostgresCharacterVisemeGenerationRepositoryAdapter,
)
from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.identity_service import ensure_local_identity
from app.persistence.migrations import apply_migrations
from app.runtime.tenant_context import pop_tenant, push_tenant


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
            application_name="omnix-avatar-generation-repository-tests",
        )
    )


def test_avatar_generation_batches_are_shared_through_postgresql() -> None:
    database = _database()
    record_ids: list[tuple[str, str]] = []
    tenant_token = None
    try:
        apply_migrations(database)
        tenant_token = push_tenant(ensure_local_identity(database))
        identity = uuid.uuid4().hex
        character_id = f"avatar-generation-test:{identity}"

        generations = PostgresCharacterAvatarGenerationRepositoryAdapter(database)
        batch = generations.create(
            character_id,
            CreateCharacterAvatarGenerationRequest(appearance_prompt="Silver-haired explorer"),
            f"job:avatar-base:{identity}",
        )
        record_ids.append(("generation-batch", batch.id))
        updated = generations.update(
            batch.id,
            status="generating_variants",
            variant_job_ids={"mouth_small": f"job:avatar-mouth:{identity}"},
            asset_ids={"base": f"asset:avatar-base:{identity}"},
        )

        fresh_generations = PostgresCharacterAvatarGenerationRepositoryAdapter(database)
        assert fresh_generations.get(batch.id) == updated
        assert [item.id for item in fresh_generations.list(character_id)] == [batch.id]

        visemes = PostgresCharacterVisemeGenerationRepositoryAdapter(database)
        viseme_batch = visemes.create(
            character_id,
            {"A": f"job:viseme-a:{identity}"},
        )
        record_ids.append(("viseme-generation-batch", viseme_batch.id))
        completed = visemes.update(
            viseme_batch.id,
            status="completed",
            asset_ids={"A": f"asset:viseme-a:{identity}"},
            attempts={"A": 1},
        )

        fresh_visemes = PostgresCharacterVisemeGenerationRepositoryAdapter(database)
        assert fresh_visemes.get(viseme_batch.id) == completed
        assert [item.id for item in fresh_visemes.list(character_id)] == [viseme_batch.id]
    finally:
        if record_ids:
            with database.transaction() as connection:
                for record_type, record_id in record_ids:
                    connection.execute(
                        """
                        DELETE FROM omnix_module_records
                         WHERE module = 'character-avatar'
                           AND record_type = %s AND record_id = %s
                        """,
                        (record_type, record_id),
                    )
        if tenant_token is not None:
            pop_tenant(tenant_token)
        database.close()
