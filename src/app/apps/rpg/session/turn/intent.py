"""Step 2, when the grammar is not sure (RQ-3.2; roadmap §4.6): one model call reads what the player means.

The command grammar reads unambiguous commands against the scene. For anything it cannot read with confidence, one
structured call returns ranked readings, each a family the pipeline runs and what in the scene it is aimed at. The
planner keeps only readings it can carry out: a family it knows, a target that is really here, of a kind that
family takes. The best is planned like the grammar's; when two stay close, the turn asks which was meant; when none
is left, the turn is a free action (``act``: the attempt told, no rule's change). With no model, or none in time,
there is no reading: only what the grammar read runs (RQ-8.8).
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Mapping

from app.apps.rpg.foundation.safe_values import safe_dict as _d, safe_list as _l, safe_str as _s
from app.apps.rpg.narration.world_data import RULE as WORLD_DATA_RULE, world_data
from app.apps.rpg.rules.intent.grammar import IntentCandidate, SceneView, asked_not_done, hypothetical
from app.prompts import prompt_template
from app.apps.rpg.foundation.state import access as _sections

logger = logging.getLogger(__name__)
INTENT_TIMEOUT_SECONDS = 10.0
TRUSTED = 0.5  # a reading below this is no reading
CLOSE = 0.15  # two readings within this of each other: ask which was meant

# Each family the pipeline runs, what it means, and the kinds of thing it is aimed at ("" when at nothing).
FAMILIES: dict[str, tuple[str, frozenset[str]]] = {
    "look": ("look around, or at something", frozenset({"", "person", "creature", "item", "place"})),
    "move": ("go to a place", frozenset({"place"})),
    "talk": ("speak to someone", frozenset({"person"})),
    "buy": ("buy something on offer", frozenset({"offer", "item"})),
    "sell": ("sell something carried", frozenset({"item"})),
    "attack": ("attack someone or something", frozenset({"person", "creature"})),
    "flee": ("break away from a fight", frozenset({""})),
    "defend": ("guard in a fight", frozenset({""})),
    "take": ("pick something up", frozenset({"item"})),
    "drop": ("put something carried down", frozenset({"item"})),
    "use_item": ("use something carried", frozenset({"item"})),
    "equip": ("wear or wield something carried", frozenset({"item"})),
    "unequip": ("take off something worn", frozenset({"item"})),
    "rest": ("rest or sleep", frozenset({""})),
    "wait": ("let time pass", frozenset({""})),
    "quest": ("take on a quest offered", frozenset({"quest"})),
    "practice": ("practise a skill", frozenset({"skill"})),
    "party": ("invite someone into the party, or part ways", frozenset({"person"})),
    "status": ("ask how the hero stands", frozenset({""})),
    "ability": ("use one of the hero's abilities", frozenset({"ability"})),
    "check": ("try something risky: persuade, intimidate, deceive, haggle, sneak, climb, pick a lock, recall "
              "lore, search, notice", frozenset({"", "person", "creature", "item", "place"})),
}
CHECK_KINDS = frozenset({"persuade", "intimidate", "deceive", "haggle", "sneak", "climb", "pick_lock",
                         "recall_lore", "search", "notice"})
_PROMPT = prompt_template(
    "rpg.turn_intent.readings", "1",
    "Read what the player means, as up to three readings, most likely first. Each is one of FAMILIES and, when it is "
    "aimed at something, the id of a thing in SCENE (never one that is not listed). A check names its kind. Reply "
    "with JSON only: {{\"readings\": [{{\"family\": \"...\", \"target_id\": \"...\", \"check\": \"...\", "
    "\"confidence\": 0.0}}]}}. Give no reading for what none of FAMILIES does (a song, a gesture, a thought). "
    + WORLD_DATA_RULE + "\nPLAYER: {v0}\nCONTEXT: ",
)


@dataclass(frozen=True)
class ModelReading:
    """What the intent call made of the command: the reading to plan, or the two to ask between."""

    reading: IntentCandidate | None = None
    between: tuple[IntentCandidate, IntentCandidate] | None = None
    unavailable: bool = False  # no model, or none in time: only what the grammar read runs (RQ-8.8)


def _scene_rows(scene: SceneView) -> list[dict[str, str]]:
    # A person's other names (what they do, what they are called) let the model read "the union leader" or "the
    # bartender" as the one meant.
    return [{"id": entity.entity_id, "kind": entity.kind, "name": entity.names[0] if entity.names else entity.entity_id,
             **({"also": list(entity.names[1:6])} if entity.kind == "person" and len(entity.names) > 1 else {}),
             **({"here": "yes"} if entity.here else {})} for entity in scene.entities[:80]]


def _parse(raw: str) -> list[dict[str, Any]]:
    match = re.search(r"\{.*\}", _s(raw), flags=re.DOTALL)
    try:
        payload = json.loads(match.group(0)) if match else {}
    except json.JSONDecodeError:
        return []
    return [_d(row) for row in _l(_d(payload).get("readings"))][:3]


def valid_readings(rows: list[dict[str, Any]], scene: SceneView) -> list[IntentCandidate]:
    """The readings the planner can carry out, best first: a family it runs, aimed at a thing really in the scene of a
    kind that family takes."""
    kinds = {entity.entity_id: entity.kind for entity in scene.entities}
    kept: list[IntentCandidate] = []
    for row in rows:
        family, target = _s(row.get("family")), _s(row.get("target_id"))
        if family not in FAMILIES:
            continue
        kind = kinds.get(target, "") if target else ""
        if target and target not in kinds or kind not in FAMILIES[family][1]:
            continue
        reason = "model_reading"
        if family == "check":
            check = _s(row.get("check"))
            if check not in CHECK_KINDS:
                continue
            reason = f"check:{check}"
        try:
            confidence = max(0.0, min(1.0, float(row.get("confidence") or 0)))
        except (TypeError, ValueError):
            confidence = 0.0
        kept.append(IntentCandidate(family=family, target_id=target or None, target_kind=kind or None,  # type: ignore[arg-type]
                                    confidence=confidence, reason=reason))
    return sorted(kept, key=lambda reading: -reading.confidence)


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


def read_with_model(simulation: Mapping[str, Any], scene: SceneView, text: str) -> ModelReading:
    """The intent call's reading of ``text`` in ``scene``; no reading without a model, or past its time."""
    from app.apps.rpg.foundation.llm_app_gateway import build_app_llm_gateway

    gateway = build_app_llm_gateway()
    if gateway is None:
        return ModelReading(unavailable=True)
    context = {"FAMILIES": {family: meaning for family, (meaning, _) in FAMILIES.items()}, "SCENE": _scene_rows(scene),
               "location": _s(_d(_sections.player_state_of(simulation)).get("location_id"))}
    prompt = _PROMPT.format(v0=text[:500]) + world_data(context)
    try:
        raw = gateway.generate(prompt, timeout_s=INTENT_TIMEOUT_SECONDS,
                               provider_options={"temperature": 0.0, "max_tokens": 200,
                                                 "chat_template_kwargs": {"enable_thinking": False}})
    except Exception:
        logger.warning("rpg_turn_intent_failed", exc_info=True)
        return ModelReading(unavailable=True)
    readings = valid_readings(_parse(_s(raw)), scene)
    # What would happen if..., what it costs, whether to: asked, never done, whatever the model read.
    if hypothetical(text) or asked_not_done(text):
        readings = [reading for reading in readings if reading.family in {"talk", "look", "status"}]
    return decide(readings)


__all__ = ["CLOSE", "FAMILIES", "TRUSTED", "ModelReading", "decide", "read_with_model", "valid_readings"]
