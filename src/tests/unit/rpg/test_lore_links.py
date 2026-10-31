"""Names that open their lore (evolution roadmap EV-12): the links of a final text, never a mark in a draft, nothing
kept from the hero linked or shown, and the entry a click opens."""
from __future__ import annotations

import gzip
import json
from pathlib import Path

from app.apps.rpg.narration import lore_links
from app.apps.rpg.session.campaign_state import upcast_campaign_document

FIXTURE = Path(__file__).resolve().parents[2] / "rpg" / "fixtures" / "campaign_documents_v5" / "aurelia.json.gz"
LIORA, VILLAGE, RUINS = "npc:liora-fen", "location:aurelia:starfall-village", "location:aurelia:moonroot-ruins"
SECRET = "she hears the Meridian Gate whisper the protagonist's true Earth name"


def _simulation() -> dict:
    document = upcast_campaign_document(json.loads(gzip.decompress(FIXTURE.read_bytes())))
    simulation = document["simulation_state"]
    simulation["world_model"]["npcs"][LIORA]["secrets"] = [SECRET]
    simulation["world_model"]["npcs"][LIORA]["description"] = f"A foxkin guide. In truth {SECRET}."
    return simulation


def _linked(text: str, simulation: dict, marks=()) -> list[tuple[str, str]]:
    return [(text[span["start"]:span["end"]], span["entry_id"])
            for span in lore_links.spans(text, simulation, marks=marks)]


def test_names_as_written_link_their_entries_and_common_words_do_not() -> None:
    simulation = _simulation()
    text = "Liora Fen waves you toward Starfall Village; the village is quiet."
    assert _linked(text, simulation) == [("Liora Fen", LIORA), ("Starfall Village", VILLAGE)]
    assert _linked("Liora smiles.", simulation) == [("Liora", LIORA)]  # a person's own name, shared by no one


def test_a_mark_links_only_a_name_of_an_entry_the_world_has() -> None:
    simulation = _simulation()
    marked = "You reach [[the village|location:aurelia:starfall-village]] and [[a guide|npc:liora-fen]], [[x|npc:no]]."
    shown = lore_links.note(marked)
    assert shown == "You reach the village and a guide, x."
    marks = lore_links.taken()
    assert lore_links.noted() == ()  # one response's marks are forgotten once taken
    assert _linked(shown, simulation, marks) == []  # "the village" and "a guide" are not their names
    assert _linked("At STARFALL VILLAGE.", simulation, [("STARFALL VILLAGE", VILLAGE)]) == [("STARFALL VILLAGE", VILLAGE)]
    assert _linked("Liora Fen is here; she will fen.", simulation, [("Liora Fen", LIORA)]) == [("Liora Fen", LIORA)]


def test_a_name_two_entries_share_links_only_the_one_a_mark_names() -> None:
    simulation = _simulation()
    simulation["world_model"]["locations"]["location:aurelia:other"] = {"name": "Starfall Village"}
    assert _linked("Starfall Village", simulation) == []
    assert _linked("Starfall Village", simulation, [("Starfall Village", VILLAGE)]) == [("Starfall Village", VILLAGE)]


def test_nothing_kept_from_the_hero_is_linked_or_shown() -> None:
    simulation = _simulation()
    simulation["world_model"]["locations"][RUINS]["hidden"] = True
    assert _linked("The Moonroot Ruins", simulation) == []
    assert lore_links.entry_view({"simulation_state": simulation}, RUINS) is None
    view = lore_links.entry_view({"simulation_state": simulation}, LIORA)
    assert view is not None and view["name"] == "Liora Fen"
    shown = json.dumps(view)
    assert "secrets" not in shown and "whisper" not in shown  # no secret field, and no sentence telling one


def test_a_draft_never_shows_a_mark_and_a_final_text_loses_no_words() -> None:
    assert lore_links.strip_marks("You see [[Liora Fen|npc:liora-fen]] by [[Starf", draft=True) == "You see Liora Fen by "
    assert lore_links.strip_marks("You meet [[Rhea|npc:rhea and she nods.") == "You meet Rhea and she nods."


def test_the_links_of_a_response_and_what_the_hero_hears_of_by_them() -> None:
    simulation = _simulation()
    simulation["hero_knowledge"] = {"entries": {VILLAGE: {"kind": "visited"}}}
    visible = {"narration": "Starfall Village is busy.", "messages": [{"text": "Find Liora Fen."}]}
    links = lore_links.visible_links(visible, simulation)
    assert links == {"narration": [{"entry_id": VILLAGE, "start": 0, "end": 16}],
                     "messages": [[{"entry_id": LIORA, "start": 5, "end": 14}]]}
    assert lore_links.heard_of_now(links, simulation) == [LIORA]


def test_a_quote_inside_narration_is_spoken_by_its_speaker_when_they_are_there() -> None:
    simulation = _simulation()
    simulation["present_npc_state"] = {"present_npc_ids": [LIORA]}
    text = lore_links.note('Liora leans close. <<npc:liora-fen|"Stay near me.">> <<npc:no-one|"Who?">>')
    assert text == 'Liora leans close. "Stay near me." "Who?"'
    spoken = lore_links.voices(text, simulation, lore_links.taken_quotes())
    assert [(text[row["start"]:row["end"]], row["speaker_id"]) for row in spoken] == [('"Stay near me."', LIORA)]
    assert lore_links.taken_quotes() == ()
    assert lore_links.strip_marks('He says <<npc:x|"Hold', draft=True) == "He says "
