"""The scripted reader: what the intent model answers in tests (evolution roadmap EV-9).

The engine sends every typed line to the intent call. In tests a scripted model answers it, and this is how it reads
the line: the command grammar the game used before EV-9 (``grammar.py``), with the words of each slot read as the
rules once read them (``line_words.py``), so a scenario plays as it did. It answers in the intent call's own shape (a
reading with its ids and slots, or the question to ask), and with nothing where the grammar read nothing it would
act on: the model's fallback, scripted per test.
"""
from __future__ import annotations

import re
from typing import Any, Mapping

from app.apps.rpg.foundation.safe_values import safe_dict as _d, safe_str as _s
from app.apps.rpg.foundation.state import access as sections
from app.apps.rpg.rules.ability_use import known as known_abilities
from app.apps.rpg.rules.intent.reading import NO_SLOTS, IntentCandidate
from app.apps.rpg.session.turn.planning import PlannedAction, plan_action
from tests.support.rpg_line_reader.grammar import parse_command
from tests.support.rpg_line_reader.line_words import with_slots

SKIP_CONFIDENCE = 0.8  # the grammar's own bar, below which the game asked the model
_EXPLORE = re.compile(r"(?i)^\s*(explore|search (the area|around|the hills|the land|the woods)|go deeper"
                      r"|look for (a|the|any) (cave|way|path|ruin))")
CLARIFICATIONS = {
    "give_without_item": "What do you want to give, and to whom?",
    "attack_without_target": "Who or what do you want to attack?",
    "move_without_place": "Where do you want to go?",
    "vague_reference": "Who or what do you mean?",
    "pronoun_without_antecedent": "Who or what do you mean?",
    "speech_without_listener": "Who are you speaking to?",
}
# Readings the grammar planned only above its bar (out of a fight).
_GATED = frozenset({"look", "inspect", "decline", "ask", "move", "use_item", "drop", "take", "equip", "unequip", "give",
                    "quest", "practice", "status", "party", "order", "talk", "rest", "wait"})
# A planned mechanic, as the intent call names its family.
_FAMILY = {"travel": "move", "talk": "talk", "look": "look", "grow": "grow", "check": "check", "ability": "ability",
           "quest": "quest", "practice": "practice", "status": "status", "party": "party", "order": "order",
           "rest": "rest", "wait": "wait", "give": "give", "use_item": "use_item", "drop": "drop", "take": "take",
           "equip": "equip", "unequip": "unequip"}
_FIGHT = {"attack": "attack", "flee": "flee", "defend": "defend"}


def scene_of(document: Mapping[str, Any]):
    from app.apps.rpg.session.turn.scene import scene_view

    simulation = _d(sections.simulation_state_of(document))
    abilities = tuple((_s(row.get("ability_id")), _s(row.get("name"))) for row in known_abilities(document))
    return scene_view(simulation, _d(sections.runtime_state_of(document)), abilities)


def grammar_plan(document: Mapping[str, Any], text: str) -> tuple[IntentCandidate, PlannedAction | None, str]:
    """The grammar's reading, what the game planned of it before EV-9 (``None``: it asked the model), and the question
    it asked when the line was unclear."""
    simulation = _d(sections.simulation_state_of(document))
    fighting = _d(sections.combat_state_of(simulation)).get("active") is True
    reading = parse_command(text, scene_of(document))
    if reading.family == "clarify" and reading.confidence >= SKIP_CONFIDENCE and reading.reason in CLARIFICATIONS:
        if not (fighting and reading.reason == "attack_without_target"):
            return reading, None, CLARIFICATIONS[reading.reason]
    if fighting and reading.reason == "attack_without_target":
        return reading, PlannedAction(mechanic="fight", ticks=0, reason="attack"), ""
    if reading.family == "clarify":
        return reading, None, ""
    gated = (not fighting or reading.family == "status") and reading.family in _GATED
    if gated and reading.confidence < SKIP_CONFIDENCE:
        return reading, None, ""
    return reading, plan_action(reading, fighting=fighting), ""


def _family(reading: IntentCandidate, planned: PlannedAction) -> str:
    if planned.mechanic == "trade":
        return planned.reason
    if planned.mechanic == "fight":
        if planned.reason in _FIGHT:
            return _FIGHT[planned.reason]
        if planned.reason in {"sneak", "persuade", "intimidate"}:
            return "check"
        return {"inspect": "look", "ask": "talk", "decline": "talk"}.get(reading.family, reading.family)
    return _FAMILY.get(planned.mechanic, "")


def read_line(document: Mapping[str, Any], text: str) -> dict[str, Any]:
    """The intent call's answer to ``text`` in the campaign ``document``: the grammar's planned reading, with its slots;
    its question; or no reading, where the game would have asked the model."""
    from app.apps.rpg.session.turn.dialogue import speaker_for

    if _EXPLORE.search(text):  # a search of the area for what is hidden (EV-10)
        return {"readings": [{"family": "explore", "target_id": "", "second_target_id": "", "confidence": 0.95,
                              "slots": {}}]}
    reading, planned, question = grammar_plan(document, text)
    if question:
        about = {"give_without_item": "give", "attack_without_target": "attack",
                 "move_without_place": "move"}.get(reading.reason, "talk")
        return {"readings": [], "question": question, "question_about": about}
    if planned is None or planned.mechanic in {"clarify", "act"}:
        return {"readings": []}
    family = _family(reading, planned)
    if not family:
        return {"readings": []}
    target = planned.target_id or ("" if planned.mechanic in {"talk", "trade"} else _s(reading.target_id))
    speaker = ""
    if family == "talk":
        simulation, runtime = _d(sections.simulation_state_of(document)), _d(sections.runtime_state_of(document))
        speaker = speaker_for(simulation, runtime, target)
    slotted = with_slots(reading, text, document, speaker_id=speaker)
    if family in {"buy", "sell"}:
        target = _s(slotted.target_id)
    check = (planned.reason if planned.mechanic == "check" else
             planned.reason if planned.mechanic == "fight" and family == "check" else
             reading.reason.removeprefix("check:") if family == "check" else "")
    second = planned.second_target_id or (_s(slotted.second_target_id) if family in {"buy", "sell", "give"} else "")
    slots = slotted.slots.model_dump(mode="json", exclude_defaults=True) if slotted.slots != NO_SLOTS else {}
    if family == "party" and planned.reason == "party_leave":
        slots["parting"] = True
    return {"readings": [{"family": family, "target_id": target, "second_target_id": second,
                          **({"check": check} if check else {}), "confidence": 0.95, "slots": slots}]}


__all__ = ["CLARIFICATIONS", "SKIP_CONFIDENCE", "grammar_plan", "read_line", "scene_of"]
