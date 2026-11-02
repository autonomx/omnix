"""Readings for tests (evolution roadmap EV-9): a line's slots, read from its words as the intent model is asked to.

The rules read a reading's ids and slots, never the player's words. A test about what a line asks for reads it here,
with the words reader the grammar uses (``tests/support/rpg_line_reader/line_words.py``), and hands the rule the slots it names.
"""
from __future__ import annotations

from typing import Any, Mapping

from tests.support.rpg_line_reader import line_words


def planned(simulation: Mapping[str, Any], speaker_id: str, text: str, **kwargs: Any):
    """The dialogue plan for ``text`` to ``speaker_id``, with the topics and step its words name."""
    from app.apps.rpg.rules.dialogue.plan import build_plan
    from app.apps.rpg.rules.quest.progress import accepted_step

    step = accepted_step(simulation, speaker_id, line_words.read_step(simulation, speaker_id, text))
    return build_plan(simulation, speaker_id, text, topics=line_words.read_topics(simulation, speaker_id, text),
                      step=step, **kwargs)


def answered(session: Mapping[str, Any], target_id: str, text: str):
    """The answer to ``text``, with the topics and step its words name to whoever answers it."""
    from app.apps.rpg.foundation.state import access as sections
    from app.apps.rpg.session.turn.dialogue import resolve_dialogue, speaker_for

    simulation = dict(sections.simulation_state_of(session) or {})
    speaker = speaker_for(simulation, dict(sections.runtime_state_of(session) or {}), target_id)
    return resolve_dialogue(session, target_id, text, topics=line_words.read_topics(simulation, speaker, text),
                            step=line_words.read_step(simulation, speaker, text))


def bought(simulation: Mapping[str, Any], text: str):
    """Buying what the words name, from whom, and how many."""
    from app.apps.rpg.rules.economy.trade import buy

    return buy(simulation, *line_words.read_buy(simulation, text))


def sold(simulation: Mapping[str, Any], text: str):
    """Selling what the words name, to whom."""
    from app.apps.rpg.rules.economy.trade import sell

    return sell(simulation, *line_words.read_sell(simulation, text))


def said_to(npc_id: str, simulation: Mapping[str, Any], text: str) -> dict[str, Any]:
    """A ``DialogueExchanged``'s fields for ``text`` said to ``npc_id``: its line and the step its words answer."""
    return {"npc_id": npc_id, "player_line": text, "step": line_words.read_step(simulation, npc_id, text)}


__all__ = ["answered", "bought", "planned", "said_to", "sold"]
