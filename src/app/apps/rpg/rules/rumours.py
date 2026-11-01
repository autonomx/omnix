"""Rumours: word the people of a place come to know and will tell (evolution roadmap EV-4). Pure.

A rumour is campaign state, learned in play: what the world's authors wrote is knowledge in its revision. Word goes
about when a person reaches a beat of a goal (``rules/routines.py``: the beat's ``rumour``, at its places) or when the
game master proposes it (``gm_rumour``). It is kept in the ``world`` section's ``active_rumors``, each with the place
it is told at, and the hero hears it from someone of that place asked for news (``rules/dialogue/plan.py``), for a
price where information is sold (``rules/economy/trade.py``, ``paid_information``), or by being there when it
happens. Heard, it is in the journal; the facts its beat set become known.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from app.apps.rpg.foundation.safe_values import safe_dict as _d, safe_list as _l, safe_str as _s
from app.apps.rpg.foundation.state import access as _sections
from app.apps.rpg.foundation.state.changes import FactLearned, RumourHeard, RumourSpread, StateChange

NEWS = "news"  # the topic a line asks a person for what is going about
TOLD_AT_ONCE = 2  # the rumours one answer or one purchase tells


def rumours(simulation: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The rumours going about, oldest first."""
    return [_d(row) for row in _l(_sections.active_rumors_of(simulation)) if _s(_d(row).get("rumour_id"))]


def untold_at(simulation: Mapping[str, Any], place_id: str) -> list[dict[str, Any]]:
    """The rumours told at ``place_id`` that the hero has not heard, newest first."""
    return [row for row in reversed(rumours(simulation)) if _s(row.get("place_id")) == place_id
            and row.get("heard") is not True and _s(row.get("text"))]


def spread(rumour_id: str, text: str, places: Iterable[str], *, text_id: str = "",
           source: str = "") -> list[RumourSpread]:
    """The word ``text`` going about at each of ``places``: one rumour a place, ``rumour_id@place``. A beat's rumour
    names the beat by ``text_id`` (``routines.beat_address``), and so the facts it tells of."""
    return [RumourSpread(rumour_id=f"{rumour_id}@{place}", place_id=place, text_id=text_id, text=text, source=source)
            for place in dict.fromkeys(_s(place) for place in places) if place]


def _facts_of(simulation: Mapping[str, Any], row: Mapping[str, Any]) -> list[str]:
    """The facts a beat's rumour tells of: those its beat set (its text id is the beat's address)."""
    from app.apps.rpg.rules.routines import beat_by_address

    beat = beat_by_address(simulation, _s(row.get("text_id")))
    return [_s(_d(fact).get("fact")) for fact in _l(_d(beat).get("sets")) if _s(_d(fact).get("fact"))]


def tell(simulation: Mapping[str, Any], rows: Iterable[Mapping[str, Any]], *,
         source: str) -> tuple[list[StateChange], list[str]]:
    """The hero hears each of ``rows``: the rumour heard (every place's copy of it), what its beat set now known; and
    its words."""
    facts = _d(_sections.world_facts_of(simulation))
    changes: list[StateChange] = []
    lines: list[str] = []
    told: set[str] = set()
    learned: set[str] = set()
    for row in rows:
        text = _s(row.get("text"))
        if not text or text in told:
            continue
        told.add(text)
        lines.append(text)
        stem = _s(row.get("rumour_id")).partition("@")[0]
        changes += [RumourHeard(rumour_id=_s(other.get("rumour_id")), source=source) for other in rumours(simulation)
                    if _s(other.get("rumour_id")).partition("@")[0] == stem and other.get("heard") is not True]
        for fact in _facts_of(simulation, row):
            if fact in facts and _d(facts[fact]).get("known") is not True and fact not in learned:
                learned.add(fact)
                changes.append(FactLearned(fact_id=fact, source=f"rumour:{stem}"))
    return changes, lines


def news_here(simulation: Mapping[str, Any], place_id: str) -> list[dict[str, Any]]:
    """What someone of ``place_id`` tells when asked for news: its untold rumours, at most ``TOLD_AT_ONCE``."""
    return untold_at(simulation, place_id)[:TOLD_AT_ONCE]


def fold_rumour(document: Mapping[str, Any], payload: Mapping[str, Any]):
    """Word the game master sends about (EV-0): its line, at one of the world's places; it names no secret; within
    the day's limit."""
    from app.apps.rpg.foundation.state.proposals import Folded, refused
    from app.apps.rpg.rules.consequences import names_a_secret_here
    from app.apps.rpg.rules.direction import allows, counted

    simulation = _d(_sections.simulation_state_of(document))
    place, text = _s(payload.get("location_id")), _s(payload.get("told"))
    if place not in _d(_d(_sections.world_model_of(simulation)).get("locations")):
        return refused("no such place in this world")
    if not text or len(text) > 600 or names_a_secret_here(simulation, text):
        return refused("a rumour needs a line, and names no secret")
    if any(_s(row.get("text")) == text for row in rumours(simulation)):
        return refused("that word is already about")
    limit = allows(simulation, "rumour")
    if limit:
        return refused(limit)
    import hashlib

    stem = hashlib.sha256(f"{place}\n{text}".encode("utf-8")).hexdigest()[:12]  # never one another rumour has
    return Folded([*spread(f"rumour:gm:{stem}", text, [place], source="game_master"),
                   counted(simulation, "rumour")])


__all__ = ["NEWS", "TOLD_AT_ONCE", "fold_rumour", "news_here", "rumours", "spread", "tell", "untold_at"]
