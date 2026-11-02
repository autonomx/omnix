"""The words of a line, read for the slots a reading carries (evolution roadmap EV-9, stage one).

The rules no longer read the player's words: they read a reading's ids and typed slots. Until every typed line goes
to the intent call, the command grammar's readings get their slots here, from the words, as the rules used to read
them: what to buy and from whom and how many, what to sell and to whom, how long to wait, how to rest, what the hero
asks of their standing, a companion's order, a level's choice, how many of a thing, what a line asks a person about
and the quest step it answers. Nothing on the turn path reads the words but this, and it goes with the grammar.
"""
from __future__ import annotations

import re
from typing import Any, Mapping

from app.apps.rpg.foundation.safe_values import safe_dict as _d, safe_list as _l, safe_str as _s
from app.apps.rpg.foundation.state import access as _sections
from app.apps.rpg.rules.intent.reading import IntentCandidate, ReadingSlots

# -- trade (rules/economy/trade.py's words, before EV-9) ----------------------------------------------------------
_WORD = re.compile(r"[a-z0-9']+")
_GENERIC = frozenset({"supplies", "goods", "wares", "something", "anything", "stuff", "things", "items"})
MOST_AT_ONCE = 10
_COUNTS = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
           "a couple of": 2, "a pair of": 2, "a few": 3, "several": 3}
_COUNT_WORDS = r"(\d+|" + "|".join(sorted(_COUNTS, key=len, reverse=True)) + r")"
_COINS = frozenset({"gold", "silver", "copper", "coin", "coins", "crown", "crowns", "credit", "credits"})
_COIN_WORDS = "|".join(sorted(_COINS))
_MEASURE_WORDS = ("feet|foot|yards?|met(?:er|re)s?|inch(?:es)?|pounds?|lbs|ounces?|miles?|hours?|days?|minutes?|"
                  "lit(?:er|re)s?|gallons?")
_KIND_WORDS = {
    "lodging": frozenset({"room", "rent", "lodging", "bed", "stay", "night", "sleep"}),
    "meal": frozenset({"meal", "food", "stew", "supper", "dinner", "breakfast", "lunch", "eat"}),
    "drink": frozenset({"drink", "ale", "wine", "beer", "mead"}),
}
_FILLER = frozenset("a an the some my one i buy purchase rent order get from to for of please".split())
_TITLES = frozenset({"captain", "lord", "lady", "sir", "dame", "dr", "doctor", "princess", "prince", "king", "queen",
                     "saint", "inspector", "archon", "master", "mistress", "father", "mother", "brother", "sister"})


def wanted_count(text: str, label: str) -> int:
    """How many of ``label`` the words ask for: a number or a number's word just before its name ("two Healing
    Potions", "3 lantern bread"), else one; at most ``MOST_AT_ONCE``. A price ("for 15 coppers") is no count."""
    named = [word for word in re.findall(r"[a-z]+", label.casefold()) if word not in {"a", "an", "the", "some", "of"}]
    words = [re.escape(word) for word in named if word not in _COINS][-1:] or [re.escape(word) for word in named][-1:]
    words += [re.escape(word) for word in re.findall(r"([a-z]+)\s+of\s", label.casefold())[:1]
              if word not in _COINS and not re.fullmatch(_MEASURE_WORDS, word)]
    if not words:
        return 1
    some_of = re.search(rf"\b{_COUNT_WORDS}\s+of\s+(?:the|those|these|your|his|her|their)\s+"
                        rf"(?:[a-z0-9'-]+\s+){{0,3}}?(?:{'|'.join(words)})(?:s|es)?\b", text.casefold())
    if some_of is not None:
        word = some_of.group(1)
        return max(1, min(MOST_AT_ONCE, int(word) if word.isdigit() else _COUNTS[word]))
    own = "|".join(re.escape(word) for word in named) or "(?!)"
    between = rf"(?:(?:{own})(?:s|es)?[\s-]+|(?!(?:{_MEASURE_WORDS}|{_COIN_WORDS})\b)[a-z']+[\s-]+)"
    match = re.search(rf"\b{_COUNT_WORDS}\s+{between}{{0,2}}(?:{'|'.join(words)})(?:s|es)?\b"
                      rf"(?!\s+(?:{_COIN_WORDS})\b)", text.casefold())
    if match is None:
        return 1
    word = match.group(1)
    own_number = re.search(rf"\b{re.escape(word)}\s+([a-z']+)", label.casefold())
    said_next = re.match(r"\s*([a-z']+)", match.group(0)[len(word):])
    if own_number and said_next and said_next.group(1).rstrip("s") == own_number.group(1).rstrip("s"):
        return 1
    return max(1, min(MOST_AT_ONCE, int(word) if word.isdigit() else _COUNTS[word]))


