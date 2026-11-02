"""Creating characters on PostgreSQL: a duplicate is a conflict, not a server error."""
from __future__ import annotations

import os

import pytest

from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresConstraintError, PostgresDatabase
from app.persistence.identity_service import ensure_local_identity
from app.persistence.migrations import apply_migrations
from app.platform.characters.models import CreateCharacterRequest
from app.platform.characters.persistence.character_store import PostgresCharacterRepositoryAdapter
from app.platform.characters.repository import CharacterConflictError
from app.platform.characters.service import CharacterService
from app.runtime.tenant_context import LOCAL_WORKSPACE_ID, pop_tenant, push_tenant, tenant_context

pytestmark = pytest.mark.skipif(
    not os.environ.get("OMNIX_TEST_DATABASE_URL"),
    reason="OMNIX_TEST_DATABASE_URL is required for PostgreSQL integration tests",
)

NEW_CHARACTER = CreateCharacterRequest(display_name="New Character", personality_prompt="Be clear.")


@pytest.fixture
def repository():
    database = PostgresDatabase(DatabaseSettings(
        url=os.environ["OMNIX_TEST_DATABASE_URL"], pool_min=1, pool_max=4, connect_timeout_seconds=10,
        statement_timeout_ms=30_000, application_name="omnix-character-store-tests",
    ))
    apply_migrations(database)
    with database.transaction() as connection:
        connection.execute("TRUNCATE omnix_character_versions, omnix_characters CASCADE")
        connection.execute(
            "UPDATE omnix_persistence_cutover SET mode = 'postgresql', authority_state = 'postgresql_stabilized' "
            "WHERE singleton = TRUE"
        )
    token = push_tenant(ensure_local_identity(database))
    try:
        yield PostgresCharacterRepositoryAdapter(database)
    finally:
        pop_tenant(token)
        database.close()


def test_a_duplicate_id_is_a_conflict(repository) -> None:
    # Seen on the live gateway: the store looked for psycopg's exception, the database layer had already wrapped it,
    # and a duplicate became a 500.
    assert repository.create(NEW_CHARACTER).id == "new-character"
    with pytest.raises(CharacterConflictError, match="already exists: new-character"):
        repository.create(NEW_CHARACTER)
    assert [character.id for character in repository.list()] == ["new-character"]


def test_a_constraint_that_is_not_a_duplicate_stays_a_server_error(repository) -> None:
    other_workspace = tenant_context(user_id="user:someone", workspace_id="workspace:does-not-exist",
                                     membership_id="membership:none", roles=["owner"])
    assert other_workspace.workspace_id != LOCAL_WORKSPACE_ID
    token = push_tenant(other_workspace)
    try:
        with pytest.raises(PostgresConstraintError):
            repository.create(NEW_CHARACTER)
    finally:
        pop_tenant(token)


def test_the_new_character_button_works_again_and_again(repository) -> None:
    service = CharacterService(repository=repository)
    first, second, third = (service.create(NEW_CHARACTER) for _ in range(3))
    assert first.id == "new-character"
    assert second.id.startswith("new-character-") and third.id.startswith("new-character-") and second.id != third.id
    assert {character.display_name for character in service.list().characters} == {"New Character"}
    assert len(service.list().characters) == 3


def test_an_id_the_caller_chose_still_conflicts(repository) -> None:
    service = CharacterService(repository=repository)
    chosen = NEW_CHARACTER.model_copy(update={"id": "maya"})
    service.create(chosen)
    with pytest.raises(CharacterConflictError):
        service.create(chosen)
