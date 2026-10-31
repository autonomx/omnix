"""Playthrough: what the game master invents (evolution roadmap EV-0, part 2). An invention it proposes is checked and
played from the next turn, kept in the campaign's lore layer; on a world whose owner asked for drafts it is filed for
review, and an approved one joins the world at its next publication, with its play data, under a canon id."""
from __future__ import annotations

from tests.rpg.playthrough.campaigns import POSTGRES
from tests.rpg.playthrough.scripted_model import Role

pytestmark = POSTGRES
VILLAGE = "location:aurelia:starfall-village"


def _ask_for_drafts(world_id: str) -> None:
    from app.apps.rpg.session.lore_review import DRAFTS_KEY
    from app.persistence.unit_of_work import unit_of_work
    from app.runtime.tenant_context import current_tenant

    context = current_tenant()
    with unit_of_work() as work:
        world = work.world_scenarios.get_world(context, world_id)
        work.world_scenarios.replace_world_metadata(context, world_id, {**dict(world["metadata"]), DRAFTS_KEY: True})
        work.commit()


def test_an_invention_plays_at_once_and_an_approved_one_joins_its_world(launch) -> None:
    from app.apps.rpg.genesis.worlds.play_section_authoring import publish_play_sections
    from app.apps.rpg.narration.game_master.direction_call import direct

    play = launch("aurelia")
    play.turn("go to Starfall Village")
    world_id = play.stored()["manifest"]["world_id"]
    _ask_for_drafts(world_id)
    play.model.answer(Role.GAME_MASTER, {"proposals": [{"kind": "gm_invent", "reason": "the village needs a messenger",
        "payload": {"family": "person", "name": "Tamsin Reed", "description": "A ferrywoman who carries word.",
                    "play": {"location_id": VILLAGE, "role": "ferrywoman",
                             "schedule": [{"from_hour": 0, "to_hour": 24, "location_id": VILLAGE,
                                           "activity": "mending nets"}]}}}]})
    assert direct(play.session_id, play.stored(), "a stall", revision=play.revision())["proposed"] == 1
    assert not any("tamsin" in npc for npc in play.simulation()["world_model"]["npcs"])  # not yet: a proposal
    play.turn("wait for an hour")
    entry_id = next(npc for npc in play.simulation()["world_model"]["npcs"] if npc.endswith(":tamsin-reed"))
    assert entry_id in play.simulation()["lore_layer"]["entries"]
    assert entry_id in play.present()  # she keeps her day where the hero stands

    queue = play.client.get(f"/api/rpg/worlds/{world_id}/lore-review").json()["groups"]
    draft = queue[0]["drafts"][0]
    assert (draft["entry_id"], draft["status"], draft["group_key"]) == (entry_id, "pending", "tamsin reed")
    decided = play.client.post(f"/api/rpg/worlds/{world_id}/lore-review/{draft['id']}/decision",
                               json={"decision": "approve"})
    assert decided.status_code == 200, decided.text[:300]
    canon_id = decided.json()["draft"]["canon_id"]
    assert canon_id == "npc:tamsin-reed"
    again = play.client.post(f"/api/rpg/worlds/{world_id}/lore-review/{draft['id']}/decision", json={"decision": "reject"})
    assert again.status_code == 409

    publish_play_sections(world_id)
    from app.persistence.unit_of_work import unit_of_work
    from app.runtime.tenant_context import current_tenant

    with unit_of_work() as work:
        latest = work.world_scenarios.latest_world_revision(current_tenant(), world_id)
        work.rollback()
    canon = latest["document"]["canon"]
    assert any(row.get("id") == canon_id and row.get("name") == "Tamsin Reed" for row in canon["entities"])
    assert any(row.get("npc_id") == canon_id for row in canon.get("routines") or ())  # with her day, its play data
