"""A player who used the hour's turns is refused the next one, counted in PostgreSQL (RQ-8.2)."""
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


def _commit_turns(campaign_id: str, count: int) -> None:
    context = current_tenant()
    with unit_of_work() as work:
        work.rpg.create_campaign(context, campaign_id=campaign_id, title="Budget", state={"tick": 0},
                                 engine_version="test", schema_version="test", seed="1")
        work.commit()
    for revision in range(1, count + 1):
        with unit_of_work() as work:
            work.rpg.commit_turn(
                context, campaign_id=campaign_id, turn_id=f"turn:{campaign_id}:{revision}",
                submission_id=f"submit:{revision}", interaction_id=f"interaction:{campaign_id}:{revision}",
                expected_revision=revision - 1, command={"text": "wait"}, next_state={"tick": revision},
                canonical_effects={}, interaction_event={"sequence": revision}, compact_response={"ok": True},
                engine_version="test", schema_version="test",
            )
            work.commit()


def test_turns_beyond_the_hourly_ceiling_are_refused_until_the_window_moves(monkeypatch) -> None:
    from app.persistence.startup import bootstrap_postgresql_runtime
    from app.apps.rpg.session import turn_budget

    bootstrap_postgresql_runtime()
    context = current_tenant()
    with unit_of_work() as work:
        before, _oldest = work.rpg.recent_turns_by_owner(context, window_seconds=turn_budget.WINDOW_SECONDS)
        work.rollback()
    campaign_id = f"campaign:budget-{uuid4().hex}"
    _commit_turns(campaign_id, 3)

    # A player other than the install's owner (a guest, an invited player): the ceiling holds.
    monkeypatch.setattr(turn_budget, "is_install_owner", lambda _context: False)
    monkeypatch.setenv(turn_budget.TURNS_PER_HOUR_ENV, str(before + 4))
    turn_budget.require_turn_budget()  # three played, one left

    monkeypatch.setenv(turn_budget.TURNS_PER_HOUR_ENV, str(before + 3))
    with pytest.raises(turn_budget.TurnBudgetExceeded) as refused:
        turn_budget.require_turn_budget()
    assert refused.value.used == before + 3
    assert 1 <= refused.value.retry_after_seconds <= turn_budget.WINDOW_SECONDS + 1

    # The install's owner is never limited (owner decision 2026-10-31).
    monkeypatch.undo()
    monkeypatch.setenv(turn_budget.TURNS_PER_HOUR_ENV, str(before + 3))
    assert turn_budget.is_install_owner(current_tenant())
    turn_budget.require_turn_budget()
