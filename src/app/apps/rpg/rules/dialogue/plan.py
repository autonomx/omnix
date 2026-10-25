"""The dialogue plan (RQ-2.2; docs/rpg/design/dialogue.md): what the person spoken to may say this turn.

A pure rule. It reads the speaker from the world model, how they stand with the hero, the world's knowledge, the
quests on offer and the speaker's wares, and decides what they reveal, offer and keep back. The model phrases the
line from the plan; when it cannot, ``fallback_line`` says what the plan holds.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Mapping

from app.apps.rpg.foundation.safe_values import safe_dict as _d, safe_list as _l, safe_str as _s
from app.apps.rpg.foundation.state.changes import KnowledgeShared, QuestOffered, StateChange
from app.apps.rpg.rules.economy.trade import stock_left

_WORD = re.compile(r"[a-z0-9']+")
_STOP = frozenset("a an the and or of to in on at for with about from is are was were be you your me my i we "
                  "what who where when why how do does did can could would will tell ask know heard any some this "
                  "that there here it its".split())
_WORK = re.compile(r"\b(work|job|jobs|task|tasks|help|quest|quests|errand|hire|bounty|contract)\b")
_WARES = re.compile(r"\b(sell|selling|wares|buy|price|prices|cost|costs|goods|offer|stock|room|rooms|food|drink)\b")
FRIENDLY_TRUST = 50


@dataclass(frozen=True)
class DialoguePlan:
    speaker_id: str
    speaker_name: str
    role: str = ""
    stance: str = "neutral"  # friendly, neutral, wary
    voice: str = ""
    personality: tuple[str, ...] = ()
    goals: tuple[str, ...] = ()
    background: str = ""
    reveals: tuple[str, ...] = ()  # fact texts shared this turn
    revealed_ids: tuple[str, ...] = ()
    for_a_price: tuple[str, ...] = ()  # "what the old road hides, for 2 silver"
    held_back: int = 0  # facts they will share once they trust the hero more
    secrets: tuple[str, ...] = ()  # never in the line
    quest_offer: dict[str, str] = field(default_factory=dict)
    wares: tuple[str, ...] = ()  # "Healing Potion for 3 silver"
    ware_names: tuple[str, ...] = ()  # each named in the line, or the line lists them itself
    player_said: str = ""

    def context(self) -> dict[str, Any]:
        """The plan as the line's writer is told it (secrets included, as what must not be said)."""
        return {key: value for key, value in {
            "speaker": self.speaker_name, "role": self.role, "stance": self.stance, "voice": self.voice,
            "personality": list(self.personality), "goals": list(self.goals), "background": self.background,
            "may_reveal": list(self.reveals), "offers_to_tell_for_a_price": list(self.for_a_price),
            "keeps_back_until_trusted": self.held_back, "offers_quest": self.quest_offer,
            "wares": list(self.wares), "must_never_reveal": list(self.secrets),
        }.items() if value}

    def fallback_line(self) -> str:
        """A true line from the plan alone, for when the model cannot write one."""
        if self.quest_offer:
            objective = self.quest_offer.get("objective")
            return (f"There is something you could do: {self.quest_offer.get('title')}."
                    + (f" {objective}." if objective else ""))
        if self.reveals:
            return self.reveals[0]
        if self.wares:
            return f"I have {', '.join(self.wares)}."
        if self.for_a_price:
            return f"I could tell you {self.for_a_price[0]}."
        return ""

    def fallback_beat(self) -> str:
        return f"{self.speaker_name} considers the question and says nothing useful."


def _words(text: str) -> set[str]:
    return {word for word in _WORD.findall(text.casefold()) if word not in _STOP and len(word) > 2}


def _stem(word: str) -> str:
    """``rooms`` and ``room`` are one word to a buyer."""
    return word[:-1] if word.endswith("s") and len(word) > 3 else word


def _trust(simulation: Mapping[str, Any], npc_id: str) -> int:
    for row in _l(_d(_d(simulation.get("player_state")).get("party_state")).get("companions")):
        if _d(row).get("npc_id") == npc_id:
            return max(FRIENDLY_TRUST, int(_d(row).get("trust") or FRIENDLY_TRUST))
    relation = _d(_d(simulation.get("relationship_state")).get(npc_id))
    return int(relation.get("trust") or relation.get("score") or 0)


def _facts(world: Mapping[str, Any], npc_id: str) -> list[dict[str, Any]]:
    for entry in _l(world.get("knowledge")):
        if _s(_d(entry).get("npc_id")) == npc_id:
            return [_d(fact) for fact in _l(_d(entry).get("facts"))]
    return []


def _price_text(price: Mapping[str, Any]) -> str:
    return ", ".join(f"{int(price.get(coin) or 0)} {coin}" for coin in ("gold", "silver", "copper")
                     if int(price.get(coin) or 0)) or "a price"


def _goals(world: Mapping[str, Any], npc_id: str, asked: set[str]) -> list[dict[str, Any]]:
    """What the speaker is after (the world's routines author it, routines.md): the goals the hero's words touch
    first, then the most pressing."""
    goals = [_d(goal) for routine in _l(world.get("routines")) if _s(_d(routine).get("npc_id")) == npc_id
             for goal in _l(_d(routine).get("goals")) if _s(_d(goal).get("summary"))]

    def touched(goal: Mapping[str, Any]) -> bool:
        return bool(asked & _goal_words(goal))

    return sorted(goals, key=lambda goal: (not touched(goal), -int(goal.get("priority") or 1)))


def _stemmed(words: set[str]) -> set[str]:
    return words | {_stem(word) for word in words}


def _goal_words(goal: Mapping[str, Any]) -> set[str]:
    return _stemmed({_s(topic).casefold() for topic in _l(goal.get("topics"))} | _words(_s(goal.get("summary"))))


