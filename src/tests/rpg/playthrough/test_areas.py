"""Playthrough: areas filled in as the hero approaches (evolution roadmap EV-10), with the area's detail given as
recorded proposals. Arriving, the hero meets what the area was filled in with; a hidden site is found by exploring,
its rooms are met one way after another, and the last holds its reward. No turn makes a generation call."""
from __future__ import annotations

from tests.rpg.playthrough.campaigns import POSTGRES

pytestmark = POSTGRES
MARCH, GROVE = "region:starfall-march", "location:aurelia:arrival-grove"


def _record(play, entries: list[dict]) -> None:
    from app.apps.rpg.foundation.state.proposals import Proposal
    from app.apps.rpg.session.turn.proposals import record_proposals

    record_proposals(play.session_id, [
        Proposal(proposal_id=f"area:{play.session_id}:{MARCH}:{index}", kind="gm_area", source="area",
                 after_revision=play.revision(), reason=f"filling in {MARCH}", payload={"area_id": MARCH, "entry": entry})
        for index, entry in enumerate(entries)])


def _fight_on(play) -> None:
    for _ in range(40):  # fought to the end
        if not play.combat().get("active"):
            return
        play.turn("attack")


def test_a_site_from_finding_it_to_its_reward(launch) -> None:
    play = launch("aurelia")
    assert play.simulation()["world_model"]["gm_guide"]["areas"][MARCH]["size"] == "medium"  # the author's palette
    _record(play, [
        {"kind": "site", "name": "Rootfall Hollow", "description": "A hollow under the old roots.", "difficulty": 5,
         "play": {"roads": [{"to": GROVE, "travel_time": "20 minutes"}]},
         "site": {"theme": "roots", "rooms": [{"name": "Bramble Door"}, {"name": "Bone Pit"}]}},
        {"kind": "rumour", "told": "Something stirs under the old roots by the grove."}])
    calls = len(play.model.calls)
    play.turn("look around")
    detail = play.simulation()["area_detail"][MARCH]["entries"]
    assert [row["kind"] for row in detail] == ["site", "rumour"]
    site_id = detail[0]["entry_id"]
    for _ in range(8):
        play.turn("search the area for anything hidden")
        if site_id in play.simulation()["exploration"]["found"]:
            break
    assert site_id in play.simulation()["exploration"]["found"]
    play.turn("go to Rootfall Hollow")
    assert play.location() == site_id
    _fight_on(play)  # a place no one lives may hold what bars the way (encounters.md)
    rooms = play.simulation()["lore_layer"]["entries"][site_id]["play"]["site"]["rooms"]
    for room in rooms:
        went = play.turn(f"go to {room['name']}")
        assert play.location() == room["id"], went["visible_response"]
        # The room's own grid, laid out by code and kept with the campaign: the hero stands on it (EV-10).
        on_the_grid = play.stored()["state"].get("current_map_instance_id")
        assert on_the_grid == f"{play.session_id}:map:{room['map']['map_id']}:1"
        if room.get("hazard"):  # met as the hero came in
            assert room["hazard"]["told"] in went["visible_response"]["plain_text"]
        assert play.combat().get("active") is True  # its encounter stands in it
        _fight_on(play)
        assert play.simulation()["exploration"].get("cleared", {}).get(site_id, {}).get(room["id"]) == "beaten", (
            play.combat().get("ended_reason"), play.hp(), room)
    reward = rooms[-1]["loot_item_id"]
    name = next(row["name"] for row in play.simulation()["world_model"]["items"] if row["id"] == reward)
    taken = play.turn(f"pick up the {name.split(' ', 1)[-1] if chr(39) in name.split(' ')[0] else name}")
    assert play.inventory().get(name, 0) >= 1, taken["visible_response"]
    generation = [call for call in play.model.calls[calls:] if call.role.value in {"game_master", "lore", "world"}]
    assert generation == []  # exploring and filling in made no generation call on the turn


def test_a_campaigns_own_room_grids_go_with_it(launch) -> None:
    """Review: a campaign that entered a room of its site deletes cleanly, its own map definitions with it."""
    from app.persistence.unit_of_work import unit_of_work
    from app.runtime.tenant_context import current_tenant

    play = launch("aurelia")
    _record(play, [{"kind": "site", "name": "Rootfall Hollow", "description": "A hollow.", "difficulty": 5,
                    "play": {"roads": [{"to": GROVE}]}, "site": {"rooms": [{"name": "Bramble Door"}]}}])
    play.turn("look around")
    site_id = play.simulation()["area_detail"][MARCH]["entries"][0]["entry_id"]
    for _ in range(8):
        play.turn("search the area for anything hidden")
        if site_id in play.simulation()["exploration"]["found"]:
            break
    play.turn("go to Rootfall Hollow")
    _fight_on(play)
    play.turn("go to Bramble Door")
    assert "rootfall-hollow:room-1" in play.stored()["state"]["current_map_instance_id"]
    context = current_tenant()
    with unit_of_work() as work:
        work.connection.execute("DELETE FROM omnix_rpg_campaigns WHERE workspace_id = %s AND id = %s",
                                (context.workspace_id, play.session_id))
        left = work.connection.execute("SELECT count(*) FROM omnix_rpg_map_definitions WHERE workspace_id = %s"
                                       " AND campaign_id = %s", (context.workspace_id, play.session_id)).fetchone()[0]
        work.commit()
    assert left == 0
