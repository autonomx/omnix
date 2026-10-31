"""Playthrough: names that open their lore (evolution roadmap EV-12). A turn's response comes with the links of its
final text; a click opens the entry's public lore and changes nothing, at no model call; and an entry the response
named that the hero did not know is heard of only by the next turn, through a folded narration proposal."""
from __future__ import annotations

from tests.rpg.playthrough.campaigns import POSTGRES
from tests.rpg.playthrough.scripted_model import Role

pytestmark = POSTGRES
RUINS = "location:aurelia:moonroot-ruins"


def _named(body: dict) -> list[tuple[str, str]]:
    visible = body["visible_response"]
    links = visible.get("links") or {}
    named = [(visible["narration"][span["start"]:span["end"]], span["entry_id"]) for span in links.get("narration", ())]
    for message, spans in zip(visible.get("messages") or (), links.get("messages") or ()):
        named += [(message["text"][span["start"]:span["end"]], span["entry_id"]) for span in spans]
    return named


def test_a_name_in_the_story_opens_its_lore_and_is_heard_of_by_the_next_turn(launch) -> None:
    play = launch("aurelia")
    play.turn("look around")
    play.model.answer(Role.DIALOGUE, ("Liora Fen", "The [[Moonroot Ruins|location:aurelia:moonroot-ruins]] lie east."))
    body = play.turn("ask Liora Fen about the Moonroot Ruins")
    named = _named(body)
    assert (("Moonroot Ruins", RUINS) in named), (body["visible_response"], named)
    shown = [body["visible_response"]["narration"], *(row["text"] for row in body["visible_response"]["messages"])]
    assert not any("[[" in text for text in shown)
    def linkable() -> set[str]:
        rows = play.client.get(f"/api/rpg/sessions/{play.session_id}/lore/linkable").json()["entries"]
        return {row["entry_id"] for row in rows}

    assert RUINS not in linkable()  # the page links by itself only what the hero knows; the response linked it

    revision, calls, turns = play.revision(), len(play.model.calls), len(play.turn_rows())
    view = play.client.get(f"/api/rpg/sessions/{play.session_id}/lore/entries/{RUINS}")
    assert view.status_code == 200, view.text[:300]
    entry = view.json()["entry"]
    assert entry["name"] == "Moonroot Ruins" and "secrets" not in view.text
    assert (play.revision(), len(play.model.calls), len(play.turn_rows())) == (revision, calls, turns)  # no cost
    assert play.client.get(f"/api/rpg/sessions/{play.session_id}/lore/entries/npc:no-one").status_code == 404

    assert RUINS not in play.simulation()["hero_knowledge"]["entries"]  # not yet: a proposal
    play.turn("look around")
    held = play.simulation()["hero_knowledge"]["entries"][RUINS]
    assert held["kind"] == "heard_of" and RUINS in linkable()
    never = "npc:archon-malrec"  # never named to the hero: not shown
    assert play.client.get(f"/api/rpg/sessions/{play.session_id}/lore/entries/{never}").status_code == 404
    folded = (play.turn_rows()[-1].get("folded_proposals") or {}).get("folded") or []
    assert any(row.get("kind") == "heard_of" and RUINS in str(row) for row in folded), folded  # replay applies it
