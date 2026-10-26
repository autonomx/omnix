"""A campaign document stored in parts: a turn writes the parts it changed (roadmap §7 Q-13, migration 0186)."""
from __future__ import annotations

import copy
import hashlib
import os
from uuid import uuid4

import pytest

from app.apps.rpg.foundation.persistence.document_parts import canonical_json, state_hash
from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.identity_service import ensure_local_identity
from app.persistence.migrations import apply_migrations
from app.persistence.unit_of_work import unit_of_work

pytestmark = pytest.mark.skipif(
    not os.environ.get("OMNIX_TEST_DATABASE_URL"),
    reason="OMNIX_TEST_DATABASE_URL is required for PostgreSQL integration tests",
)

_ARCHIVE = [f"Day {day}: the road ran on past quiet farms and shuttered mills." for day in range(300)]


@pytest.fixture()
def database():
    database = PostgresDatabase(DatabaseSettings(
        url=os.environ["OMNIX_TEST_DATABASE_URL"], pool_min=1, pool_max=2, connect_timeout_seconds=10,
        statement_timeout_ms=30_000, application_name="omnix-rpg-campaign-parts"))
    try:
        apply_migrations(database)
        yield database
    finally:
        database.close()


def _start(campaign_id: str) -> dict:
    return {
        "manifest": {"session_id": campaign_id, "title": "Parts", "turn_count": 0},
        "state": {"player": {"level": 1}, "location": "loc:square", "player_journal_archive": list(_ARCHIVE)},
        "runtime_state": {"state_revision": 0, "interaction_timeline": []},
        "simulation_state": {"rng_seed": 11},
    }


def _commit(database, context, campaign_id: str, revision: int, next_state: dict) -> dict:
    with unit_of_work(database) as work:
        committed = work.rpg.commit_turn(
            context, campaign_id=campaign_id, turn_id=f"turn:{campaign_id}:{revision}",
            submission_id=f"submit:{revision}", interaction_id=f"interaction:{campaign_id}:{revision}",
            expected_revision=revision - 1, command={"text": f"turn {revision}"}, next_state=next_state,
            canonical_effects={}, interaction_event={"sequence": revision}, compact_response={"ok": True},
            engine_version="test", schema_version="test")
        work.commit()
    return committed


def _parts(database, campaign_id: str) -> dict[str, tuple[str, int]]:
    with database.transaction() as connection:
        connection.execute("SELECT set_config('omnix.system', 'on', true)")
        rows = connection.execute(
            "SELECT path, part_hash, xmin::text::bigint FROM omnix_rpg_campaign_parts WHERE campaign_id = %s",
            (campaign_id,)).fetchall()
    return {str(row[0]): (str(row[1]), int(row[2])) for row in rows}


def test_a_turn_writes_only_the_parts_it_changed_and_history_replays(database) -> None:
    context = ensure_local_identity(database)
    campaign_id = f"campaign:parts-{uuid4().hex}"
    start = _start(campaign_id)
    with unit_of_work(database) as work:
        created = work.rpg.create_campaign(context, campaign_id=campaign_id, title="Parts", state=start,
                                           engine_version="test", schema_version="test", seed="1")
        work.rpg.keep_snapshot(context, campaign_id=campaign_id, revision=0, state=start, engine_version="test",
                               schema_version="test")
        work.commit()
    assert created["state_hash"] == state_hash(start)
    first = _parts(database, campaign_id)
    assert set(first) == {"/state/player_journal_archive"}

    state = copy.deepcopy(start)
    for revision in range(1, 5):
        state = copy.deepcopy(state)
        state["runtime_state"]["state_revision"] = revision
        state["manifest"]["turn_count"] = revision
        state["runtime_state"]["interaction_timeline"].append({"turn": revision, "text": "x" * 2000})
        committed = _commit(database, context, campaign_id, revision, state)
        assert committed["campaign"]["state"] == state and committed["turn"]["state_hash_after"] == state_hash(state)

    parts = _parts(database, campaign_id)
    assert set(parts) == {"/state/player_journal_archive", "/runtime_state/interaction_timeline"}
    assert parts["/state/player_journal_archive"] == first["/state/player_journal_archive"]  # never rewritten
    with unit_of_work(database) as work:
        loaded = work.rpg.get_campaign(context, campaign_id)
        replayed = work.rpg.document_at_revision(context, campaign_id, 4)
        listed = work.connection.execute(
            "SELECT turn_count, player_level, location_name FROM omnix_rpg_campaigns WHERE id = %s",
            (campaign_id,)).fetchone()
        work.rollback()
    assert loaded is not None and loaded["state"] == state and loaded["state_hash"] == state_hash(state)
    assert replayed == state
    assert tuple(listed) == (4, 1, "loc:square")  # the summary trigger reads the head

    smaller = copy.deepcopy(state)
    smaller["runtime_state"]["state_revision"] = 5
    smaller["state"]["player_journal_archive"] = ["Day 1."]
    _commit(database, context, campaign_id, 5, smaller)
    assert set(_parts(database, campaign_id)) == {"/runtime_state/interaction_timeline"}
    with unit_of_work(database) as work:
        assert work.rpg.get_campaign(context, campaign_id)["state"] == smaller
        work.rollback()


