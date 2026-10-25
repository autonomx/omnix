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


ASKED = {"aurelia": ("Liora Fen", "npc:liora-fen"), "starter": ("Bran", "npc:bran"),
         "vesper": ("Mara Vey", "ent:actors:mara-vey")}


@pytest.mark.parametrize("world", in_worlds())
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


@pytest.mark.parametrize("world", in_worlds("aurelia"))
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


@pytest.mark.parametrize("world", in_worlds("aurelia"))
def test_a_hermes_command_is_a_committed_turn_and_a_retry_commits_once(launch, world) -> None:
    """RQ-1.6: Hermes submits its approved command as the play screen submits a turn, keyed by its submission id;
    the turn commits (it ran on a copy before and was never saved) and Hermes reads its TurnOutcome."""
    from app.apps.rpg.edge.hermes.canonical_submitter import hermes_rpg_canonical_submitter

    play = launch(world)
    revision, turns = play.revision(), play.turn_count()
    submission = f"hermes-{uuid.uuid4().hex}"
    first = hermes_rpg_canonical_submitter({"session_id": play.session_id, "command_text": "wait",
                                            "submission_id": submission})
    assert first["ok"] is True and first["state_changed"] is True, first
    assert play.revision() == revision + 1 and play.turn_count() == turns + 1
    assert play.turn_rows()[-1]["submission_id"] == submission
    assert "turn_counted" in {change["type"] for change in first["outcome"]["applied_changes"]}
    again = hermes_rpg_canonical_submitter({"session_id": play.session_id, "command_text": "wait",
                                            "submission_id": submission})
    assert again["ok"] is True and play.revision() == revision + 1


def test_a_view_the_campaign_has_moved_past_is_refused_with_how_it_stands(launch) -> None:
    """RQ-8.9: a grid command from a view the campaign has moved past (another tab took a turn) is refused, taking
    no turn, with a plain message and the campaign as it stands, so the play screen redraws; so is a map action
    from an outdated map view."""
    play = launch("aurelia")
    play.turn("I attack the Echo Wolf.")
    seen, instance = play.revision(), play.map_instance()
    play.turn("attack")  # another tab's turn
    hero = next(actor for actor in instance["snapshot"]["actors"] if actor["actor_id"].startswith("player:"))
    stale = play.client.post(f"/api/rpg/map-instances/{instance['map_instance_id']}/tactical/move", json={
        "submission_id": "stale-move", "command_id": "command:stale-move", "actor_id": hero["actor_id"],
        "destination": [hero["cell"][0] - 1, hero["cell"][1]],
        "expected_map_state_revision": int(instance["snapshot"]["map_state_revision"]),
        "expected_campaign_revision": seen})
    assert stale.status_code == 409, stale.text[:300]
    detail = stale.json()["detail"]
    assert detail["stale_view"] is True and detail["current_revision"] == seen + 1 == play.revision()
    assert detail["message"].startswith("The fight moved on") and detail["session"]["state"]["turn_count"] == play.turn_count()

    map_id = play.stored()["state"]["map_state"]["current_map_id"]
    overlay = play.client.get(f"/api/rpg/sessions/{play.session_id}/maps/{map_id}/overlay").json()
    outdated = play.client.post(f"/api/rpg/sessions/{play.session_id}/maps/{map_id}/map-actions", json={
        "action": "inspect", "target_object_id": "anything", "definition_revision": overlay["definition_revision"],
        "overlay_revision": int(overlay["overlay_revision"]) + 1})  # a view of another revision
    assert outdated.status_code == 409, outdated.text[:300]
    assert outdated.json()["detail"]["message"].startswith("The map changed") and outdated.json()["detail"]["session"]