def _words(text: str) -> set[str]:
    return {word for word in _WORD.findall(text.casefold()) if word not in _FILLER}


def _name_words(name: str) -> set[str]:
    return {word for word in _words(name) if len(word) >= 3 and word not in _TITLES}


def _named(providers: list[dict[str, Any]], words: set[str], text: str) -> list[dict[str, Any]]:
    lowered = text.casefold()
    return [provider for provider in providers
            if _s(provider.get("provider_name")).casefold() in lowered
            or words & {_s(alias).casefold() for alias in _l(provider.get("aliases")) if " " not in _s(alias)}
            or words & _name_words(_s(provider.get("provider_name")))]


def _score(offer: Mapping[str, Any], words: set[str]) -> int:
    label = _words(_s(offer.get("label")))
    score = 10 * len(words & label)
    if words & _KIND_WORDS.get(_s(offer.get("service_kind")), frozenset()):
        score += 6
    items = {_s(_d(item).get("item_id")).rsplit(":", 1)[-1] for item in _l(_d(offer.get("effects")).get("items_added"))}
    if any(word in item.split("-") or word in item.split("_") for word in words for item in items):
        score += 4
    return score


def read_buy(simulation: Mapping[str, Any], text: str) -> tuple[str, str, int | None]:
    """(offer id, seller id, count) the words ask to buy; "" for an offer the words do not name."""
    from app.apps.rpg.rules.economy.trade import _offers, _providers_here

    words = _words(text)
    sellers = [provider for provider in _providers_here(simulation) if _offers(simulation, provider)]
    named = _named(sellers, words, text)
    candidates = named or sellers
    seller = _s(named[0].get("provider_id")) if len(named) == 1 else ""
    ranked = sorted(((_score(offer, words), index, provider, offer) for provider in candidates
                     for index, offer in enumerate(_offers(simulation, provider))), key=lambda row: (-row[0], row[1]))
    if not ranked or ranked[0][0] == 0 or words <= _GENERIC:
        return "", seller, None
    _, _, provider, offer = ranked[0]
    count = wanted_count(text, _s(offer.get("label"))) if _s(offer.get("service_kind")) == "shop_goods" else 1
    return _s(offer.get("offer_id")), _s(provider.get("provider_id")), count if count > 1 else None


