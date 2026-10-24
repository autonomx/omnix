"""A turn's narration is kept beside the campaign document, not in it (RQ-1.4, roadmap §4.1)."""
from __future__ import annotations

import os
from uuid import uuid4

import pytest

from app.persistence.unit_of_work import unit_of_work
from app.runtime.tenant_context import current_tenant

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        not os.environ.get("OMNIX_TEST_DATABASE_URL"),
        reason="OMNIX_TEST_DATABASE_URL is required for PostgreSQL integration tests",
    ),
]


def _narrated(state: dict, *turn_ids: str) -> dict:
    artifacts = [{"turn_id": turn_id, "narration": f"Narrated {turn_id}."} for turn_id in turn_ids]
    return {**state, "runtime_state": {**state.get("runtime_state", {}), "narration_artifacts": artifacts,
                                       "narration_artifacts_by_turn": {a["turn_id"]: a for a in artifacts}}}


def test_turn_narrations_leave_the_document_and_come_back_on_load() -> None:
    from app.persistence.startup import bootstrap_postgresql_runtime
    from app.apps.rpg.session.persistence.session_records import load_session_from_postgres, save_session_to_postgres

    bootstrap_postgresql_runtime()
    context = current_tenant()
    campaign_id = f"campaign:narrations-{uuid4().hex}"
    state = {"manifest": {"session_id": campaign_id, "id": campaign_id, "schema_version": 6},
             "runtime_state": {"state_revision": 0}, "simulation_state": {"tick": 0}}
    with unit_of_work() as work:
        work.rpg.create_campaign(context, campaign_id=campaign_id, title="Narrations", state=state,
                                 engine_version="test", schema_version="test", seed="1")
        committed = work.rpg.commit_turn(
            context, campaign_id=campaign_id, turn_id=f"turn:{campaign_id}:1", submission_id="submit:1",
            interaction_id=f"interaction:{campaign_id}:1", expected_revision=0, command={"text": "look"},
            next_state=_narrated({**state, "runtime_state": {"state_revision": 1}}, "turn:1"),
            canonical_effects={}, interaction_event={"sequence": 1}, compact_response={"ok": True},
            engine_version="test", schema_version="test",
        )
        work.commit()
    assert "narration_artifacts" not in committed["campaign"]["state"]["runtime_state"]

    loaded = load_session_from_postgres(campaign_id)
    assert loaded["runtime_state"]["narration_artifacts_by_turn"]["turn:1"]["narration"] == "Narrated turn:1."

    # A narration that finishes later is saved beside the document: the campaign stays at its revision.
    loaded = _narrated(loaded, "turn:1", "turn:2")
    save_session_to_postgres(loaded)
    with unit_of_work() as work:
        campaign = work.rpg.get_campaign(context, campaign_id)
        kept = work.rpg.turn_narrations(context, campaign_id)
        work.rollback()
    assert campaign["revision"] == 1 and "narration_artifacts" not in campaign["state"]["runtime_state"]
    assert [turn_id for turn_id, _ in kept] == ["turn:1", "turn:2"]


def test_only_the_newest_turn_narrations_are_kept() -> None:
    from app.persistence.startup import bootstrap_postgresql_runtime

    bootstrap_postgresql_runtime()
    context = current_tenant()
    campaign_id = f"campaign:narrations-{uuid4().hex}"
    with unit_of_work() as work:
        work.rpg.create_campaign(context, campaign_id=campaign_id, title="Narrations", state={"tick": 0},
                                 engine_version="test", schema_version="test", seed="1")
        kept = work.rpg.TURN_NARRATIONS_KEPT
        for batch in range(3):
            work.rpg.put_turn_narrations(context, campaign_id=campaign_id, narrations={
                f"turn:{batch}:{index:03d}": {"narration": "x"} for index in range(kept)})
        rows = work.rpg.turn_narrations(context, campaign_id)
        work.commit()
    assert len(rows) == kept and {turn_id.split(":")[1] for turn_id, _ in rows} == {"2"}


def test_a_turn_waits_for_the_campaigns_turn_in_progress_and_gives_up_after_the_limit(monkeypatch) -> None:
    import threading

    from app.persistence.startup import bootstrap_postgresql_runtime
    from app.apps.rpg.session.persistence import turn_order

    bootstrap_postgresql_runtime()
    campaign_id = f"campaign:order-{uuid4().hex}"
    monkeypatch.setenv(turn_order.TURN_WAIT_ENV, "1")
    order: list[str] = []
    holding, release = threading.Event(), threading.Event()

    def first_turn() -> None:
        with turn_order.campaign_turn(campaign_id):
            order.append("first")
            holding.set()
            release.wait(10)

    runner = threading.Thread(target=first_turn)
    runner.start()
    assert holding.wait(10)
    with pytest.raises(turn_order.TurnInProgress):  # the first turn holds it past the second's wait
        with turn_order.campaign_turn(campaign_id):
            order.append("second, too early")
    release.set()
    runner.join(10)
    with turn_order.campaign_turn(campaign_id):  # once it finishes, the next turn runs
        order.append("second")
    with turn_order.campaign_turn(f"{campaign_id}:other"):  # another campaign never waits on it
        pass
    assert order == ["first", "second"]
