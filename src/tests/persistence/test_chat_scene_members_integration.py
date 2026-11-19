"""A character chat's call guests in PostgreSQL: two seats, first free seat, and they leave with their chat or
character (companion 5.1)."""
from __future__ import annotations

import os
import threading
import uuid

import psycopg
import pytest

from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.identity_service import ensure_local_identity
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
def seats():
    from app.platform.chat.persistence.scene_repository import PostgresSceneMemberRepository

    database = PostgresDatabase(DatabaseSettings(url=os.environ["OMNIX_TEST_DATABASE_URL"], pool_min=1, pool_max=4))
    tenant = ensure_local_identity(database)
    install_process_tenant(tenant)
    tag = uuid.uuid4().hex[:10]
    session_id = f"chat:scene:{tag}"
    characters = {name: f"scene-{name}-{tag}" for name in ("host", "bea", "theo", "zed")}
    with psycopg.connect(admin_database_url(), autocommit=True) as admin:
        for character_id in characters.values():
            admin.execute("INSERT INTO omnix_characters (id, workspace_id, profile) VALUES (%s, %s, '{}'::jsonb)",
                          (character_id, tenant.workspace_id))
        admin.execute("INSERT INTO omnix_chat_sessions (id, workspace_id, title, profile_id) "
                      "VALUES (%s, %s, 'scene test', 'default')", (session_id, tenant.workspace_id))
    try:
        yield PostgresSceneMemberRepository(database), session_id, characters
    finally:
        with psycopg.connect(admin_database_url(), autocommit=True) as admin:
            admin.execute("DELETE FROM omnix_chat_sessions WHERE id = %s", (session_id,))
            admin.execute("DELETE FROM omnix_characters WHERE id = ANY(%s)", (list(characters.values()),))
        database.close()


def _guests(repository, session_id) -> list[tuple[str, int]]:
    return [(seat.character_id, seat.seat) for seat in repository.guests(session_id)]


def test_a_call_seats_two_guests_in_the_first_free_seat(seats) -> None:
    from app.platform.chat.persistence.scene_repository import SceneFullError

    repository, session_id, ids = seats

    assert repository.add_guest(session_id, ids["bea"]).seat == 1
    assert repository.add_guest(session_id, ids["bea"]).seat == 1  # already seated: same seat, no new row
    assert repository.add_guest(session_id, ids["theo"]).seat == 2
    with pytest.raises(SceneFullError):
        repository.add_guest(session_id, ids["zed"])
    assert repository.remove_guest(session_id, ids["bea"]) is True
    assert repository.remove_guest(session_id, ids["bea"]) is False
    assert repository.add_guest(session_id, ids["zed"]).seat == 1
    assert _guests(repository, session_id) == [(ids["zed"], 1), (ids["theo"], 2)]
    with pytest.raises(LookupError):
        repository.add_guest("chat:scene:missing", ids["bea"])


def test_two_adds_racing_for_the_last_seat_seat_one(seats) -> None:
    from app.platform.chat.persistence.scene_repository import SceneFullError

    repository, session_id, ids = seats
    repository.add_guest(session_id, ids["bea"])
    barrier = threading.Barrier(2)
    outcomes: list[object] = []

    def add(character_id: str) -> None:
        barrier.wait()
        try:
            outcomes.append(repository.add_guest(session_id, character_id).seat)
        except SceneFullError as error:
            outcomes.append(error)

    threads = [threading.Thread(target=add, args=(ids[name],)) for name in ("theo", "zed")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert sorted(outcome for outcome in outcomes if isinstance(outcome, int)) == [2]
    assert sum(isinstance(outcome, SceneFullError) for outcome in outcomes) == 1
    assert len(_guests(repository, session_id)) == 2


def test_a_guest_leaves_with_its_character_and_the_scene_with_its_chat(seats) -> None:
    repository, session_id, ids = seats
    repository.add_guest(session_id, ids["bea"])
    repository.add_guest(session_id, ids["theo"])

    with psycopg.connect(admin_database_url(), autocommit=True) as admin:
        admin.execute("DELETE FROM omnix_characters WHERE id = %s", (ids["theo"],))
    assert _guests(repository, session_id) == [(ids["bea"], 1)]

    with psycopg.connect(admin_database_url(), autocommit=True) as admin:
        admin.execute("DELETE FROM omnix_chat_sessions WHERE id = %s", (session_id,))
        left = admin.execute("SELECT count(*) FROM omnix_chat_scene_members WHERE session_id = %s",
                             (session_id,)).fetchone()
    assert left[0] == 0
    assert repository.clear(session_id) == 0


def test_the_guest_check_does_not_see_another_workspaces_character(seats) -> None:
    from app.platform.characters.persistence.character_store import PostgresCharacterRepositoryAdapter

    repository, session_id, ids = seats
    other, stranger = f"ws-scene-{uuid.uuid4().hex[:10]}", f"scene-stranger-{uuid.uuid4().hex[:10]}"
    with psycopg.connect(admin_database_url(), autocommit=True) as admin:
        (owner,) = admin.execute(
            "SELECT w.created_by FROM omnix_workspaces w JOIN omnix_chat_sessions s ON s.workspace_id = w.id "
            "WHERE s.id = %s", (session_id,)).fetchone()
        admin.execute("INSERT INTO omnix_workspaces (id, name, created_by) VALUES (%s, %s, %s)", (other, other, owner))
        profile = '{"display_name": "Bea", "personality_prompt": "Warm."}'
        admin.execute("INSERT INTO omnix_characters (id, workspace_id, profile) VALUES (%s, %s, %s::jsonb)",
                      (stranger, other, profile))
        admin.execute("UPDATE omnix_characters SET profile = %s::jsonb WHERE id = %s", (profile, ids["bea"]))
    try:
        # scene.add_guest seats only what the workspace-scoped character store returns; the seat's foreign key
        # would take any id, since a foreign key check ignores row-level security.
        characters = PostgresCharacterRepositoryAdapter(repository.database)
        assert characters.get(ids["bea"]) is not None and characters.get(stranger) is None
        assert repository.add_guest(session_id, stranger).seat == 1
    finally:
        with psycopg.connect(admin_database_url(), autocommit=True) as admin:
            admin.execute("DELETE FROM omnix_workspaces WHERE id = %s", (other,))