def read_sell(simulation: Mapping[str, Any], text: str) -> tuple[str, str]:
    """(item id, buyer id) the words ask to sell; "" for what they do not name."""
    from app.apps.rpg.rules.economy.trade import _providers_here

    world = _d(_sections.world_model_of(simulation))
    lowered = text.casefold()
    store = _d(_sections.inventory_state_of(_d(_sections.player_state_of(simulation))))
    carried = sorted((_d(item) for item in _l(store.get("items")) if _s(_d(item).get("name")).casefold() in lowered),
                     key=lambda item: len(_s(item.get("name"))), reverse=True)
    if not carried:
        return "", ""
    item = carried[0]
    name = _s(item.get("name"))
    shops = [provider for provider in _providers_here(simulation) if "shop_goods" in _l(provider.get("service_kinds"))]
    rest = lowered.replace(name.casefold(), " ")
    people = _d(world.get("npcs"))
    present = {npc_id: _s(_d(people.get(npc_id)).get("name"))
               for npc_id in _l(_d(_sections.present_npc_state_of(simulation)).get("present_npc_ids"))}

    def someone_in(words: set[str], said: str) -> bool:
        return bool(_named(shops, words, said)) or any(words & _name_words(person) for person in present.values())

    def buyer_after(to: re.Match[str]) -> str:
        after = rest[to.end():].split()
        start = 1 if after[:1] == ["the"] else 0
        return " ".join(after[start:start + 1])

    verb = re.search(r"\b(?:sell|selling|sold|pawn|pawned|offload|trade|traded|hawk)\b", rest)
    slot = next((buyer_after(to) for to in re.finditer(r"\bto\s+", rest)
                 if (verb is None or to.start() > verb.start())
                 and someone_in(_words(buyer_after(to)) - _words(name), buyer_after(to))), "")
    asked = _words(slot or rest) - _words(name)
    named = _named(shops, asked, slot or rest)
    buyer = _s(named[0].get("provider_id")) if len(named) == 1 else ""
    if not named and slot:
        buyer = next((npc_id for npc_id, person in present.items() if asked & _name_words(person)), "")
    return _s(item.get("item_id") or item.get("id")), buyer


# -- waiting, resting, standing, orders, choices, counts ---------------------------------------------------------
_UNTIL = (
    (("dawn", "daybreak", "sunrise", "first light"), 6),
    (("morning",), 8),
    (("noon", "midday"), 12),
    (("afternoon",), 14),
    (("dusk", "sunset", "sundown"), 18),
    (("evening",), 19),
    (("nightfall", "night", "tonight", "dark"), 21),
    (("midnight",), 0),
)
_NUMBERS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
            "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "a few": 3, "a couple of": 2, "several": 4, "half an": 0.5}
_FOR = re.compile(r"\b(\d+|a few|a couple of|several|half an|an|a|one|two|three|four|five|six|seven|eight|nine|ten|"
                  r"eleven|twelve)\s+(hours?|minutes?)\b")


def read_wait(text: str) -> dict[str, Any]:
    """The wait the words name: until an hour of the day (tomorrow's, when they say so), or for so long."""
    lowered = text.casefold()
    until = (re.search(r"\b(?:until|till|til)\s+(?:the\s+)?(tomorrow\s+)?(\w+(?:\s\w+)?)", lowered)
             or re.search(r"\bfor\s+(?:the\s+)?(tomorrow\s+)?(\w+)(?=\s*(?:[.!?,;]|$))", lowered))
    if until:
        for names, hour in _UNTIL:
            if any(re.match(rf"{name}\b", until.group(2)) for name in names):
                return {"until_hour": hour, "tomorrow": bool(until.group(1))}
    counted = _FOR.search(lowered)
    if counted:
        amount = float(counted.group(1)) if counted.group(1).isdigit() else _NUMBERS[counted.group(1)]
        return {"wait_minutes": max(1, int(amount * (60 if counted.group(2).startswith("hour") else 1)))}
    return {}


_SLEEP = re.compile(r"\b(sleep|slumber|bed|night|room)\b")
_CAMP = re.compile(r"\b(camp|bedroll|tent)\b")
_STATUS_TOPICS = {
    "progress": re.compile(r"\b(level|experience|xp|progress|character)\b"),
    "inventory": re.compile(r"\b(inventory|pack|bag|belongings|purse|carry(?:ing)?|gear|have|money|coin|gold)\b"),
    "quests": re.compile(r"\b(quests?|journal|objectives?)\b"),
    "skills": re.compile(r"\b(skills?|training)\b"),
    "health": re.compile(r"\b(health|hurt|wounds?|hp)\b"),
}
_ORDERS = (("keep watch", "watch"), ("stand watch", "watch"), ("stand guard", "guard"), ("keep guard", "guard"),
           ("guard", "guard"), ("wait here", "stay"), ("stay", "stay"), ("hold", "stay"), ("follow", "follow"),
           ("scout", "scout"), ("protect", "guard"), ("cover", "guard"), ("take point", "scout"))
