"""Playthrough: a campaign launched from a published world keeps the id the player was given (the creation wizard's,
while World Forge made its world: genesis/forge/wizard_world.py), and plays on the pipeline."""
from __future__ import annotations

import uuid

from tests.rpg.playthrough.campaigns import AURELIA, POSTGRES, Playthrough, _import_and_adopt

pytestmark = POSTGRES


def test_a_published_launch_under_a_given_id_is_that_campaign(model, tmp_path, monkeypatch) -> None:
    from app.persistence.unit_of_work import unit_of_work
    from app.runtime.tenant_context import current_tenant
    from app.apps.rpg.edge.api.feature_routes.rpg_world_library_routes import SESSION_CAMPAIGN_SESSIONS
    from app.apps.rpg.genesis.worlds.published_launch import launch_published_scenario

    world_id = _import_and_adopt(AURELIA, tmp_path, monkeypatch, name="aurelia-wizard")
    with unit_of_work() as work:
        context = current_tenant()
        scenario = sorted(work.world_library.iter_scenarios(context, world_id=world_id), key=lambda row: str(row["id"]))[0]
        document = dict(work.world_library.list_scenario_revisions(context, str(scenario["id"]))[0]["document"])
        work.rollback()
    given = f"rpg_wizard_{uuid.uuid4().hex[:10]}"
    launched = launch_published_scenario(
        sessions=SESSION_CAMPAIGN_SESSIONS, world_id=world_id, world_revision=int(document["world_revision"]),
        world_release=int(document["compatible_release"]), scenario_id=str(document["scenario_id"]),
        scenario_revision=int(document["revision"]), player={"name": "Wren", "pronouns": "they/them"},
        session_id=given)
    assert launched["session_id"] == given
    play = Playthrough(given)
    play.model = model
    assert play.stored()["manifest"]["session_id"] == given
    assert play.simulation()["world_model"]["world_id"] == world_id  # it plays from the world, under the given id
    assert play.location() and play.simulation()["world_model"]["npcs"]  # it plays from the world
    assert play.turn("look around")["outcome"]["planned_action"] == "look"
