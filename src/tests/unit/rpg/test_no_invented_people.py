"""An id is not a person: someone no record names does not speak, and gets no biography."""
from __future__ import annotations

from app.apps.rpg.genesis.forge.npc_lore_projection import ensure_encountered_npc_lore
from app.apps.rpg.rules.dialogue.plan import build_plan


def _simulation() -> dict:
    return {"npc_index": {"npc:he_(unspecified)": {"role": "Local NPC"}, "npc:mara": {"name": "Mara Venn", "role": "Fixer"}}}


def test_someone_no_record_names_does_not_speak() -> None:
    assert build_plan(_simulation(), "npc:he_(unspecified)", "What are you doing here?") is None
    assert build_plan(_simulation(), "npc:nobody", "What are you doing here?") is None


def test_someone_named_still_speaks_under_their_name() -> None:
    plan = build_plan(_simulation(), "npc:mara", "What are you doing here?")
    assert plan is not None and plan.speaker_name == "Mara Venn"


def test_someone_no_record_names_gets_no_biography() -> None:
    session = {"state": {"npc_dossiers": {"npc:mara": {"name": "Mara Venn", "role": "Fixer"}}}}
    bible, ensured, created, _ = ensure_encountered_npc_lore(
        {"entities": {}, "documents": []}, session, explicit_npc_ids=("npc:he_(unspecified)", "npc:mara"))
    assert "npc:he_(unspecified)" not in bible["entities"]
    assert "npc:he_(unspecified)" not in ensured and "npc:he_(unspecified)" not in created
    assert bible["entities"]["npc:mara"]["name"] == "Mara Venn"


def test_a_person_of_the_world_keeps_their_biography_with_no_other_record() -> None:
    session = {"simulation_state": {"world_model": {"npcs": {"npc:liora-fen": {"name": "Liora Fen"}}}}}
    bible, ensured, _, _ = ensure_encountered_npc_lore({"entities": {}, "documents": []}, session, explicit_npc_ids=("npc:liora-fen",))
    assert "npc:liora-fen" in ensured and "npc:liora-fen" in bible["entities"]


def test_a_thing_bought_or_carried_is_no_person_and_gets_no_biography() -> None:
    """What the published-world golden showed: an item and a shop's offers were filed as "Local NPC"s."""
    session = {"simulation_state": {"world_model": {"npcs": {"npc:orik-stonewake": {"name": "Orik Stonewake"}}}}}
    things = ("npc:iron_dagger", "npc:brindle-gearwing:healing-potion", "npc:orik-stonewake:meal")
    bible, ensured, created, _ = ensure_encountered_npc_lore({"entities": {}, "documents": []}, session, explicit_npc_ids=things)
    assert not set(things) & set(bible["entities"])
    assert not ensured and not created