def test_a_campaign_stored_whole_before_parts_loads_and_its_next_turn_splits_it(database) -> None:
    context = ensure_local_identity(database)
    campaign_id = f"campaign:whole-{uuid4().hex}"
    start = _start(campaign_id)
    encoded = canonical_json(start)
    legacy = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    with unit_of_work(database) as work:
        work.connection.execute(
            "INSERT INTO omnix_rpg_campaigns (id, workspace_id, owner_user_id, title, revision, state_jsonb, state_hash, "
            "engine_version, schema_version, seed) VALUES (%s, %s, %s, 'Whole', 0, %s::jsonb, %s, 'test', 'test', '1')",
            (campaign_id, context.workspace_id, context.user_id, encoded, legacy))
        work.rpg.create_snapshot(context, campaign_id=campaign_id, snapshot_id=f"snapshot:{campaign_id}:0",
                                 revision=0, state=start, state_hash_value=legacy, engine_version="test",
                                 schema_version="test")
        loaded = work.rpg.get_campaign(context, campaign_id)
        work.commit()
    assert loaded is not None and loaded["state"] == start and loaded["part_hashes"] == {}

    after = copy.deepcopy(start)
    after["runtime_state"]["state_revision"] = 1
    committed = _commit(database, context, campaign_id, 1, after)
    assert committed["turn"]["state_hash_before"] == legacy
    assert set(_parts(database, campaign_id)) == {"/state/player_journal_archive"}
    with unit_of_work(database) as work:
        assert work.rpg.document_at_revision(context, campaign_id, 1) == after  # across both hash schemes
        work.rollback()


def test_a_kept_document_is_read_only_while_the_row_still_has_its_revision_and_hash(database) -> None:
    """F2: a turn reads its campaign at its load and under its commit's lock; the kept document stands in for the
    stored one only while the row's revision and hash are the kept ones, and a reader gets a copy."""
    from app.apps.rpg.foundation.persistence import rpg_repository

    context = ensure_local_identity(database)
    campaign_id = f"campaign:kept-{uuid4().hex}"
    start = _start(campaign_id)
    with unit_of_work(database) as work:
        work.rpg.create_campaign(context, campaign_id=campaign_id, title="Kept", state=start, engine_version="test",
                                 schema_version="test", seed="1")
        work.commit()
    after = copy.deepcopy(start)
    after["runtime_state"]["state_revision"] = 1
    after["runtime_state"]["interaction_timeline"].append({"turn": 1, "text": "y" * 5000})
    rpg_repository.clear_kept_documents()
    with unit_of_work(database) as work:
        work.rpg.get_campaign(context, campaign_id)  # a miss: read whole, and kept
        work.rollback()
    _commit(database, context, campaign_id, 1, after)  # the commit keeps what it wrote
    kept = rpg_repository._kept((context.workspace_id, campaign_id))
    assert kept is not None and kept.revision == 1 and kept.document == after

    with unit_of_work(database) as work:
        read = work.rpg.get_campaign(context, campaign_id)
        assert read["state"] == after and read["state"] is not kept.document  # a copy
        read["state"]["state"]["player"]["level"] = 99  # changing it changes nothing kept
        assert work.rpg.get_campaign(context, campaign_id)["state"] == after
        # Out of band, the stored document and its hash change at the same revision: the kept one is not used.
        changed = copy.deepcopy(after)
        changed["state"]["player"]["level"] = 7
        work.connection.execute("UPDATE omnix_rpg_campaigns SET state_jsonb = %s::jsonb, state_hash = %s WHERE id = %s",
                                (canonical_json(changed), state_hash(changed), campaign_id))
        assert work.rpg.get_campaign(context, campaign_id)["state"]["state"]["player"]["level"] == 7
        work.rollback()
