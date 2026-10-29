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
from app.apps.rpg.foundation.state.changes import (
    DialogueExchanged,
    KnowledgeShared,
    QuestOffered,
    QuestStatusChanged,
    QuestStepCompleted,
    StateChange,
)
from app.apps.rpg.rules import routines
from app.apps.rpg.rules.economy.trade import coins, price_of, stock_left
from app.apps.rpg.rules.secrets import meaning_words as _words, names_a_secret as _names_a_secret, sayable
from app.apps.rpg.rules.wording import in_sentence
from app.apps.rpg.foundation.state import access as _sections

_WORK = re.compile(r"\b(work|jobs?|tasks?|help|quests?|errands?|hire|bount(y|ies)|contracts?|need (of|from) me|"
                   r"anything i can do)\b")
# Someone whose work is handing out work (a guild's registrar, a quartermaster, a bounty clerk): they offer a quest
# no one else gave, wherever it is (the playtest: the Wayfarers' Guild's registrar had no contract to offer).
_GIVES_WORK = re.compile(r"\b(guild|registrar|registry|contracts?|bount(y|ies)|quest|notice|clerk|quartermaster|"
                         r"broker|mercenar(y|ies)|wayfarer)\b")
_DEFEAT = re.compile(r"\b(defeat|slay|kill|hunt|drive off|destroy)\b")
_WARES = re.compile(r"\b(sell|selling|sale|wares|buy|price|prices|cost|costs|goods|offer|stock|shop|merchandise|room|rooms|"
                    r"food|drink)\b")
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
    hero_quests: tuple[dict[str, Any], ...] = ()  # the hero's quests they bear on, and where each goes on
    offered_rows: dict[str, dict[str, Any]] = field(default_factory=dict)  # an offer's row, when the log has none
    common_knowledge: tuple[dict[str, Any], ...] = ()  # what anyone here may know of the places and people asked of
    settled_now: tuple[dict[str, Any], ...] = ()  # the quest steps the hero's words to them do, as they are said
    hero: dict[str, str] = field(default_factory=dict)  # the hero's name and pronouns (the playtest: "lass")
    wares: tuple[str, ...] = ()  # "Healing Potion for 3 silver"
    ware_names: tuple[str, ...] = ()  # each named in the line, or the line lists them itself
    player_said: str = ""

    def context(self) -> dict[str, Any]:
        """The plan as the line's writer is told it. The speaker's secrets are not in it: the model cannot say what it
        never sees, so the line can be shown as it is written (roadmap §7 Q-12); ``line_keeps_the_plan`` still checks
        the written line against them."""
        return {key: value for key, value in {
            "speaker": self.speaker_name, "role": self.role, "stance": self.stance, "voice": self.voice,
            "hero": dict(self.hero),
            "personality": list(self.personality), "goals": list(self.goals), "background": self.background,
            "may_reveal": list(self.reveals), "offers_to_tell_for_a_price": list(self.for_a_price),
            "keeps_back_until_trusted": self.held_back, "offers_quest": self.quest_offer,
            "heros_quests": [dict(quest) for quest in self.hero_quests],
            "what_these_words_do": [dict(step) for step in self.settled_now],
            "common_knowledge": [dict(known) for known in self.common_knowledge],
            "wares": list(self.wares),
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




def _stem(word: str) -> str:
    """``rooms`` and ``room`` are one word to a buyer."""
    return word[:-1] if word.endswith("s") and len(word) > 3 else word


def _trust(simulation: Mapping[str, Any], npc_id: str) -> int:
    for row in _l(_d(_sections.party_state_of(_d(_sections.player_state_of(simulation)))).get("companions")):
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


def _common_knowledge(world: Mapping[str, Any], text: str, speaker_id: str) -> tuple[dict[str, Any], ...]:
    """What anyone here may know of the places and people the player names: a place's own description and who lives
    there; a person's calling and where they are found (the playtest: Liora, asked about the Moonroot Ruins, knew
    "not much beyond the name"). Never a secret: only what the world states openly."""
    places = _d(world.get("locations"))
    people = _d(world.get("npcs"))

    def named(*names: str, as_written: bool = False) -> bool:
        """Whether the words name one of ``names`` as whole words; ``as_written``: in its capitals (a first name
        alone: "Will you help?" names no Will, "a hopeful look" no Hope)."""
        return any(len(name) > 3 and re.search(
            (r"(?<![.!?]\s)(?<!^)" if as_written else "") + rf"(?<![\w']){re.escape(name)}(?![\w'])", text.strip(),
            flags=0 if as_written else re.IGNORECASE) for name in names if name)

    known: list[dict[str, Any]] = []
    for place_id, place in places.items():
        place = _d(place)
        if not named(_s(place.get("name")), *(_s(alias) for alias in _l(place.get("aliases")))):
            continue
        living = [f"{_s(_d(person).get('name'))}, {_s(_d(person).get('role'))}".strip(", ")
                  for person in people.values() if _s(_d(person).get("location_id")) == place_id]
        known.append({"place": _s(place.get("name")), "is": _s(place.get("description")),
                      **({"who_is_there": living[:4]} if living else {})})
    for group in _d(world.get("groups")).values():  # a faction, a union, a network the world names
        group = _d(group)
        if named(_s(group.get("name")), *_s(group.get("name")).split()[-1:]) and _s(group.get("summary")):
            known.append({"group": _s(group.get("name")), "is": _s(group.get("summary"))})
    for person_id, person in people.items():
        person = _d(person)
        full = _s(person.get("name"))
        if person_id == speaker_id or not (named(full) or named(*full.split()[:1], as_written=True)):
            continue
        found = _s(_d(places.get(_s(person.get("location_id")))).get("name"))
        known.append({"person": _s(person.get("name")), "is": _s(person.get("role")),
                      **({"found_at": found} if found else {})})
    return tuple(known[:3])


def _by_road(world: Mapping[str, Any], start: str) -> list[str]:
    """The world's places, nearest first by its roads from ``start`` (then those no road reaches)."""
    neighbours: dict[str, list[str]] = {}
    for route in _l(world.get("routes")):
        origin, target = _s(_d(route).get("from")), _s(_d(route).get("to"))
        neighbours.setdefault(origin, []).append(target)
        neighbours.setdefault(target, []).append(origin)
    order, queue = [start], [start]
    while queue:
        for place in neighbours.get(queue.pop(0), ()):
            if place not in order:
                order.append(place)
                queue.append(place)
    return [*order[1:], *(place for place in _d(world.get("locations")) if place not in order)]


def _charged(simulation: Mapping[str, Any], world: Mapping[str, Any], speaker_id: str, here: str,
             offer: Mapping[str, Any]) -> str:
    """An offer's price as the trade rule would charge it now (the playtest: Brindle said a potion was 3 silver, and
    the roads' fifth made it 3 silver 6 copper at the counter)."""
    provider = _d(_d(world.get("providers")).get(speaker_id)) or {"provider_id": speaker_id, "location_id": here}
    return coins(price_of(simulation, provider, offer)[0])


def _step_places(simulation: Mapping[str, Any], world: Mapping[str, Any], quest: Mapping[str, Any]) -> list[str]:
    """Where a quest of steps goes on now: the places its stage's ways send the hero to (a place to reach, where the
    one to talk to is at this hour, the quest's own places for a creature), "here" for the hero's own place (the
    playtest: a quest's unvisited places said "come to Valecourt" to a hero standing in it)."""
    from app.apps.rpg.rules.quest.progress import ANYONE, step_ways

    steps = [_d(step) for step in _l(quest.get("steps"))]
    stage = int(_d(quest.get("progress")).get("stage") or 0)
    if stage >= len(steps):
        return []
    places, people, hero = _d(world.get("locations")), _d(world.get("npcs")), routines.hero_location(simulation)
    found: list[str] = []
    now = routines.whereabouts(simulation, routines.clock(simulation))
    for way, _ in step_ways(steps[stage]):
        for condition in way:
            if condition.get("reach"):
                found.append(_s(condition["reach"]))
            elif condition.get("talk"):
                where = now.get(_s(condition["talk"]))
                found.append(where.location_id if where else _s(_d(people.get(_s(condition["talk"]))).get("location_id")))
            elif condition.get("defeat"):
                found.extend(_s(place) for place in _l(quest.get("locations")))
            elif condition.get("companion") and _s(condition["companion"]) != ANYONE:
                found.append(_s(_d(people.get(_s(condition["companion"]))).get("location_id")))
    return list(dict.fromkeys("here" if place == hero else _s(_d(places.get(place)).get("name")) or place
                              for place in found if place))


def _settled_now(simulation: Mapping[str, Any], speaker_id: str, text: str) -> tuple[dict[str, Any], ...]:
    """The quest steps the hero's words to the speaker do, judged by the quest rules as if the words were said (the
    playtest: told what should become of the engine, the princess asked to be told it at the engine)."""
    from app.apps.rpg.rules.quest.progress import quest_progress

    changes, _ = quest_progress(simulation, [DialogueExchanged(npc_id=speaker_id, player_line=text[:500])],
                                lambda quest: ([], ""))
    quests = {_s(_d(row).get("quest_id") or _d(row).get("id")): _d(row)
              for row in _l(_d(_sections.quest_state_of(simulation)).get("quests"))}
    done = {change.quest_id for change in changes if isinstance(change, QuestStatusChanged) and change.status == "completed"}
    settled = []
    for change in changes:
        if not isinstance(change, QuestStepCompleted):
            continue
        quest = quests.get(change.quest_id, {})
        steps = [_d(step) for step in _l(quest.get("steps"))]
        did = _s(steps[change.stage - 1].get("summary")) if 0 < change.stage <= len(steps) else ""
        settled.append({"quest": _s(quest.get("title")), "done": did,
                        **({"quest_complete": True} if change.quest_id in done and not change.next_objective
                           else {"next": change.next_objective} if change.next_objective else {})})
    return tuple(settled)


def _hero_quests(simulation: Mapping[str, Any], world: Mapping[str, Any], speaker_id: str, name: str,
                 here: str) -> tuple[dict[str, Any], ...]:
    """The hero's quests under way that the speaker bears on (one they gave, one at their place, one naming them, or
    any, for someone travelling with the hero), each with where the game says it goes on: the places it has not
    reached yet. A line then points there rather than inventing an errand the game does not have (the playtest: asked
    how to mend the phone, Brindle wanted "aether-coil wire"; the quest goes on at the Moonroot Ruins)."""
    companions = {_s(_d(row).get("npc_id")) for row in
                  _l(_d(_sections.party_state_of(_d(_sections.player_state_of(simulation)))).get("companions"))}
    places = _d(world.get("locations"))
    first_name = name.split()[0].casefold() if name else ""
    found: list[dict[str, Any]] = []
    for quest in _l(_d(_sections.quest_state_of(simulation)).get("quests")):
        quest = _d(quest)
        if quest.get("status") not in {"active", "completed"}:
            continue
        locations = [_s(place) for place in _l(quest.get("locations"))]
        told = f"{_s(quest.get('title'))} {_s(quest.get('objective'))}".casefold()
        if not (speaker_id in companions or _s(quest.get("giver_id")) == speaker_id or (here and here in locations)
                or (first_name and first_name in told)):
            continue
        if quest.get("status") == "completed":  # done: a line does not send the hero back to it
            found.append({"title": _s(quest.get("title")), "done": True})
            continue
        visited = {_s(place) for place in _l(quest.get("visited_locations"))}
        ahead = (_step_places(simulation, world, quest) if _l(quest.get("steps"))
                 else [_s(_d(places.get(place)).get("name")) or place for place in locations if place not in visited])
        if not ahead and _DEFEAT.search(_s(quest.get("objective")).casefold()):
            # A creature to defeat, at no place of its own: where the world's creatures are met (encounters.md).
            ahead = [_s(_d(places.get(place_id)).get("name")) or place_id
                     for place_id in _by_road(world, routines.hero_location(simulation))
                     if routines.is_wild(simulation, place_id)][:2]
        found.append({"title": _s(quest.get("title")), "objective": _s(quest.get("objective")),
                      **({"goes_on_at": ahead} if ahead else {})})
    return tuple(found[:3])


def build_plan(simulation: Mapping[str, Any], speaker_id: str, text: str, *,
               hero: Mapping[str, str] | None = None) -> DialoguePlan | None:
    """The plan for ``speaker_id``'s answer to ``text``, to the ``hero`` (their name and pronouns); ``None`` when the
    world does not know them."""
    world = _d(_sections.world_model_of(simulation))
    npc = {**_d(_d(_sections.npc_index_of(simulation)).get(speaker_id)), **_d(_d(world.get("npcs")).get(speaker_id))}
    if not npc:
        return None
    name = _s(npc.get("name")) or speaker_id
    trust = _trust(simulation, speaker_id)
    stance = "friendly" if trust >= FRIENDLY_TRUST else "wary" if trust < 0 else "neutral"
    asked = _words(text) | {_stem(word) for word in _words(text)}
    known = set(_l(_d(_d(simulation.get("dialogue")).get("known_facts")).get(speaker_id)))
    reveals, revealed_ids, priced, held = [], [], [], 0
    # The speaker's own name asks about none of what they know ("Brindle, what does a potion cost?" is not about
    # "Brindle's Impossible Radio": the golden, once Aurelia's people knew things).
    named = _words(name) | {_stem(word) for word in _words(name)}
    for fact in _facts(world, speaker_id):
        topics = ({topic.casefold() for topic in _l(fact.get("topics"))} | _words(_s(fact.get("text")))) - named
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
    new_quests: dict[str, dict[str, Any]] = {}  # an offered quest the log does not have yet, with its row
    here = _s(npc.get("location_id"))
    offerable = []
    hands_out_work = bool(_GIVES_WORK.search(_s(npc.get("role")).casefold()))
    logged = [_d(quest) for quest in _l(_d(_sections.quest_state_of(simulation)).get("quests"))]
    in_log = {_s(quest.get("quest_id") or quest.get("id")) for quest in logged}
    # The log's quests on offer, and the world's that are not in it yet (offered, they join it).
    unlogged = [{**_d(row), "status": "available"} for quest_id, row in _d(world.get("quests")).items()
                if quest_id not in in_log]
    for quest in [*logged, *unlogged]:
        places = [_s(place) for place in _l(quest.get("locations"))]
        giver = _s(quest.get("giver_id") or quest.get("offered_by"))
        if quest.get("status") == "available" and (giver == speaker_id or (not giver and (here in places
                                                                                          or hands_out_work))):
            # The speaker's own name is no word of the quest's ("Vael, nice weather" is not about his vow).
            steps = " ".join(_s(_d(step).get("summary")) for step in _l(quest.get("steps")))
            # A finale by its name alone ("the Hollow Meridian"): its steps' words are a newcomer's own ("is this
            # Earth? is there a gate?": the third review).
            told = (_s(quest.get("title")) if _s(quest.get("tier")) == "finale"
                    else f"{_s(quest.get('title'))} {_s(quest.get('objective'))} {steps}")
            about = _stemmed(_words(told)) - _stemmed(_words(name))
            # A finale is the last thing offered for work in general (a newcomer was offered the Hollow Meridian).
            fitting = 0 if _s(quest.get("tier")) == "finale" else 1
            offerable.append((len(about & asked), fitting, len(about & pressing), quest))
    # Asked for work, about what one of their goals is after and a quest of theirs answers, or about a quest of their
    # own (the playtest: asked what vow he would have witnessed, Vael never offered his): the quest closest to the
    # words, then to the goal they are most after (routines.md), offered.
    on_a_goal = any(asked & _goal_words(goal) for goal in goals) and any(row[0] for row in offerable)
    # Two of its own words, at least, and never the finale this way ("Liora, should we head to the village?" touched
    # the finale's "should" and offered it: the review).
    on_their_quest = any(row[0] >= 2 and _s(row[3].get("giver_id") or row[3].get("offered_by")) == speaker_id
                         for row in offerable)
    # A finale is offered only when asked about in its own words (two of them), never for work in general.
    offerable = [row for row in offerable if row[1] or row[0] >= 2]
    if offerable and (_WORK.search(text.casefold()) or on_a_goal or on_their_quest):
        quest = max(offerable, key=lambda row: row[:3])[3]
        quest_id = _s(quest.get("quest_id") or quest.get("id"))
        quest_offer = {"quest_id": quest_id, "title": _s(quest.get("title")), "objective": _s(quest.get("objective"))}
        if quest_id not in in_log:
            new_quests[quest_id] = quest
    hero_quests = _hero_quests(simulation, world, speaker_id, name, here)
    common = _common_knowledge(world, text, speaker_id)
    settled = _settled_now(simulation, speaker_id, text)
    on_sale: list[dict[str, Any]] = []
    if _WARES.search(text.casefold()):
        on_sale = [_d(offer) for offer in _l(_d(world.get("offers")).get(speaker_id))
                   if _s(_d(offer).get("label")) and stock_left(simulation, _d(offer)) != 0]
        # Asked about some of them ("what does a room cost"), those; asked what they sell, all of them.
        # Not by the speaker's own name: asking Brindle a price is not asking for "Brindle's Arc Baton".
        wanted = [offer for offer in on_sale
                  if asked & ({_stem(word) for word in _words(_s(offer.get("label")))} - named)]
        on_sale = wanted or on_sale
    secrets = tuple(_s(secret) for secret in _l(npc.get("secrets")) if _s(secret).strip())
    # What the writer is told leaves out whatever repeats a secret (an author's description or goal may), so the
    # model never sees one and the line can be shown as it is written (Q-12).
    goal_texts = dict.fromkeys([*(_s(goal.get("summary")) for goal in goals), *(_s(goal) for goal in _l(npc.get("goals")))])
    background = sayable(_s(npc.get("description")), secrets)
    return DialoguePlan(
        speaker_id=speaker_id, speaker_name=name, role=_s(npc.get("role")), stance=stance,
        voice=_s(npc.get("speech_style")), personality=tuple(_s(trait) for trait in _l(npc.get("personality"))),
        goals=tuple(goal for goal in goal_texts if goal and not _names_a_secret(goal, secrets)),
        background=background,
        reveals=tuple(reveals), revealed_ids=tuple(revealed_ids), for_a_price=tuple(priced), held_back=held,
        secrets=secrets, quest_offer=quest_offer, offered_rows=new_quests, hero_quests=hero_quests,
        common_knowledge=common, settled_now=settled, hero=dict(hero or {}),
        wares=tuple(f"{in_sentence(_s(offer.get('label')))} for {_charged(simulation, world, speaker_id, here, offer)}"
                    for offer in on_sale),
        ware_names=tuple(_s(offer.get("label")) for offer in on_sale),
        player_said=text,
    )


def plan_changes(plan: DialoguePlan) -> list[StateChange]:
    """What the plan makes real before the commit: what is now known, and what is offered."""
    changes: list[StateChange] = []
    changes.extend(KnowledgeShared(npc_id=plan.speaker_id, fact_id=fact_id) for fact_id in plan.revealed_ids)
    if plan.quest_offer.get("quest_id"):
        quest_id = plan.quest_offer["quest_id"]
        changes.append(QuestOffered(quest_id=quest_id, npc_id=plan.speaker_id,
                                    quest=dict(plan.offered_rows.get(quest_id) or {})))
    return changes






def line_keeps_the_plan(plan: DialoguePlan, line: str) -> bool:
    """The written line may be shown: it is not empty, names each ware asked about (by a word of its name: the
    prices are the game's, so a line that leaves one out gives way to the plan's own list), and repeats none of
    the speaker's secrets."""
    lowered = line.casefold()
    said = {_stem(word) for word in _words(line)}
    if not lowered.strip() or any(not said & {_stem(word) for word in _words(name)} for name in plan.ware_names):
        return False
    return not _names_a_secret(line, plan.secrets)


__all__ = ["DialoguePlan", "build_plan", "line_keeps_the_plan", "plan_changes"]