_ITEM_NUMBERS = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "both": 2, "all": 0}
_ATTRIBUTE_WORDS = {"str": "strength", "agility": "dexterity", "dex": "dexterity", "endurance": "constitution",
                    "con": "constitution", "intellect": "intelligence", "int": "intelligence", "wis": "wisdom",
                    "perception": "wisdom", "cha": "charisma", "presence": "charisma"}


def read_rest(text: str) -> str | None:
    lowered = text.casefold()
    return "camp" if _CAMP.search(lowered) else "sleep" if _SLEEP.search(lowered) else None


def read_status(text: str) -> tuple[str, ...]:
    lowered = text.casefold()
    return tuple(topic for topic, pattern in _STATUS_TOPICS.items() if pattern.search(lowered))


def read_order(text: str) -> str:
    lowered = text.casefold()
    return next((stance for words, stance in _ORDERS if words in lowered), "")


def read_count(text: str) -> dict[str, Any]:
    """How many of a thing carried the words name: a number, "both", or all of them."""
    for word in re.findall(r"[a-z]+|\d+", text.casefold()):
        if word.isdigit():
            return {"quantity": max(1, min(99, int(word)))}
        if word in _ITEM_NUMBERS:
            return {"everything": True} if _ITEM_NUMBERS[word] == 0 else {"quantity": _ITEM_NUMBERS[word]}
    return {}


def read_choice(document: Mapping[str, Any], text: str) -> str:
    """A level's choice the words make: an attribute raised, an ability learned, or two skills improved."""
    from app.apps.rpg.rules.player.progression import ATTRIBUTES, _learnable, _player

    words = re.findall(r"[a-z]+", text.casefold())
    attribute = next((word if word in ATTRIBUTES else _ATTRIBUTE_WORDS[word]
                      for word in words if word in ATTRIBUTES or word in _ATTRIBUTE_WORDS), "")
    if attribute and words[:1] != ["learn"]:
        return f"attribute:{attribute}"
    named = [row for row in _learnable(document)
             if all(word in words for word in re.findall(r"[a-z]+", _s(row.get("name")).casefold()))]
    if named:
        return f"ability:{_s(max(named, key=lambda row: len(_s(row.get('name')))).get('ability_id'))}"
    skills = _d(_player(_d(_sections.simulation_state_of(document))).get("skills"))
    chosen = [skill for skill in skills if skill.replace("_", " ") in " ".join(words)][:2]
    return f"skills:{','.join(chosen)}" if len(chosen) == 2 else ""


# -- what a line asks a person about, and the step it answers (rules/dialogue/plan.py's words, before EV-9) ------
_NEWS = re.compile(r"\b(news|rumou?rs?|gossip|word going about|what is going on)\b")
_WORK = re.compile(r"\b(work|jobs?|tasks?|help|quests?|errands?|hire|bount(y|ies)|contracts?|need (of|from) me|"
                   r"anything i can do)\b")
_WARES = re.compile(r"\b(sell|selling|sale|wares|buy|price|prices|cost|costs|goods|offer|stock|shop|merchandise|room|"
                    r"rooms|food|drink)\b")


def _stem(word: str) -> str:
    return word[:-1] if word.endswith("s") and len(word) > 3 else word


