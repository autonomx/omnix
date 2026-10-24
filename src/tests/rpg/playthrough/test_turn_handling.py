"""Playthrough: refusals, questions, ambiguity, and two submissions at once (RQ-0.3)."""
from __future__ import annotations

import threading
import uuid

import pytest

from tests.rpg.playthrough.campaigns import POSTGRES, in_worlds
from tests.rpg.playthrough.scripted_model import Role

pytestmark = POSTGRES

NO_ONE_PRESENT = ("RQ-2.0: a lore-only world (Vesper-9) launches with an empty world model: no one is present at "
                  "its opening to ask")
REFUSALS = {
    "aurelia": ("I buy a dragon from Brindle Gearwing.", ("go to Starfall Village",)),
    "starter": ("I buy a dragon from Bran.", ()),
    "vesper": ("I buy a dragon.", ()),
}


@pytest.mark.parametrize("world", in_worlds())
def test_a_refused_action_changes_nothing_but_the_turn(launch, world) -> None:
    play = launch(world)
    command, route = REFUSALS[world]
    play.turn("look around")
    for step in route:
        play.turn(step)
    before = play.facts()
    body = play.turn(command)
    after = play.facts()
    assert after["turn_count"] == before["turn_count"] + 1  # a refusal is still a turn
    for fact in ("purse_copper", "inventory", "location_id", "hp", "quests", "party"):
        assert after[fact] == before[fact], fact
    assert body["ok"] is not False and body["visible_response"]["plain_text"]


ASKED = {"aurelia": ("Liora Fen", "npc:liora-fen"), "starter": ("Bran", "npc:bran"), "vesper": ("someone", "")}


@pytest.mark.parametrize("world", in_worlds(vesper=NO_ONE_PRESENT, starter=(
    "RQ-2.8: the starter tavern's scene lists no one present, so a question to Bran takes the long path (an NPC "
    "dialogue call and then the narrative writer) instead of one short call")))
def test_a_question_to_someone_present_is_one_short_call(launch, world) -> None:
    play = launch(world)
    name, npc_id = ASKED[world]
    play.model.answer(Role.DIALOGUE, (name, "The gate hums at dusk."))
    before, calls = play.facts(), len(play.model.calls)
    body = play.turn(f"I ask {name} what she thinks of the weather here.")
    assert play.model.roles(calls) == ["dialogue"]  # one short call writes the line, nothing else
    speakers = [block.get("speaker_id") for block in body["canonical_narrative_response"]["blocks"]]
    assert npc_id in speakers
    assert "The gate hums at dusk." in body["visible_response"]["plain_text"]
    after = play.facts()
    for fact in ("purse_copper", "inventory", "location_id", "quests", "party"):
        assert after[fact] == before[fact], fact
    assert after["turn_count"] == before["turn_count"] + 1


@pytest.mark.parametrize("world", in_worlds("aurelia"))
def test_an_ambiguous_command_asks_one_question(launch, world) -> None:
    play = launch(world)
    play.turn("go to Starfall Village")
    assert len(play.present()) >= 3
    calls, count, before = len(play.model.calls), play.turn_count(), play.facts()
    # The command grammar asks who is meant (RQ-3.1), and the turn pipeline commits the question as the turn's
    # answer (RQ-1.4): a turn that changes nothing else and passes no time.
    body = play.turn("I talk to him.")
    assert body["visible_response"]["plain_text"].strip() == "Who are you speaking to?"
    assert play.model.roles(calls) == []  # the game asks; no model picks someone or writes the question
    assert play.turn_count() == count + 1
    after = play.facts()
    for fact in ("purse_copper", "inventory", "location_id", "hp", "quests", "party", "survival"):
        assert after[fact] == before[fact], fact


@pytest.mark.parametrize("world", in_worlds("aurelia", aurelia=(
    "RQ-2.4: the command grammar reads 'I eat one Lantern Bread.' as using the carried item, but the turn's "
    "item rules know only the built-in catalog (unknown_item) and its drop/take paths differ from the ground-"
    "item rules; one item engine (RQ-2.4) takes the grammar's item actions")))
def test_using_a_carried_item_by_text(launch, world) -> None:
    play = launch(world)
    play.turn("I eat one Lantern Bread.")
    assert play.inventory()["Lantern Bread"] == 1


@pytest.mark.parametrize("world", in_worlds("aurelia"))
def test_two_submissions_racing_on_one_revision(launch, world) -> None:
    """Two tabs submit at once against the same revision: the campaign's turns run one at a time (RQ-1.4), so
    both commit, one after the other; nothing commits twice and no revision is skipped."""
    play = launch(world)
    play.turn("look around")
    revision, turns = play.revision(), play.turn_count()
    responses: dict[str, object] = {}
    start = threading.Barrier(2)

    def submit(command: str) -> None:
        start.wait()
        responses[command] = play.post_turn(command, submission_id=f"submit-{uuid.uuid4().hex}")

    threads = [threading.Thread(target=submit, args=(command,)) for command in ("wait", "Check my quests")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=120)
    codes = sorted(response.status_code for response in responses.values())
    committed = codes.count(200)
    assert codes == [200, 200], [(c, r.text[:200]) for c, r in responses.items()]
    assert play.revision() == revision + committed
    assert play.turn_count() == turns + committed
    rows = play.turn_rows()
    assert [row["resulting_revision"] for row in rows] == list(range(rows[0]["resulting_revision"], play.revision() + 1))
    assert len({row["submission_id"] for row in rows}) == len(rows)


@pytest.mark.parametrize("world", in_worlds("aurelia"))
def test_a_submission_retried_commits_once(launch, world) -> None:
    play = launch(world)
    submission = f"submit-{uuid.uuid4().hex}"
    first = play.turn("wait", submission_id=submission)
    revision, turns = play.revision(), play.turn_count()
    again = play.post_turn("wait", submission_id=submission)
    assert again.status_code == 200, again.text[:300]
    assert play.revision() == revision and play.turn_count() == turns
    assert again.json()["turn_id"] == first["turn_id"]


@pytest.mark.parametrize("world", in_worlds("aurelia"))
def test_an_earlier_narration_finishing_meanwhile_moves_no_revision(launch, world) -> None:
    """RQ-1.4: a turn's narration is kept beside the campaign document, so one that finishes after its turn
    committed is no campaign revision, and the player's next turn commits on the revision it read."""
    from app.apps.rpg.session.persistence.session_records import load_session_from_postgres, save_session_to_postgres

    play = launch(world)
    play.turn("look around")
    revision = play.revision()
    # What a deferred narration job does when it finishes (session/narration_jobs.py): it stores the
    # finished narration in the campaign's runtime state and saves the session.
    session = load_session_from_postgres(play.session_id)
    artifact = {"turn_id": "turn:1", "narration": "Done.", "artifact_type": "turn_narration"}
    session["runtime_state"].setdefault("narration_artifacts", []).append(artifact)
    session["runtime_state"].setdefault("narration_artifacts_by_turn", {})["turn:1"] = artifact
    save_session_to_postgres(session)
    assert play.revision() == revision  # narration is not a campaign revision
    assert "narration_artifacts" not in play.stored_row_state()["runtime_state"]  # nor part of the document
    play.turn("wait")
    assert play.revision() == revision + 1
    assert play.stored()["runtime_state"]["narration_artifacts_by_turn"]["turn:1"]["narration"] == "Done."