def build_plan(simulation: Mapping[str, Any], speaker_id: str, text: str) -> DialoguePlan | None:
    """The plan for ``speaker_id``'s answer to ``text``; ``None`` when the world does not know them."""
    world = _d(simulation.get("world_model"))
    npc = {**_d(_d(simulation.get("npc_index")).get(speaker_id)), **_d(_d(world.get("npcs")).get(speaker_id))}
    if not npc:
        return None
    name = _s(npc.get("name")) or speaker_id
    trust = _trust(simulation, speaker_id)
    stance = "friendly" if trust >= FRIENDLY_TRUST else "wary" if trust < 0 else "neutral"
    asked = _words(text) | {_stem(word) for word in _words(text)}
    known = set(_l(_d(_d(simulation.get("dialogue")).get("known_facts")).get(speaker_id)))
    reveals, revealed_ids, priced, held = [], [], [], 0
    for fact in _facts(world, speaker_id):
        topics = {topic.casefold() for topic in _l(fact.get("topics"))} | _words(_s(fact.get("text")))
        if not asked & topics:
            continue
        shares = _s(fact.get("shares")) or "freely"
        if shares == "freely" or (shares == "when_trusted" and trust >= int(fact.get("trust_needed") or 0)):
            reveals.append(_s(fact.get("text")))
            if _s(fact.get("fact_id")) and _s(fact.get("fact_id")) not in known:
                revealed_ids.append(_s(fact.get("fact_id")))
        elif shares == "for_price":
            priced.append(f"{', '.join(sorted(asked & topics))} for {_price_text(_d(fact.get('price')))}")
        elif shares == "when_trusted":
            held += 1
    goals = _goals(world, speaker_id, asked)
    pressing = _goal_words(goals[0]) if goals else set()
    quest_offer: dict[str, str] = {}
    here = _s(npc.get("location_id"))
    offerable = []
    for quest in _l(_d(simulation.get("quest_state")).get("quests")):
        quest = _d(quest)
        places = [_s(place) for place in _l(quest.get("locations"))]
        giver = _s(quest.get("giver_id") or quest.get("offered_by"))
        if quest.get("status") == "available" and (giver == speaker_id or (not giver and here in places)):
            about = _stemmed(_words(f"{_s(quest.get('title'))} {_s(quest.get('objective'))}"))
            offerable.append((len(about & asked), len(about & pressing), quest))
    # Asked for work, or about what one of their goals is after and a quest of theirs answers: the quest closest to
    # the words, then to the goal they are most after (routines.md), offered.
    on_a_goal = any(asked & _goal_words(goal) for goal in goals) and any(said for said, _, _ in offerable)
    if offerable and (_WORK.search(text.casefold()) or on_a_goal):
        _, _, quest = max(offerable, key=lambda row: (row[0], row[1]))
        quest_offer = {"quest_id": _s(quest.get("quest_id") or quest.get("id")), "title": _s(quest.get("title")),
                       "objective": _s(quest.get("objective"))}
    on_sale: list[dict[str, Any]] = []
    if _WARES.search(text.casefold()):
        on_sale = [_d(offer) for offer in _l(_d(world.get("offers")).get(speaker_id))
                   if _s(_d(offer).get("label")) and stock_left(simulation, _d(offer)) != 0]
        # Asked about some of them ("what does a room cost"), those; asked what they sell, all of them.
        named = [offer for offer in on_sale if asked & {_stem(word) for word in _words(_s(offer.get("label")))}]
        on_sale = named or on_sale
    return DialoguePlan(
        speaker_id=speaker_id, speaker_name=name, role=_s(npc.get("role")), stance=stance,
        voice=_s(npc.get("speech_style")), personality=tuple(_s(trait) for trait in _l(npc.get("personality"))),
        goals=tuple(dict.fromkeys([*(_s(goal.get("summary")) for goal in goals), *(_s(goal) for goal in _l(npc.get("goals")))])),
        background=_s(npc.get("description")),
        reveals=tuple(reveals), revealed_ids=tuple(revealed_ids), for_a_price=tuple(priced), held_back=held,
        secrets=tuple(_s(secret) for secret in _l(npc.get("secrets"))), quest_offer=quest_offer,
        wares=tuple(f"{_s(offer.get('label'))} for {_price_text(_d(offer.get('price')))}" for offer in on_sale),
        ware_names=tuple(_s(offer.get("label")) for offer in on_sale),
        player_said=text,
    )


def plan_changes(plan: DialoguePlan) -> list[StateChange]:
    """What the plan makes real before the commit: what is now known, and what is offered."""
    changes: list[StateChange] = []
    changes.extend(KnowledgeShared(npc_id=plan.speaker_id, fact_id=fact_id) for fact_id in plan.revealed_ids)
    if plan.quest_offer.get("quest_id"):
        changes.append(QuestOffered(quest_id=plan.quest_offer["quest_id"], npc_id=plan.speaker_id))
    return changes


def line_keeps_the_plan(plan: DialoguePlan, line: str) -> bool:
    """The written line may be shown: it is not empty, names each ware asked about (by a word of its name: the
    prices are the game's, so a line that leaves one out gives way to the plan's own list), and repeats none of
    the speaker's secrets."""
    lowered = line.casefold()
    said = {_stem(word) for word in _words(line)}
    if not lowered.strip() or any(not said & {_stem(word) for word in _words(name)} for name in plan.ware_names):
        return False
    for secret in plan.secrets:
        words = _words(secret)
        if secret.casefold() in lowered or (len(words) >= 4 and len(words & _words(line)) >= max(4, len(words) * 2 // 3)):
            return False
    return True


__all__ = ["DialoguePlan", "build_plan", "line_keeps_the_plan", "plan_changes"]
