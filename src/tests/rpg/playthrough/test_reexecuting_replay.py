"""Playthrough: re-executing replay (evolution roadmap §2, EV-11's D1 gate on a short run).

D1 rebuilt each turn from its stored patch; that cannot catch a rule that depends on something unrecorded. Here a
campaign is played, and then re-executed: a second campaign, launched the same way, plays the same inputs, with every
intent call answered by the reading the first run recorded (the reading and its slots, or a card), each turn folding
in the set the first run's turn row recorded (``folded_proposals_jsonb``, not the store), and the same returns after
time away. Each turn's document, ids and times normalized, must hash as the first run's did.
"""
from __future__ import annotations

import json

from app.apps.rpg.foundation.state.proposals import Proposal
from app.apps.rpg.rules.hero_knowledge import known_entries, world_entries
from app.apps.rpg.session.turn.proposals import record_proposals, replay_folded
from tests.characterization.test_rpg_published_world_golden import _document_hash
from tests.rpg.playthrough.campaigns import POSTGRES, Playthrough, launch_aurelia
from tests.rpg.playthrough.scripted_model import Role

pytestmark = POSTGRES

LINES = ("look around", "I greet Liora Fen and ask her where I am", "go to Starfall Village",
         "I ask Brindle Gearwing what a Healing Potion costs.", "I buy a Healing Potion from Brindle Gearwing.",
         "I drop one Lantern Bread on the ground.", "I pick up the Lantern Bread.", "wait", "Check my quests")


def _proposal(play: Playthrough) -> Proposal:
    simulation = play.simulation()
    known = known_entries(simulation)
    person = next(entry for entry, row in world_entries(simulation).items()
                  if row["family"] == "person" and entry not in known)
    return Proposal(proposal_id="proposal:replay-heard", kind="heard_of", source="narration",
                    after_revision=play.revision(), payload={"entry_id": person})


def _play(play: Playthrough, world_id: str, *, recorded: list[str] | None = None,
          folds: list[list[dict]] | None = None) -> tuple[list[str], list[str], list[list[dict]]]:
    """Play the scenario; its normalized hash after each input, the intent answers it was given, and what each of
    its turns folded in, as its turn rows recorded it."""
    model = play.model
    answers: list[str] = []
    start = len(play.turn_rows())
    commits = iter(folds or ())

    def next_turn() -> None:  # re-executed: the turn folds in what the first run's same turn did
        if folds is not None:
            replay_folded(play.session_id, next(commits, []))
    if recorded is not None:  # re-executed: every intent call answered by the reading the first run recorded
        model.session_id = ""
        model.queue(Role.INTENT, *(json.loads(answer) for answer in recorded))
    hashes = []
    last: dict = {}

    def after(step: str) -> None:
        hashes.append(f"{step}:{_document_hash(play.stored(), play.session_id, world_id)}")

    for index, line in enumerate(LINES):
        if index == 3 and folds is None:  # a name heard in narration, folded into the next turn (EV-11)
            record_proposals(play.session_id, [_proposal(play).model_copy(update={"after_revision": play.revision()})])
        if index == 6:  # the player goes away and comes back: a return
            next_turn()
            response = play.client.post(f"/api/rpg/sessions/{play.session_id}/resume", json={"elapsed_seconds": 60},
                                        headers={"x-omnix-rpg-submission-id": f"resume-{index}"})
            assert response.status_code == 200, response.text[:300]
            after("resume")
        if index == 8:  # a card the game offered: its reading, with no model call
            offered = (last.get("outcome") or {}).get("presentation") or {}
            card = next(row for row in offered["suggestions"] if row.get("action", {}).get("family") == "status")
            next_turn()
            response = play.client.post(f"/api/rpg/sessions/{play.session_id}/turn",
                                        json={"command": card["command"], "card": card["action"]})
            assert response.status_code == 200, response.text[:300]
            after("card")
        calls = len(model.calls)
        next_turn()
        last = play.turn(line)
        answers += [call.answer for call in model.calls[calls:] if call.role is Role.INTENT]
        after(line)
    folded = [list((row.get("folded_proposals") or {}).get("folded") or ()) for row in play.turn_rows()[start:]]
    return hashes, answers, folded


def test_a_campaign_re_executed_from_its_recorded_inputs_hashes_as_it_did(model, tmp_path, monkeypatch) -> None:
    session_id, world_id = launch_aurelia(tmp_path, monkeypatch)
    first = Playthrough(session_id)
    first.model, model.session_id = model, session_id
    hashes, answers, folds = _play(first, world_id)
    assert len(answers) == len(LINES)  # every typed line went to the intent call (EV-9); the card did not
    assert any(row["proposal_id"] == "proposal:replay-heard" for turn in folds for row in turn)

    session_id, world_id = launch_aurelia(tmp_path, monkeypatch)
    again = Playthrough(session_id)
    again.model = model
    replayed, _, refolded = _play(again, world_id, recorded=answers, folds=folds)
    assert replayed == hashes and refolded == folds  # folded from the turn rows, as recorded
