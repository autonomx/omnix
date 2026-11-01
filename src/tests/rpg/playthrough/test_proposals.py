"""Playthrough: the proposal record (evolution roadmap EV-11). Work done off the turn reaches the campaign only as a
proposal that a later turn folds in at its load, exactly once, and records on its turn row."""
from __future__ import annotations

import pytest

from app.apps.rpg.foundation.persistence.rpg_proposal_repository import ProposalAlreadySettled
from app.apps.rpg.foundation.state.proposals import Proposal
from app.apps.rpg.rules.hero_knowledge import known_entries, world_entries
from app.apps.rpg.session.turn.proposals import record_proposals
from tests.rpg.playthrough.campaigns import POSTGRES

pytestmark = POSTGRES


def _stored(play, proposal_id: str) -> dict:
    from app.persistence.unit_of_work import unit_of_work
    from app.runtime.tenant_context import current_tenant

    with unit_of_work() as work:
        row = work.rpg_proposals.get(current_tenant(), play.session_id, proposal_id)
        work.rollback()
    assert row is not None
    return row


def _unknown_person(play) -> str:
    simulation = play.simulation()
    known = known_entries(simulation)
    return next(entry for entry, row in world_entries(simulation).items()
                if row["family"] == "person" and entry not in known)


def _heard_of(play, proposal_id: str, entry_id: str) -> Proposal:
    proposal = Proposal(proposal_id=proposal_id, kind="heard_of", source="narration", after_revision=play.revision(),
                        reason="the narrator named them", payload={"entry_id": entry_id})
    assert record_proposals(play.session_id, [proposal]) == 1
    assert record_proposals(play.session_id, [proposal]) == 0  # a source's retry stores nothing again
    return proposal


def test_a_proposal_folds_into_the_next_turn_once_and_its_turn_row_records_it(launch) -> None:
    play = launch("aurelia")
    person = _unknown_person(play)
    _heard_of(play, "proposal:heard-1", person)

    outcome = play.turn("look around")
    assert known_entries(play.simulation())[person] == "heard_of"
    reported = outcome.get("turn_pipeline", {}).get("proposals") or {}
    row = play.turn_rows()[-1]
    stored = _stored(play, "proposal:heard-1")
    assert stored["status"] == "folded" and stored["settled_by_turn_id"] == row["id"]
    assert [entry["proposal_id"] for entry in row["folded_proposals"]["folded"]] == ["proposal:heard-1"]
    assert row["folded_proposals"]["folded"][0]["payload"] == {"entry_id": person}  # enough to fold it in again
    assert not reported or [entry["proposal_id"] for entry in reported["folded"]] == ["proposal:heard-1"]

    play.turn("look around")
    again = (play.turn_rows()[-1]["folded_proposals"] or {}).get("folded") or []
    assert "proposal:heard-1" not in [entry["proposal_id"] for entry in again]  # folded in once (the narration's own
    # heard-of proposals, EV-12, may fold in beside it)


def test_a_proposal_its_rule_refuses_is_dropped_with_its_reason(launch) -> None:
    play = launch("aurelia")
    _heard_of(play, "proposal:nobody", "npc:no-such-person")
    play.turn("look around")
    stored = _stored(play, "proposal:nobody")
    assert stored["status"] == "dropped" and stored["drop_reason"] == "no entry 'npc:no-such-person' in this world"
    assert play.turn_rows()[-1]["folded_proposals"]["dropped"] == ["proposal:nobody"]


def test_a_proposal_from_the_last_turn_before_quitting_folds_into_the_return(launch) -> None:
    play = launch("aurelia")
    play.turn("look around")
    person = _unknown_person(play)
    _heard_of(play, "proposal:after-quitting", person)
    response = play.client.post(f"/api/rpg/sessions/{play.session_id}/resume", json={"elapsed_seconds": 60},
                                headers={"x-omnix-rpg-submission-id": "resume-1"})
    assert response.status_code == 200, response.text[:300]
    assert known_entries(play.simulation())[person] == "heard_of"
    assert _stored(play, "proposal:after-quitting")["status"] == "folded"


def test_a_proposal_of_a_later_revision_waits(launch) -> None:
    play = launch("aurelia")
    person = _unknown_person(play)
    later = Proposal(proposal_id="proposal:later", kind="heard_of", source="narration",
                     after_revision=play.revision() + 1, payload={"entry_id": person})
    record_proposals(play.session_id, [later])
    play.turn("look around")
    assert _stored(play, "proposal:later")["status"] == "pending"  # it came after a turn this one did not follow
    play.turn("look around")
    assert _stored(play, "proposal:later")["status"] == "folded"


def test_two_turns_cannot_both_settle_one_proposal(launch) -> None:
    from app.persistence.unit_of_work import unit_of_work
    from app.runtime.tenant_context import current_tenant

    play = launch("aurelia")
    _heard_of(play, "proposal:raced", _unknown_person(play))
    context = current_tenant()
    with unit_of_work() as work:
        work.rpg_proposals.settle(context, campaign_id=play.session_id, turn_id="turn:a", revision=9,
                                  folded=["proposal:raced"], dropped=[])
        work.commit()
    with unit_of_work() as work:
        with pytest.raises(ProposalAlreadySettled):
            work.rpg_proposals.settle(context, campaign_id=play.session_id, turn_id="turn:b", revision=9,
                                      folded=["proposal:raced"], dropped=[])
        work.rollback()
    assert _stored(play, "proposal:raced")["settled_by_turn_id"] == "turn:a"
