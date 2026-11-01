"""Step 2 (evolution roadmap EV-9; RQ-3.2): the intent call reads every typed line.

No code reads the player's words. One structured call returns ranked readings, each a family the pipeline runs and
what in the scene it is aimed at, with the typed slots the rules need (how many, how long, how to rest, the topics a
line asks a person about, the quest step it answers, and the rest of ``rules/intent/reading.ReadingSlots``); or, when
the line is unclear, the one question to ask. The planner keeps only what it can carry out: a family it runs, a target
that is really here of a kind that family takes, and each slot checked against the scene and the rules (an unknown
slot is dropped, never guessed). The best reading is planned; when two stay close, the turn asks which was meant; when
none is left, the turn is a free action (``act``: the attempt told, no rule's change). With no model, or none in time,
there is no reading, and only the cards the game offers run (RQ-8.8).
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Mapping

from pydantic import ValidationError

from app.apps.rpg.foundation.safe_values import safe_dict as _d, safe_list as _l, safe_str as _s
from app.apps.rpg.foundation.state import access as _sections
from app.apps.rpg.narration.world_data import RULE as WORLD_DATA_RULE, world_data
from app.apps.rpg.rules.contracts import CHECK_KINDS as _CHECK_KINDS
from app.apps.rpg.rules.intent.reading import STATUS_TOPICS, IntentCandidate, ReadingSlots, SceneView
from app.prompts import prompt_template

logger = logging.getLogger(__name__)
INTENT_TIMEOUT_SECONDS = 10.0
TRUSTED = 0.5  # a reading below this is no reading
CLOSE = 0.15  # two readings within this of each other: ask which was meant

# Each family the pipeline runs, what it means, and the kinds of thing it is aimed at ("" when at nothing).
FAMILIES: dict[str, tuple[str, frozenset[str]]] = {
    "look": ("look around, or at something", frozenset({"", "person", "creature", "item", "place"})),
    "move": ("go to a place", frozenset({"place"})),
    "talk": ("speak to someone, or ask them something", frozenset({"", "person"})),
    "buy": ("buy something on offer", frozenset({"", "offer", "item"})),
    "sell": ("sell something carried", frozenset({"item"})),
    "attack": ("attack someone or something", frozenset({"", "person", "creature"})),
    "flee": ("break away from a fight", frozenset({""})),
    "defend": ("guard in a fight; aimed at one of the party, guard them", frozenset({"", "person"})),
    "take": ("pick something up", frozenset({"item"})),
    "drop": ("put something carried down", frozenset({"item"})),
    "give": ("give something carried to someone here", frozenset({"item"})),
    "use_item": ("use something carried", frozenset({"", "item"})),
    "equip": ("wear or wield something carried", frozenset({"item"})),
    "unequip": ("take off something worn", frozenset({"item"})),
    "rest": ("rest or sleep", frozenset({""})),
    "wait": ("let time pass", frozenset({""})),
    "quest": ("take on a quest offered", frozenset({"quest"})),
    "practice": ("practise a skill", frozenset({"skill"})),
    "party": ("invite someone into the party, or part ways (parting)", frozenset({"person"})),
    "order": ("give a companion a standing order", frozenset({"person"})),
    "status": ("ask how the hero stands", frozenset({""})),
    "ability": ("use one of the hero's abilities", frozenset({"ability"})),
    "grow": ("make the level's choice that waits", frozenset({""})),
    "explore": ("search the area around for what is hidden, explore the land, go deeper in", frozenset({""})),
    "check": ("try something risky: persuade, intimidate, deceive, haggle, sneak, climb, pick a lock, recall "
              "lore, search, notice", frozenset({"", "person", "creature", "item", "place"})),
}
CHECK_KINDS = frozenset(_CHECK_KINDS)  # the checks the rules resolve (rules/checks.py)
# Readings of a line that asks or supposes rather than does: an answer, the hero's standing, a look at what is here.
_ASKING = frozenset({"talk", "status", "look"})
_PROMPT = prompt_template(
    "rpg.turn_intent.readings", "4",
    "Read what the player means, as up to three readings, most likely first. Each is one of FAMILIES and, when it is "
    "aimed at something, the id of a thing in SCENE (never one that is not listed). Reply with JSON only: "
    "{{\"readings\": [{{\"family\": \"...\", \"target_id\": \"...\", \"second_target_id\": \"...\", \"check\": \"...\", "
    "\"confidence\": 0.0, \"asks\": false, \"slots\": {{}}}}], \"question\": \"\"}}. "
    "second_target_id is the person here a thing is given to, the seller bought from, or the buyer sold to. "
    "asks is true when the line asks or supposes (\"what would happen if...\", \"can I...?\") rather than does. "
    "slots hold only what the line says: quantity (a number), everything (true: all of them), wait_minutes, or "
    "until_hour (0-23) with tomorrow, rest (while, sleep or camp), status (of STATUS_TOPICS), order (of ORDERS), "
    "parting (true: leaving the party), choice (of LEVEL_CHOICES), topics (the ids of what a line asks the person "
    "about: their topics in SCENE, or a place, group, person or thing in SCENE), step (from the person's steps in "
    "SCENE, only when the line plainly does what that step asks), and weakness (of the target's weaknesses in SCENE, "
    "when an attack uses it). When the line is unclear and no reading fits, "
    "question is the one short question to ask the player, and question_about the family it is about. Idioms and figures of speech mean what they mean "
    "(\"give it a rest\" is no rest; \"break a leg\" is no attack). Give no reading for what none of FAMILIES does (a "
    "song, a gesture, a thought). A refusal or a declined offer (\"no thanks\", \"not now\", \"forget it\") is talk, "
    "with the one who offered or is being talked with; so is a remark said aloud (\"I hate this weather\"). "
    + WORLD_DATA_RULE + "\nPLAYER: {v0}\nCONTEXT: ",
)


@dataclass(frozen=True)
class ModelReading:
    """What the intent call made of the line: the reading to plan, the two to ask between, or the question to ask."""

    reading: IntentCandidate | None = None
    between: tuple[IntentCandidate, IntentCandidate] | None = None
    question: str = ""
    question_about: str = ""  # the family the question is about (whom to attack, where to go), for its answers
    unavailable: bool = False  # no model, or none in time: only the cards run (RQ-8.8)


def _scene_rows(scene: SceneView) -> list[dict[str, Any]]:
    # A person's other names (what they do, what they are called) let the model read "the union leader" or "the
    # bartender" as the one meant; one present also says what a line may ask them about and the steps it may answer.
    rows = []
    for entity in scene.entities[:80]:
        row: dict[str, Any] = {"id": entity.entity_id, "kind": entity.kind,
                               "name": entity.names[0] if entity.names else entity.entity_id}
        if entity.kind == "person" and len(entity.names) > 1:
            row["also"] = list(entity.names[1:6])
        if entity.here:
            row["here"] = "yes"
        if entity.topics:
            row["topics"] = [{"id": topic, "about": about} for topic, about in entity.topics[:24]]
        if entity.steps:
            row["steps"] = [{"step": address, "asks": asks} for address, asks in entity.steps[:8]]
        if entity.weaknesses:
            row["weaknesses"] = [{"weakness": tag, "names": names} for tag, names in entity.weaknesses[:4]]
        rows.append(row)
    return rows


def _level_choices(simulation: Mapping[str, Any], document: Mapping[str, Any]) -> list[str]:
    """The choices a waiting level offers, as a reading names them (``rules/player/progression.choose``)."""
    from app.apps.rpg.rules.player.progression import ATTRIBUTES, _learnable

    player = _d(_sections.player_state_of(simulation))
    if int(player.get("level_choices_pending") or 0) <= 0:
        return []
    return [*(f"attribute:{name}" for name in ATTRIBUTES),
            *(f"ability:{_s(row.get('ability_id'))}" for row in _learnable(document)),
            *(f"skills:<one>,<other> of {', '.join(sorted(_d(player.get('skills'))))}",)]


def _parse(raw: str) -> tuple[list[dict[str, Any]], str, str]:
    match = re.search(r"\{.*\}", _s(raw), flags=re.DOTALL)
    try:
        payload = json.loads(match.group(0)) if match else {}
    except json.JSONDecodeError:
        return [], "", ""
    payload = _d(payload)
    about = _s(payload.get("question_about"))
    return ([_d(row) for row in _l(payload.get("readings"))][:3], _s(payload.get("question")).strip()[:200],
            about if about in FAMILIES else "")


def _slots(raw: Mapping[str, Any], *, target: str, scene: SceneView, choices: list[str] | None) -> ReadingSlots:
    """The slots a reading names that the scene and the rules can take; each other one is dropped."""
    from app.apps.rpg.rules.player.requests import ORDERS

    kept: dict[str, Any] = {}
    raw = {**raw, **({"status": [topic for topic in _l(raw.get("status")) if topic in STATUS_TOPICS]}
                     if "status" in raw else {})}
    for key, value in raw.items():
        try:
            ReadingSlots(**{key: value})
        except (ValidationError, TypeError):
            continue
        kept[key] = value
    if kept.get("order") and kept["order"] not in ORDERS:
        kept.pop("order")
    if kept.get("status"):
        kept["status"] = tuple(topic for topic in kept["status"] if topic in STATUS_TOPICS)
    if kept.get("choice") and choices is not None:  # else the level rule refuses what it does not offer
        kind, _, value = str(kept["choice"]).partition(":")
        offered = {choice.partition(":")[0] for choice in choices}
        if kind not in offered or (kind != "skills" and kept["choice"] not in choices):
            kept.pop("choice")
    person = next((entity for entity in scene.entities if entity.entity_id == target and entity.kind == "person"), None)
    asked_of = scene.entity(scene.focus_id) if person is None and scene.focus_id else person
    if kept.get("topics"):
        # Of what the person may be asked (never a secret), or anything the world names that anyone may know of.
        theirs = {topic for topic, _ in (asked_of.topics if asked_of else ())}
        known = {entity.entity_id for entity in scene.entities if entity.kind in {"place", "group", "person", "item"}}
        kept["topics"] = tuple(topic for topic in dict.fromkeys(kept["topics"]) if topic in theirs | known)
    if kept.get("step") and kept["step"] not in {address for address, _ in (asked_of.steps if asked_of else ())}:
        kept.pop("step")
    foe = scene.entity(target) if target else None
    if kept.get("weakness") and kept["weakness"] not in {tag for tag, _ in (foe.weaknesses if foe else ())}:
        kept.pop("weakness")  # one the target has, by the scene
    return ReadingSlots(**{key: value for key, value in kept.items() if value not in (None, "", ())})


def valid_readings(rows: list[dict[str, Any]], scene: SceneView, *,
                   choices: list[str] | None = None) -> list[IntentCandidate]:
    """The readings the planner can carry out, best first: a family it runs, aimed at a thing really in the scene of a
    kind that family takes, with the slots the rules can take."""
    kinds = {entity.entity_id: entity.kind for entity in scene.entities}
    here = {entity.entity_id for entity in scene.entities if entity.here}
    kept: list[IntentCandidate] = []
    for row in rows:
        family, target = _s(row.get("family")), _s(row.get("target_id"))
        if family not in FAMILIES:
            continue
        kind = kinds.get(target, "") if target else ""
        if target and FAMILIES[family][1] == {""}:  # a family aimed at nothing ("how do I stand on this quest?"): its
            target, kind = "", ""  # target is dropped, not the reading
        if target and target not in kinds or kind not in FAMILIES[family][1]:
            continue
        reason = "model_reading"
        if family == "check":
            check = _s(row.get("check"))
            if check not in CHECK_KINDS:
                continue
            reason = f"check:{check}"
        second = _s(row.get("second_target_id"))
        allowed = {"person", "creature"} if family == "ability" else {"person"}
        if second and (kinds.get(second) not in allowed or second not in here):
            second = ""  # a receiver, seller or buyer is someone here; an ability's, the foe it is aimed at
        try:
            confidence = max(0.0, min(1.0, float(row.get("confidence") or 0)))
        except (TypeError, ValueError):
            confidence = 0.0
        slots = _slots(_d(row.get("slots")), target=target, scene=scene,
                       choices=list(choices) if choices is not None else None)
        kept.append(IntentCandidate(family=family, target_id=target or None, target_kind=kind or None,  # type: ignore[arg-type]
                                    confidence=confidence, reason=reason, second_target_id=second or None,
                                    slots=slots, asks=row.get("asks") is True))
    return sorted(kept, key=lambda reading: -reading.confidence)


def answered(asked: list[IntentCandidate], scene: SceneView, *, choices: list[str] | None = None) -> IntentCandidate | None:
    """A line that asks or supposes, none of whose readings may be done ("what if I attacked the guide?", "who is the
    Archon?"): a question to whoever here can answer it, the one it names, the one being talked with, or the only
    person here. Its readings together say how sure the reading is that it asks; their targets and topics are what it
    asks about."""
    here = [entity.entity_id for entity in scene.of("person", here=True)]
    named = [reading.target_id for reading in asked if reading.target_id in here]
    answerer = next(iter(named), "") or (scene.focus_id if scene.focus_id in here else "") or (
        here[0] if len(here) == 1 else "")
    confidence = min(1.0, sum(reading.confidence for reading in asked))
    if not answerer or confidence < TRUSTED:
        return None
    about = [topic for reading in asked for topic in (*reading.slots.topics, reading.target_id or "")
             if topic and topic != answerer]
    return IntentCandidate(family="talk", target_id=answerer, target_kind="person", confidence=confidence,
                           reason="model_reading", asks=True,
                           slots=_slots({"topics": about} if about else {}, target=answerer, scene=scene,
                                        choices=choices))


def decide(readings: list[IntentCandidate]) -> ModelReading:
    """The reading to plan; two close, different readings to ask between; or nothing (a free action)."""
    trusted = [reading for reading in readings if reading.confidence >= TRUSTED]
    if not trusted:
        return ModelReading()
    first = trusted[0]
    second = next((reading for reading in trusted[1:]
                   if (reading.family, reading.target_id) != (first.family, first.target_id)), None)
    if second is not None and first.confidence - second.confidence < CLOSE:
        return ModelReading(between=(first, second))
    return ModelReading(reading=first)


def read_with_model(document: Mapping[str, Any], scene: SceneView, text: str) -> ModelReading:
    """The intent call's reading of ``text`` in ``scene``; no reading without a model, or past its time."""
    from app.apps.rpg.foundation.llm_app_gateway import build_app_llm_gateway
    from app.apps.rpg.rules.player.requests import ORDERS

    gateway = build_app_llm_gateway()
    if gateway is None:
        return ModelReading(unavailable=True)
    simulation = _d(_sections.simulation_state_of(document))
    choices = _level_choices(simulation, document)
    context = {"FAMILIES": {family: meaning for family, (meaning, _) in FAMILIES.items()}, "SCENE": _scene_rows(scene),
               "STATUS_TOPICS": list(STATUS_TOPICS), "ORDERS": dict(ORDERS),
               **({"LEVEL_CHOICES": choices} if choices else {}),
               **({"talking_with": scene.focus_id} if scene.focus_id else {}),
               "location": _s(_d(_sections.player_state_of(simulation)).get("location_id"))}
    prompt = _PROMPT.format(v0=text[:500]) + world_data(context)
    try:
        raw = gateway.generate(prompt, timeout_s=INTENT_TIMEOUT_SECONDS,
                               provider_options={"temperature": 0.0, "max_tokens": 400,
                                                 "chat_template_kwargs": {"enable_thinking": False}})
    except Exception:
        logger.warning("rpg_turn_intent_failed", exc_info=True)
        return ModelReading(unavailable=True)
    rows, question, about = _parse(_s(raw))
    readings = valid_readings(rows, scene, choices=choices)
    # Asked or supposed, not done: an answer, the hero's standing, or a look at something here; a question about a
    # place elsewhere ("what is the pass like?") is no look at it, and no deed is done.
    # Asked of someone not here, the line is a question to someone who is (``answered``).
    here = {entity.entity_id for entity in scene.entities if entity.here}
    # The line asks when its best reading does: a lower one that would do the deed is not done either.
    line_asks = bool(readings) and readings[0].asks
    asked = [reading for reading in readings if reading.asks or line_asks]
    readings = [reading for reading in readings if not (reading.asks or line_asks) or (
        reading.family in _ASKING and (reading.family == "status" or not reading.target_id or reading.target_id in here))]
    decided = decide(readings)
    if decided.reading is None and decided.between is None:
        answer = answered(asked, scene, choices=choices) if asked else None
        if answer is not None:
            return ModelReading(reading=answer)
    if decided.reading is None and decided.between is None and question:
        return ModelReading(question=question, question_about=about)
    return decided


__all__ = ["CLOSE", "FAMILIES", "TRUSTED", "ModelReading", "answered", "decide", "read_with_model", "valid_readings"]
