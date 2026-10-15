"""A campaign's state is its starting state plus each turn's stored patch (WP-5.6, migration 0158)."""
from __future__ import annotations

import copy
import os
from uuid import uuid4

import pytest

from app.apps.rpg.foundation.persistence.rpg_repository import state_hash
from app.apps.rpg.foundation.persistence.state_delta import apply_state_delta
from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.identity_service import ensure_local_identity
from app.persistence.migrations import apply_migrations
from app.persistence.unit_of_work import unit_of_work

pytestmark = pytest.mark.skipif(
    not os.environ.get("OMNIX_TEST_DATABASE_URL"),
    reason="OMNIX_TEST_DATABASE_URL is required for PostgreSQL integration tests",
)


def _turns(start: dict) -> list[dict]:
    """Successive states: nested edits, added and removed keys, appends, a trimmed window."""
    states, state = [], copy.deepcopy(start)
    for index in range(1, 7):
        state = copy.deepcopy(state)
        state["runtime_state"]["state_revision"] = index
        state["state"]["player"]["hp"] -= 1
        state["state"]["log"].append({"turn": index, "text": f"turn {index}"})
        state["runtime_state"]["recent"] = (state["runtime_state"]["recent"] + [index])[-3:]
        if index == 2:
            state["state"]["npcs"]["npc:bran/innkeeper"] = {"mood": "wary"}
        if index == 4:
            del state["state"]["npcs"]["npc:bran/innkeeper"]
            state["state"]["flags"] = {"met_~bran": True}
        states.append(state)
    return states


def test_starting_state_plus_turn_patches_reproduce_every_committed_state() -> None:
    database = PostgresDatabase(
        DatabaseSettings(
            url=os.environ["OMNIX_TEST_DATABASE_URL"],
            pool_min=1,
            pool_max=2,
            connect_timeout_seconds=10,
            statement_timeout_ms=30_000,
            application_name="omnix-rpg-turn-delta",
        )
    )
    try:
        apply_migrations(database)
        context = ensure_local_identity(database)
        campaign_id = f"campaign:delta-{uuid4().hex}"
        start = {
            "manifest": {"session_id": campaign_id, "title": "Delta"},
            "state": {"player": {"hp": 20}, "log": [], "npcs": {}},
            "runtime_state": {"state_revision": 0, "recent": []},
        }
        with unit_of_work(database) as work:
            work.rpg.create_campaign(
                context, campaign_id=campaign_id, title="Delta", state=start,
                engine_version="test", schema_version="test", seed="1",
            )
            work.commit()
        for revision, next_state in enumerate(_turns(start), start=1):
            with unit_of_work(database) as work:
                work.rpg.commit_turn(
                    context, campaign_id=campaign_id, turn_id=f"turn:{campaign_id}:{revision}",
                    submission_id=f"submit:{revision}", interaction_id=f"interaction:{campaign_id}:{revision}",
                    expected_revision=revision - 1, command={"text": f"turn {revision}"},
                    next_state=next_state, canonical_effects={}, interaction_event={"sequence": revision},
                    compact_response={"ok": True}, engine_version="test", schema_version="test",
                )
                work.commit()

        with database.transaction() as connection:
            rows = connection.execute(
                "SELECT resulting_revision, state_delta_jsonb, state_hash_after FROM omnix_rpg_turns "
                "WHERE workspace_id = %s AND campaign_id = %s ORDER BY sequence",
                (context.workspace_id, campaign_id),
            ).fetchall()
        with unit_of_work(database) as work:
            stored = work.rpg.get_campaign(context, campaign_id)
            work.rollback()

        assert [int(row[0]) for row in rows] == list(range(1, 7))
        replayed = start
        for _revision, delta, hash_after in rows:
            replayed = apply_state_delta(replayed, list(delta))
            assert state_hash(replayed) == hash_after
        assert replayed == stored["state"]
        # A patch carries the change, not the state: a later turn's patch is small.
        assert len(rows[-1][1]) <= 4
    finally:
        database.close()
