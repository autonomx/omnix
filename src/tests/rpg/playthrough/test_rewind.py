"""Playthrough: undo and save points (RQ-5.7; docs/rpg/design/rewind.md)."""
from __future__ import annotations

from tests.rpg.playthrough.campaigns import POSTGRES

pytestmark = POSTGRES


def _rewind(play, save_point: str | None = None):
    return play.client.post(f"/api/rpg/sessions/{play.session_id}/rewind",
                            json={"save_point": save_point} if save_point else {})


def test_undo_restores_the_game_as_a_new_revision_and_twice_goes_two_turns_back(launch) -> None:
    play = launch("aurelia")
    start = (play.inventory(), play.purse(), play.turn_count())
    play.turn("I drop the Lantern Bread.")
    play.turn("I drop the Lantern Bread.")
    assert "Lantern Bread" not in play.inventory()
    revision, rows = play.revision(), len(play.turn_rows())

    undone = _rewind(play)
    assert undone.status_code == 200, undone.text[:300]
    assert undone.json()["visible_response"]["plain_text"] == "You return to the moment before your last turn."
    assert play.inventory()["Lantern Bread"] == 1  # one drop undone
    assert play.revision() == revision + 1 and len(play.turn_rows()) == rows + 1  # a new revision; history kept
    assert _rewind(play).status_code == 200  # twice: two turns back
    assert (play.inventory(), play.purse(), play.turn_count()) == start

    play.client.post(f"/api/rpg/sessions/{play.session_id}/resume", json={"elapsed_seconds": 60},
                     headers={"x-omnix-rpg-submission-id": "resume-1"})
    play.turn("I drop the Lantern Bread.")
    play.client.post(f"/api/rpg/sessions/{play.session_id}/resume", json={"elapsed_seconds": 60},
                     headers={"x-omnix-rpg-submission-id": "resume-2"})
    assert _rewind(play).status_code == 200  # past the world's ticks, to before the hero's own turn
    assert play.inventory()["Lantern Bread"] == 2


def test_a_save_point_is_returned_to_and_can_be_forgotten(launch) -> None:
    play = launch("aurelia")
    saved = play.client.post(f"/api/rpg/sessions/{play.session_id}/save-points", json={"name": "Before the gate"})
    assert saved.status_code == 200, saved.text[:300]
    here, turns = play.location(), play.turn_count()
    play.turn("go to Starfall Village")
    play.turn("wait")
    assert play.location() != here
    back = _rewind(play, "Before the gate")
    assert back.status_code == 200, back.text[:300]
    assert back.json()["visible_response"]["plain_text"] == 'You return to the save point "Before the gate".'
    assert play.location() == here and play.turn_count() == turns
    listed = play.client.get(f"/api/rpg/sessions/{play.session_id}/save-points").json()["save_points"]
    assert [point["name"] for point in listed] == ["Before the gate"]
    assert play.client.delete(f"/api/rpg/sessions/{play.session_id}/save-points/Before the gate").status_code == 200
    assert _rewind(play, "Before the gate").status_code == 409  # forgotten


def test_a_hardcore_campaign_has_no_going_back(launch) -> None:
    play = launch("aurelia", gameplay={"permadeath": True})
    play.turn("wait")
    revision = play.revision()
    refused = _rewind(play)
    assert refused.status_code == 409 and "hardcore" in refused.text and play.revision() == revision
    assert play.client.post(f"/api/rpg/sessions/{play.session_id}/save-points",
                            json={"name": "Never"}).status_code == 409


def test_a_moment_that_will_not_upgrade_is_refused_not_a_server_error(launch, monkeypatch) -> None:
    from pydantic import BaseModel

    from app.apps.rpg.foundation.persistence.rpg_repository import PostgresRpgRepository
    from app.apps.rpg.session import campaign_state

    class Strict(BaseModel):
        required: int

    upcast, read = campaign_state.upcast_if_outdated, PostgresRpgRepository.document_at_revision

    def earlier(self, *args, **kwargs):
        document = read(self, *args, **kwargs)
        return {**document, "_will_not_upgrade": True} if document is not None else None

    def upgrade(document):
        if document.get("_will_not_upgrade"):  # as an earlier revision whose upgrade fails validation would
            Strict.model_validate({})
        return upcast(document)

    play = launch("aurelia")
    play.turn("I drop the Lantern Bread.")
    monkeypatch.setattr(PostgresRpgRepository, "document_at_revision", earlier)
    monkeypatch.setattr(campaign_state, "upcast_if_outdated", upgrade)
    refused = _rewind(play)
    assert refused.status_code == 409, refused.text[:300]
    assert "can no longer be rebuilt" in refused.text
