"""A campaign the v5 code saved upgrades once, as a system turn, and plays on (RQ-1.1; the desktop upgrade).

An install updated over v5 campaigns opens them with the v6 code. Here a campaign is played, then its stored
document is rewritten as the v5 code stored it (manifest version 5, the simulation's copy in the setup, no
world-binding marker, a World Forge campaign's creation artifacts in the document three times over). Opening
it through the gateway upgrades it: a pinned backup at revision R, a system turn at R+1 with a pinned v6
snapshot, the artifacts kept once outside the document; then a turn plays at R+2, and the whole chain replays
across the version boundary.
"""
from __future__ import annotations

import importlib.util
from copy import deepcopy
from pathlib import Path

import pytest

from tests.rpg.playthrough.campaigns import POSTGRES

pytestmark = POSTGRES

_ROOT = Path(__file__).resolve().parents[4]


def _replay_audit():
    spec = importlib.util.spec_from_file_location("omnix_rpg_replay_audit", _ROOT / "scripts/rpg_replay_audit.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _store_as_v5(session_id: str) -> dict:
    """Rewrite the campaign's stored document the way the v5 code stored it; the v5 document."""
    from app.apps.rpg.foundation.persistence.rpg_repository import canonical_json, state_hash
    from app.persistence.unit_of_work import unit_of_work
    from app.security.tenant_context import current_tenant

    context = current_tenant()
    with unit_of_work() as work:
        campaign = work.rpg.get_campaign(context, session_id, for_update=True)
        artifacts = work.rpg.get_campaign_artifacts(context, session_id)
        document = deepcopy(dict(campaign["state"]))
        document["manifest"]["schema_version"] = 5
        if set(document["state"].get("world_binding") or {}) == {"kind"}:
            document["state"].pop("world_binding")
        metadata = document["setup_payload"].setdefault("metadata", {})
        metadata["simulation_state"] = deepcopy(document["simulation_state"])
        if "compiled_genesis" in artifacts:
            for section, key in (("setup_payload", "compiled_genesis"), ("state", "compiled_genesis_snapshot"),
                                 ("runtime_state", "compiled_genesis_snapshot")):
                document[section][key] = deepcopy(artifacts["compiled_genesis"])
            for section in ("setup_payload", "state", "runtime_state"):
                document[section]["bootstrap_snapshot"] = deepcopy(artifacts["bootstrap_snapshot"])
            work.connection.execute("DELETE FROM omnix_rpg_campaign_artifacts WHERE campaign_id = %s", (session_id,))
        work.connection.execute(
            "UPDATE omnix_rpg_campaigns SET state_jsonb = %s::jsonb, state_hash = %s WHERE id = %s",
            (canonical_json(document), state_hash(document), session_id),
        )
        # The v5 code recorded no document version on its turn rows.
        work.connection.execute("UPDATE omnix_rpg_turns SET document_version = NULL WHERE campaign_id = %s", (session_id,))
        work.commit()
    return document


def _rows(session_id: str) -> tuple[list[tuple], list[tuple], dict]:
    from app.persistence.unit_of_work import unit_of_work
    from app.security.tenant_context import current_tenant

    context = current_tenant()
    with unit_of_work() as work:
        turns = work.connection.execute(
            "SELECT resulting_revision, command_jsonb, document_version, canonical_effects_jsonb FROM omnix_rpg_turns "
            "WHERE campaign_id = %s ORDER BY sequence", (session_id,)).fetchall()
        snapshots = work.connection.execute(
            "SELECT revision, pinned, document_version FROM omnix_rpg_snapshots WHERE campaign_id = %s ORDER BY revision",
            (session_id,)).fetchall()
        artifacts = work.rpg.get_campaign_artifacts(context, session_id)
        work.rollback()
    return turns, snapshots, artifacts


@pytest.mark.parametrize("world", ["starter", "aurelia", "genesis"])
def test_a_v5_campaign_upgrades_once_as_a_system_turn_and_plays_on(launch, world) -> None:
    play = launch(world)
    play.turn("look around")
    play.turn("wait")
    facts, revision = play.facts(), play.revision()
    v5 = _store_as_v5(play.session_id)

    assert play.facts() == facts  # opening it through the gateway upgrades it, and no fact changes
    assert play.revision() == revision + 1
    stored = play.stored()
    assert stored["manifest"]["schema_version"] == 6
    assert "simulation_state" not in stored["setup_payload"].get("metadata", {})
    turns, snapshots, artifacts = _rows(play.session_id)
    upgrade = turns[-1]
    assert upgrade[0] == revision + 1 and upgrade[2] == 6
    assert upgrade[1] == {"kind": "system", "type": "document_upgrade", "from_document_version": 5,
                          "to_document_version": 6}
    assert upgrade[3]["inventory_differences"] == []  # this campaign's copies already agreed
    assert (revision, True, 5) in snapshots and (revision + 1, True, 6) in snapshots
    if world == "genesis":
        assert sorted(artifacts) == ["bootstrap_snapshot", "compiled_genesis"]
        assert artifacts["compiled_genesis"] == v5["setup_payload"]["compiled_genesis"]
        for section in ("setup_payload", "state", "runtime_state"):
            assert "bootstrap_snapshot" not in stored[section]
    if world == "starter":  # the classic new game is an opening of the starter world (RQ-2.8)
        assert stored["state"]["world_binding"]["world_id"].startswith("world:the-market-road-")

    assert play.revision() == revision + 1  # opened again: upgraded once only
    play.turn("wait")
    turns, _, _ = _rows(play.session_id)
    assert turns[-1][0] == revision + 2 and turns[-1][2] == 6
    assert play.turn_count() == facts["turn_count"] + 1

    audit = _replay_audit()
    from app.persistence.unit_of_work import unit_of_work

    with unit_of_work() as work:
        report = audit._load(work.connection, [play.session_id])[0]
        work.rollback()
    assert report["replay_reaches_current"] and report["replay_matches_current"], report
    assert report["document_version_boundaries"] == [revision + 1]  # the upgrade turn, after unrecorded v5 rows
    assert report["document_version_mismatches"] == []
    assert report["verified_turns_by_document_version"]["6"] == 2


@pytest.mark.parametrize("world", ["starter", "aurelia", "vesper", "genesis"])
def test_the_typed_view_reads_what_the_play_screen_shows(launch, world) -> None:
    """CampaignStateView's sections read the same facts the play screen shows, after turns that change them."""
    from app.apps.rpg.foundation.state import CampaignStateView

    play = launch(world)
    for command in ("look around", "Practice swordsmanship with a careful training drill.", "wait"):
        play.turn(command)
    if world == "aurelia":
        play.turn("I ask Liora Fen to join my party as a companion.")
        play.turn("go to Starfall Village")
        play.turn("I buy a Healing Potion from Brindle Gearwing.")
    view = CampaignStateView(play.stored())
    view.validate()
    assert view.meta.document_version == 6
    assert view.inventory.purse.total_copper == play.purse()
    assert {item.name: item.quantity for item in view.inventory.items} == play.inventory()
    assert view.player.hp == play.hp() and view.player.skills["swordsmanship"].xp == 10
    assert view.location.location_id == play.location()
    assert sorted(view.npcs.present_npc_ids) == sorted(play.present())
    assert [companion.npc_id for companion in view.party.companions] == play.party()
    assert {quest.title: quest.status for quest in view.quests.quests} == {
        title: quest.get("status") for title, quest in play.quests().items()}
    assert (view.survival.hunger, view.survival.thirst, view.survival.fatigue) == tuple(
        play.survival()[key] for key in ("hunger", "thirst", "fatigue"))
    assert view.time.turn_count == play.turn_count()