def read_topics(simulation: Mapping[str, Any], speaker_id: str, text: str) -> tuple[str, ...]:
    """The topic ids (``rules/dialogue/plan.speaker_topics``, and the world's places, groups and people) the words of
    a line to ``speaker_id`` touch."""
    from app.apps.rpg.rules.dialogue.plan import (
        WARES,
        WORK,
        _facts,
        _goal_id,
        _goal_words,
        _goals,
        _offerable,
        _stemmed,
        offer_key,
    )
    from app.apps.rpg.rules.secrets import meaning_words

    world = _d(_sections.world_model_of(simulation))
    npc = {**_d(_d(_sections.npc_index_of(simulation)).get(speaker_id)), **_d(_d(world.get("npcs")).get(speaker_id))}
    if not npc:
        return ()
    name = _s(npc.get("name")) or speaker_id
    asked = meaning_words(text) | {_stem(word) for word in meaning_words(text)}
    named = meaning_words(name) | {_stem(word) for word in meaning_words(name)}
    topics: list[str] = []
    for fact in _facts(world, speaker_id):
        about = ({topic.casefold() for topic in _l(fact.get("topics"))} | meaning_words(_s(fact.get("text")))) - named
        if asked & about and _s(fact.get("fact_id")):
            topics.append(_s(fact.get("fact_id")))
    goals = _goals(world, speaker_id, frozenset())
    touched = [goal for goal in goals if asked & _goal_words(goal)]
    topics += [_goal_id(goal) for goal in touched if _goal_id(goal)]
    work = bool(_WORK.search(text.casefold()))
    pressing = _goal_words(touched[0] if touched else goals[0]) if goals else set()
    offerable = []
    for quest in _offerable(simulation, world, npc, speaker_id):
        steps = " ".join(_s(_d(step).get("summary")) for step in _l(quest.get("steps")))
        told = (_s(quest.get("title")) if _s(quest.get("tier")) == "finale"
                else f"{_s(quest.get('title'))} {_s(quest.get('objective'))} {steps}")
        about = _stemmed(meaning_words(told)) - _stemmed(named)
        fitting = 0 if _s(quest.get("tier")) == "finale" else 1
        offerable.append((len(about & asked), fitting, len(about & pressing), quest))
    on_a_goal = bool(touched) and any(row[0] for row in offerable)
    on_their_quest = any(row[0] >= 2 and _s(row[3].get("giver_id") or row[3].get("offered_by")) == speaker_id
                         for row in offerable)
    offerable = [row for row in offerable if row[1] or row[0] >= 2]
    if offerable and (work or on_a_goal or on_their_quest):
        quest = max(offerable, key=lambda row: row[:3])[3]
        topics.append(_s(quest.get("quest_id") or quest.get("id")))
    elif work:
        topics.append(WORK)
    if _WARES.search(text.casefold()):
        offers = [_d(offer) for offer in _l(_d(world.get("offers")).get(speaker_id)) if _s(_d(offer).get("label"))]
        wanted = [offer_key(offer) for offer in offers
                  if asked & ({_stem(word) for word in meaning_words(_s(offer.get("label")))} - named)]
        topics += wanted or [WARES]
    if _NEWS.search(text.casefold()):  # what is going about (EV-4), when anything is
        from app.apps.rpg.rules.rumours import NEWS, news_here
        from app.apps.rpg.rules.routines import hero_location

        topics += [NEWS] if news_here(simulation, hero_location(simulation)) else []
    topics += _named_in(world, text, speaker_id)
    return tuple(dict.fromkeys(topic for topic in topics if topic))


def _named_in(world: Mapping[str, Any], text: str, speaker_id: str) -> list[str]:
    """The places, groups and people of the world the words name (common knowledge)."""
    def named(*names: str, as_written: bool = False) -> bool:
        return any(len(name) > 3 and re.search(
            (r"(?<![.!?]\s)(?<!^)" if as_written else "") + rf"(?<![\w']){re.escape(name)}(?![\w'])", text.strip(),
            flags=0 if as_written else re.IGNORECASE) for name in names if name)

    found = [place_id for place_id, place in _d(world.get("locations")).items()
             if named(_s(_d(place).get("name")), *(_s(alias) for alias in _l(_d(place).get("aliases"))))]
    found += [group_id for group_id, group in _d(world.get("groups")).items()
              if named(_s(_d(group).get("name")), *_s(_d(group).get("name")).split()[-1:])]
    found += [person_id for person_id, person in _d(world.get("npcs")).items() if person_id != speaker_id
              and (named(_s(_d(person).get("name"))) or named(*_s(_d(person).get("name")).split()[:1], as_written=True))]
    return found


