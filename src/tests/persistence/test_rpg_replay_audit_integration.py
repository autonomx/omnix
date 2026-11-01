"""The replay audit reads committed campaigns, turns and snapshots from PostgreSQL (RQ-0.9)."""
from __future__ import annotations

import copy
import importlib.util
import os
from pathlib import Path
from uuid import uuid4

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "rpg_replay_audit.py"
spec = importlib.util.spec_from_file_location("omnix_rpg_replay_audit_pg", SCRIPT)
assert spec and spec.loader
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def _states(count: int) -> list[dict]:
    states, state = [], {"simulation_state": {"npc_presence": {}, "tick": 0}, "runtime_state": {"log": []}}
    states.append(copy.deepcopy(state))
    for index in range(1, count + 1):
        state = copy.deepcopy(state)
        state["simulation_state"]["tick"] = index
        state["runtime_state"]["log"].append(index)
        states.append(state)
    return states


@pytest.mark.skipif(
    not os.environ.get("OMNIX_TEST_DATABASE_URL"),
    reason="OMNIX_TEST_DATABASE_URL is required for PostgreSQL integration tests",
)
def test_the_audit_reads_committed_turns_from_postgresql() -> None:
    from app.persistence.config import DatabaseSettings
    from app.persistence.database import PostgresDatabase
    from app.persistence.identity_service import ensure_local_identity
    from app.persistence.migrations import apply_migrations
    from app.persistence.unit_of_work import unit_of_work

    url = os.environ["OMNIX_TEST_DATABASE_URL"]
    database = PostgresDatabase(
        DatabaseSettings(url=url, pool_min=1, pool_max=2, connect_timeout_seconds=10,
                         statement_timeout_ms=30_000, application_name="omnix-rpg-replay-audit-test")
    )
    try:
        apply_migrations(database)
        context = ensure_local_identity(database)
        campaign_id = f"campaign:audit-{uuid4().hex}"
        states = _states(3)
        with unit_of_work(database) as work:
            work.rpg.create_campaign(context, campaign_id=campaign_id, title="Audit", state=states[0],
                                     engine_version="test", schema_version="test", seed="1")
            work.commit()
        for revision in range(1, 4):
            with unit_of_work(database) as work:
                work.rpg.commit_turn(
                    context, campaign_id=campaign_id, turn_id=f"turn:{campaign_id}:{revision}",
                    submission_id=f"submit:{revision}", interaction_id=f"interaction:{campaign_id}:{revision}",
                    expected_revision=revision - 1, command={"text": "wait"}, next_state=states[revision],
                    canonical_effects={}, interaction_event={"sequence": revision}, compact_response={"ok": True},
                    engine_version="test", schema_version="test",
                )
                work.commit()
    finally:
        database.close()

    report = audit.run(url, [campaign_id])

    [result] = report["campaigns"]
    assert result["turn_rows"] == 3
    assert result["revisions_without_turn_row"] == 0
    assert result["hash_chain_breaks"] == 0
    assert result["turns_without_patch"] == 0
