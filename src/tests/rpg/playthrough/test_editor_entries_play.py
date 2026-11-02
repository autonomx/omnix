"""Playthrough: what the world editor adds or changes is played (evolution roadmap EV-6).

Aurelia, as installed from its bundle, has nothing to recompile its canon from; its people are its ``characters``
topic's list and its things its ``economy`` topic's ``items``. An author adds a person there and changes a blade's
gear through the editor's own entry functions, publishes, and a campaign launched after it has both.
"""
from __future__ import annotations

from tests.rpg.playthrough.campaigns import AURELIA, POSTGRES, _import_and_adopt, _launch_scenario

pytestmark = POSTGRES

PERSON = {"id": "npc:tamsin-reed", "kind": "npc", "name": "Tamsin Reed", "role": "lantern keeper",
          "species": "human", "location_id": "location:aurelia:starfall-village",
          "biography": "Tamsin keeps the village's lanterns lit through the long blue nights."}


def _topic(world_id: str, topic_id: str) -> dict:
    from app.persistence.unit_of_work import unit_of_work
    from app.runtime.tenant_context import current_tenant

    with unit_of_work() as work:  # as the editor's page reads it
        topic = work.world_generation.get_topic(current_tenant(), world_id=world_id, topic_id=topic_id)
        work.rollback()
    return topic


def test_a_person_and_gear_written_in_the_editor_are_played(tmp_path, monkeypatch) -> None:
    from app.apps.rpg.genesis.worlds.entity_authoring import add_world_entity, update_world_entity
    from app.apps.rpg.genesis.worlds.play_section_authoring import publish_play_sections
    from app.apps.rpg.session.service import load_session

    world_id = _import_and_adopt(AURELIA, tmp_path, monkeypatch, name="aurelia-editor")
    people = _topic(world_id, "characters")
    added = add_world_entity(world_id, "characters", expected_draft_revision=int(people["draft_revision"]),
                             expected_content_hash=str(people["content_hash"]), entity=PERSON)
    assert any(row["id"] == PERSON["id"] for row in added["topic"]["content"]["characters"])  # where the bundle keeps them
    assert "entities" not in added["topic"]["content"]
    goods = _topic(world_id, "economy")
    blade = next(row for row in goods["content"]["items"] if row["id"] == "item:ashen-oathblade")
    stats = {**blade["equipment"]["stats"], "damage_max": int(blade["equipment"]["stats"]["damage_max"]) + 1}
    update_world_entity(world_id, "economy", "item:ashen-oathblade",
                        expected_draft_revision=int(goods["draft_revision"]),
                        expected_content_hash=str(goods["content_hash"]),
                        changes={"equipment": {**blade["equipment"], "stats": stats}})
    publish_play_sections(world_id)

    session = load_session(_launch_scenario(world_id, "gateborn", {"name": "Wren", "pronouns": "they/them"}))
    world = session["simulation_state"]["world_model"]
    assert world["npcs"][PERSON["id"]]["name"] == "Tamsin Reed"
    assert world["npcs"][PERSON["id"]].get("location_id") == PERSON["location_id"]
    played = next(row for row in session["simulation_state"]["world_model"]["items"].values()
                  if row.get("id") == "item:ashen-oathblade" or row.get("item_id") == "item:ashen-oathblade") \
        if isinstance(world.get("items"), dict) else next(
            row for row in world.get("items") or () if row.get("id") == "item:ashen-oathblade")
    assert played["equipment"]["stats"]["damage_max"] == stats["damage_max"]