def read_step(simulation: Mapping[str, Any], speaker_id: str, text: str) -> str:
    """The open step a line to ``speaker_id`` answers, as the step's ``about`` words were matched before EV-3."""
    from app.apps.rpg.rules.quest.progress import step_address, step_ways

    lowered = text.casefold()
    for quest in map(_d, _l(_d(_sections.quest_state_of(simulation)).get("quests"))):
        steps = [_d(step) for step in _l(quest.get("steps"))]
        stage = int(_d(quest.get("progress")).get("stage") or 0)
        quest_id = _s(quest.get("quest_id") or quest.get("id"))
        if quest.get("status") != "active" or stage >= len(steps):
            continue
        for index, (way, _) in enumerate(step_ways(steps[stage])):
            for condition in way:
                about = [_s(word).casefold() for word in (_l(condition.get("about")) or [condition.get("about")])
                         if _s(word)]
                if _s(condition.get("talk")) == speaker_id and about and any(word in lowered for word in about):
                    return step_address(quest_id, _s(steps[stage].get("id")), index)
    return ""


def read_weakness(simulation: Mapping[str, Any], target_id: str, text: str) -> str:
    """The weakness of the foe ``target_id`` the words use (one of its names, whole), for an attack (EV-2)."""
    combat = _d(_sections.combat_state_of(simulation))
    rows = [_d(row) for row in _d(combat.get("participants")).values()
            if _d(row).get("side") == "enemy" and (not target_id or target_id in {
                _s(_d(row).get("definition_id")), _s(_d(row).get("actor_id"))})]
    creatures = _d(_d(_sections.campaign_mechanics_of(simulation)).get("creatures"))
    rows += [_d(creatures.get(target_id))] if target_id in creatures else []
    lowered = text.casefold()
    for row in rows:
        for weakness in _l(row.get("vulnerabilities")):
            names = [_s(_d(weakness).get("trigger_tag")), *(_s(alias) for alias in _l(_d(weakness).get("aliases")))]
            if any(name and re.search(rf"\b{re.escape(name.casefold())}\b", lowered) for name in names):
                return _s(_d(weakness).get("trigger_tag"))
    return ""


# -- a reading's slots, from its words ---------------------------------------------------------------------------

def with_slots(reading: IntentCandidate, text: str, document: Mapping[str, Any], *,
               speaker_id: str = "") -> IntentCandidate:
    """The grammar's reading with the slots its words name, its trade aimed at the offer or the thing they name."""
    from dataclasses import replace

    simulation = _d(_sections.simulation_state_of(document))
    family = reading.family
    slots: dict[str, Any] = {}
    target, second = reading.target_id, reading.second_target_id
    if family == "buy":
        offer, seller, count = read_buy(simulation, text)
        target, second = offer or None, seller or None
        slots = {"quantity": count} if count else {}
    elif family == "sell":
        item, buyer = read_sell(simulation, text)
        target, second = item or None, buyer or None
    elif family == "wait":
        slots = read_wait(text)
    elif family == "rest":
        slots = {"rest": read_rest(text)}
    elif family == "status":
        slots = {"status": read_status(text)}
    elif family == "order":
        slots = {"order": read_order(text)}
    elif family == "grow":
        slots = {"choice": read_choice(document, text)}
    elif family in {"drop", "give", "take"}:
        slots = read_count(text)
    elif family == "attack":
        slots = {"weakness": read_weakness(simulation, _s(reading.target_id), text)}
    elif family in {"talk", "ask", "decline"} and speaker_id:
        slots = {"topics": read_topics(simulation, speaker_id, text), "step": read_step(simulation, speaker_id, text)}
    slots = {key: value for key, value in slots.items() if value not in (None, "", ())}
    kind = reading.target_kind if target == reading.target_id else ("offer" if family == "buy" and target else
                                                                    "item" if target else None)
    return replace(reading, target_id=target, target_kind=kind, second_target_id=second,
                   slots=ReadingSlots(**slots) if slots else reading.slots)


__all__ = ["read_buy", "read_choice", "read_count", "read_order", "read_rest", "read_sell", "read_status",
           "read_step", "read_topics", "read_wait", "wanted_count", "with_slots"]
