"""Who speaks in a turn the narrative bridge narrates: a world's own person, whatever their id looks like.

Found by the narration eval (Vesper-9, scripted model): "talk to Juno" whose line was not written was narrated as a
dialogue with no speaker, because only ``npc:`` ids counted as people (Vesper-9's are ``ent:actors:...``), and the
turn failed validation (``invalid_speaker``) instead of answering.
"""
from __future__ import annotations

from app.apps.rpg.session.narrative_engine_bridge import _npc_identity


def _result(target_id: str, people: dict) -> dict:
    return {"session": {"simulation_state": {"world_model": {"npcs": people}}},
            "resolved_result": {"target_id": target_id}}


def test_a_worlds_own_person_speaks_by_their_own_id() -> None:
    people = {"ent:actors:juno-rask": {"name": "Juno Rask"}}
    assert _npc_identity(_result("ent:actors:juno-rask", people))[0] == "ent:actors:juno-rask"


def test_a_place_or_an_item_is_still_no_speaker() -> None:
    people = {"ent:actors:juno-rask": {"name": "Juno Rask"}}
    assert _npc_identity(_result("ent:places:tidebreak-docks", people)) == ("", "")
    assert _npc_identity(_result("item:rope", people)) == ("", "")
