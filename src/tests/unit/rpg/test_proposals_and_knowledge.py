"""EV-11's fold-in and EV-1's record of what the hero knows (evolution roadmap 2026-10-29)."""
from __future__ import annotations

import gzip
import json
from pathlib import Path

from app.apps.rpg.foundation.state import changes as c
from app.apps.rpg.foundation.state.proposals import Proposal
from app.apps.rpg.foundation.state.reducer import reduce
from app.apps.rpg.rules.hero_knowledge import entries_met, heard_of, known_entries, seeded_record
from app.apps.rpg.session.campaign_state import CURRENT_SCHEMA_VERSION, upcast_campaign_document
from app.apps.rpg.session.turn.proposals import fold_in

FIXTURE = Path(__file__).resolve().parents[2] / "rpg" / "fixtures" / "campaign_documents_v5" / "aurelia.json.gz"
ELYRA = "npc:elyra-moonroot"


def _document() -> dict:
    return upcast_campaign_document(json.loads(gzip.decompress(FIXTURE.read_bytes())))


def _proposal(proposal_id: str, kind: str = "heard_of", **payload) -> Proposal:
    return Proposal(proposal_id=proposal_id, kind=kind, source="narration", after_revision=3, payload=payload)


def test_the_upgrade_seeds_the_record_from_what_the_campaign_kept() -> None:
    document = _document()
    simulation = document["simulation_state"]
    assert document["manifest"]["schema_version"] == CURRENT_SCHEMA_VERSION == 17
    known = known_entries(simulation)
    here = simulation["player_state"]["location_id"]
    assert known[here] == "visited"
    assert all(known[npc] == "met" for npc in simulation["present_npc_state"]["present_npc_ids"])
    assert simulation["world_facts"] == {} and simulation["group_standing"] == {}
    assert seeded_record(simulation) == simulation["hero_knowledge"]  # the record is what it seeds, once


def test_a_name_heard_folds_in_once_and_a_known_one_is_dropped() -> None:
    document = _document()
    assert ELYRA not in known_entries(document["simulation_state"])
    folded, record = fold_in(document, [_proposal("p:1", entry_id=ELYRA), _proposal("p:2", entry_id=ELYRA)])
    assert [proposal.proposal_id for proposal in record.folded] == ["p:1"]
    assert [(proposal.proposal_id, reason) for proposal, reason in record.dropped] == [
        ("p:2", "the hero already knows it")]
    assert known_entries(folded["simulation_state"])[ELYRA] == "heard_of"
    assert record.changes == (c.EntryMet(entry_id=ELYRA, kind="heard_of", source="narration"),)
    assert ELYRA not in known_entries(document["simulation_state"])  # pure: the document handed in is as it was


def test_what_no_rule_owns_or_the_world_lacks_is_dropped_with_its_reason() -> None:
    document = _document()
    _, record = fold_in(document, [_proposal("p:1", kind="rain_of_frogs"), _proposal("p:2", entry_id="npc:nobody"),
                                   _proposal("p:3")])
    reasons = {proposal.proposal_id: reason for proposal, reason in record.dropped}
    assert reasons == {"p:1": "no rule owns proposals of the kind 'rain_of_frogs'",
                       "p:2": "no entry 'npc:nobody' in this world", "p:3": "no entry '' in this world"}
    assert not record.folded and not record.changes


def test_a_hidden_entry_is_not_heard_of_until_found() -> None:
    document = _document()
    place = next(iter(document["simulation_state"]["world_model"]["locations"]))
    document["simulation_state"]["world_model"]["locations"][place]["hidden"] = True
    document["simulation_state"]["hero_knowledge"]["entries"].pop(place, None)
    assert heard_of(document, {"entry_id": place}).refused.startswith("the world keeps this entry")


def test_meeting_replaces_hearing_of_and_never_the_reverse() -> None:
    document, _ = reduce(_document(), [c.EntryMet(entry_id=ELYRA, kind="heard_of")])
    simulation = document["simulation_state"]
    assert [change.kind for change in entries_met(simulation, [c.DialogueExchanged(npc_id=ELYRA)])] == ["met"]
    document, _ = reduce(document, [c.EntryMet(entry_id=ELYRA, kind="met")])
    again, patch = reduce(document, [c.EntryMet(entry_id=ELYRA, kind="heard_of")])
    assert patch == [] and known_entries(again["simulation_state"])[ELYRA] == "met"


def test_a_turn_shows_the_hero_the_place_they_reach_and_the_things_they_take() -> None:
    document = _document()
    simulation = document["simulation_state"]
    item = simulation["world_model"]["items"][0]["id"]
    simulation["hero_knowledge"]["entries"].pop(item, None)
    met = entries_met(simulation, [c.ItemAdded(item_id=item, name="x"), c.ItemAdded(item_id="item:not-of-this-world",
                                                                                    name="y")])
    assert [(change.entry_id, change.kind) for change in met] == [(item, "met")]  # what the world lacks is no entry


def test_facts_and_standing() -> None:
    document, _ = reduce(_document(), [c.FactSet(fact_id="fact:gate", value="sealed", known=False),
                                       c.StandingChanged(group_id="faction:x", delta=150)])
    simulation = document["simulation_state"]
    assert simulation["world_facts"]["fact:gate"]["known"] is False
    assert simulation["group_standing"]["faction:x"] == 100  # held between -100 and 100
    learned, _ = reduce(document, [c.FactLearned(fact_id="fact:gate")])
    assert learned["simulation_state"]["world_facts"]["fact:gate"]["known"] is True
    reset, _ = reduce(learned, [c.FactSet(fact_id="fact:gate", value="open", known=False)])
    assert reset["simulation_state"]["world_facts"]["fact:gate"] == {**reset["simulation_state"]["world_facts"]["fact:gate"],
                                                                    "value": "open", "known": True}  # still known
