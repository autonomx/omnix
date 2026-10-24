"""The command grammar: what a player's words ask for, read against the scene they stand in (RQ-3.1).

The grammar parses the commands a game can understand without a model: "buy the healing potion",
"go to Skybridge Pass", "attack the echo wolf with my dagger", "ask Liora where the Archon is". It
reads the text against a ``SceneView`` (the people present, the creatures, what is for sale, the
exits, the items, places, quests and skills the world knows) and returns an ``IntentCandidate``:
the action family, the entity it is aimed at, and how sure it is. When it is not sure it says so, and
the turn asks the model (RQ-3.2) or the player (a clarification).

Matching is by whole words. Verbs and the longer words of names tolerate one typo ("lok around",
"sel my dagger", "go too the market"); short words must match exactly, so "rest" is never found in
"forest" nor "use" in "useful".
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Literal

Family = Literal[
    "look", "inspect", "move", "talk", "ask", "decline", "buy", "sell", "attack", "flee", "defend",
    "take", "drop", "give", "use_item", "equip", "unequip", "manipulate", "rest", "wait", "quest",
    "practice", "party", "status", "order", "clarify", "ability", "check", "grow",
]
EntityKind = Literal["person", "creature", "item", "place", "offer", "quest", "skill", "group", "ability"]

# Families that change the campaign's state when carried out.
STATEFUL_FAMILIES = frozenset(
    {"move", "buy", "attack", "take", "drop", "give", "use_item", "rest", "quest", "practice", "party"}
)


@dataclass(frozen=True)
class SceneEntity:
    entity_id: str
    kind: EntityKind
    names: tuple[str, ...]
    here: bool = False  # present in the scene (a person or creature here, an exit, an offer on sale here)


@dataclass(frozen=True)
class SceneView:
    entities: tuple[SceneEntity, ...] = ()
    focus_id: str = ""  # the person the player is in conversation with, whom "him" or "her" means

    def of(self, *kinds: str, here: bool | None = None) -> list[SceneEntity]:
        return [
            entity for entity in self.entities
            if entity.kind in kinds and (here is None or entity.here == here)
        ]


@dataclass(frozen=True)
class IntentCandidate:
    family: Family
    target_id: str | None = None
    target_kind: str | None = None
    confidence: float = 0.0
    reason: str = ""
    second_target_id: str | None = None  # the recipient of a give, the seller of a buy
    clauses: tuple[str, ...] = field(default=())

    @property
    def stateful(self) -> bool:
        """Whether carrying it out would change state, as far as the words tell: buying needs something on sale."""
        if self.family == "buy":
            return self.target_kind == "offer"
        return self.family in STATEFUL_FAMILIES


_FILLER = frozenset(
    "a an the my some your his her their its this that these those of to too for at with from in on into "
    "up down out over about around and or then please just me i i'm im i'll ill i'd lets let us we our "
    "want would like wanna gonna going try trying will can could might should go".split()
)
_PRONOUNS = frozenset({"him", "her", "them", "it", "he", "she", "they", "that", "this", "there"})
_LEADING = (
    "i want to ", "i'd like to ", "id like to ", "i would like to ", "i'll ", "ill ", "i will ", "i try to ",
    "let me ", "lets ", "let's ", "can i ", "could i ", "may i ", "please ", "i'm going to ", "im going to ",
    "i am going to ", "i ", "we ",
)
_QUESTION_WORDS = frozenset(
    "what where who whom whose why how when which is are does do did can could would should will was were".split()
)


def _norm(text: str) -> str:
    text = text.casefold().replace("’", "'")
    text = re.sub(r"[^a-z0-9'?\s-]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


# Typos players make in command words, and the word they meant.
_TYPOS = {
    "lok": "look", "loook": "look", "arround": "around", "aroud": "around", "sel": "sell", "aks": "ask",
    "goto": "go to", "too": "to", "atack": "attack", "attak": "attack", "practise": "practice",
    "inventroy": "inventory", "invetory": "inventory", "examin": "examine", "pickup": "pick up",
    "whats": "what is", "what's": "what is", "who's": "who is", "where's": "where is", "im": "i am",
    "i'm": "i am", "dont": "don't", "wont": "won't", "cant": "can't", "purchse": "purchase", "byu": "buy",
    "giv": "give", "drp": "drop", "tke": "take", "lookk": "look", "sleeep": "sleep", "wiat": "wait",
    "pratice": "practice", "pracitce": "practice", "travle": "travel", "exmaine": "examine",
}
_BARE_VERBS = (
    "attack", "buy", "take", "give", "drop", "use", "sell", "equip", "eat", "drink", "fight", "open", "move",
    "talk", "ask", "again", "hmm", "um", "uh", "what", "huh",
)
_ATTRIBUTE_NAMES = ("strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma", "agility",
                    "endurance", "intellect", "perception", "presence")
# What a check is (checks.md), by the words that ask for one; searching stays a manipulation of the scene.
_CHECKS = (
    ("haggle", ("haggle", "bargain with", "bargain for", "talk the price down", "a better price", "a lower price",
                "beat the price down")),
    ("persuade", ("persuade", "convince", "coax", "sweet talk", "win over", "talk him into", "talk her into",
                  "talk them into", "reason with", "talk it down", "talk them down", "talk my way", "parley",
                  "negotiate with")),
    ("intimidate", ("intimidate", "threaten", "menace", "frighten", "scare")),
    ("deceive", ("lie to", "deceive", "bluff", "mislead", "trick", "fool")),
    ("sneak", ("sneak", "creep", "slip past", "steal past", "tiptoe", "hide from", "move quietly")),
    ("climb", ("climb", "scale the", "clamber")),
    ("pick_lock", ("pick the lock", "pick a lock", "pick its lock", "lockpick", "pick the door")),
    ("recall_lore", ("recall", "what do i know about", "try to remember", "remember what i know")),
    ("notice", ("listen for", "keep an eye out", "watch for", "look out for", "notice anything", "notice something")),
)
_VAGUE = ("same as before", "the thing", "the other one", "that one", "do that", "the usual", "you know what")
_SOCIAL = (
    "ask", "tell", "talk", "speak", "chat", "greet", "say", "wave", "hail", "call", "nod", "bow", "thank",
    "thanks", "hello", "hi", "hey", "shout", "whisper", "reply", "answer", "compliment", "apologize",
    "apologise", "introduce", "insult", "flatter", "joke", "smile", "laugh with", "salute", "beckon", "warn",
    "promise", "praise", "congratulate", "comfort", "console", "argue", "plead", "beg",
)


def _words(text: str) -> list[str]:
    words: list[str] = []
    raw = [word for word in re.split(r"[\s?-]+", text) if word]
    for index, word in enumerate(raw):
        if word == "tak":
            # "tak to Mira" is talking; "tak the dagger" is taking.
            word = "talk" if index + 1 < len(raw) and raw[index + 1] in {"to", "too", "with"} else "take"
        elif word == "by" and index == 0:
            word = "buy"
        word = _TYPOS.get(word, word)
        words.extend(part for part in word.replace("'s", "").split() if part)
    return words


def _edit1(a: str, b: str) -> bool:
    """Whether ``a`` and ``b`` differ by at most one edit (insert, delete, substitute, swap)."""
    if a == b:
        return True
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        diff = [i for i in range(len(a)) if a[i] != b[i]]
        return len(diff) == 1 or (len(diff) == 2 and diff[1] == diff[0] + 1
                                  and a[diff[0]] == b[diff[1]] and a[diff[1]] == b[diff[0]])
    short, long = (a, b) if len(a) < len(b) else (b, a)
    for index in range(len(long)):
        if long[:index] + long[index + 1:] == short:
            return True
    return False


def _word_matches(word: str, wanted: str) -> bool:
    """Short command words match exactly (their common typos are in ``_TYPOS``); long ones tolerate one typo."""
    return word == wanted or (len(wanted) >= 6 and len(word) >= 5 and _edit1(word, wanted))


def _name_word_matches(word: str, wanted: str) -> bool:
    return word == wanted or (len(wanted) >= 5 and len(word) >= 4 and _edit1(word, wanted))


def _has(words: list[str], *phrases: str) -> bool:
    """Whether any phrase (one or more words) occurs in ``words`` as whole words."""
    for phrase in phrases:
        parts = phrase.split()
        for start in range(len(words) - len(parts) + 1):
            if all(_word_matches(words[start + offset], part) for offset, part in enumerate(parts)):
                return True
    return False


def _starts(words: list[str], *phrases: str) -> bool:
    for phrase in phrases:
        parts = phrase.split()
        if len(words) >= len(parts) and all(_word_matches(words[i], part) for i, part in enumerate(parts)):
            return True
    return False


@dataclass(frozen=True)
class _Hit:
    entity: SceneEntity
    score: float
    start: int


def _name_tokens(name: str) -> list[str]:
    return [word for word in _words(_norm(name)) if word not in _FILLER]


def _find(words: list[str], entities: Iterable[SceneEntity]) -> list[_Hit]:
    """Entities named in ``words``: every distinctive word of one of its names present, best first."""
    hits: list[_Hit] = []
    for entity in entities:
        best: _Hit | None = None
        for name in entity.names:
            tokens = _name_tokens(name)
            if not tokens:
                continue
            positions = []
            for token in tokens:
                found = next((i for i, word in enumerate(words) if _name_word_matches(word, token)), None)
                positions.append(found)
            matched = [p for p in positions if p is not None]
            if len(matched) == len(tokens):
                score = len(tokens) + 0.5 + (0.25 if entity.here else 0.0)
            elif len(tokens) >= 2 and matched and any(len(tokens[i]) >= 4 for i, p in enumerate(positions) if p is not None):
                # A distinctive part of a longer name ("Juno" for "Juno Rask", "the market" for a long market name).
                score = len(matched) / len(tokens) + (0.25 if entity.here else 0.0)
            else:
                continue
            hit = _Hit(entity, score, min(matched))
            if best is None or hit.score > best.score:
                best = hit
        if best is not None:
            hits.append(best)
    return sorted(hits, key=lambda hit: (-hit.score, hit.start, hit.entity.entity_id))


def _first(words: list[str], scene: SceneView, *kinds: str, here: bool | None = None) -> _Hit | None:
    hits = _find(words, scene.of(*kinds, here=here))
    return hits[0] if hits else None


def _candidate(family: Family, hit: _Hit | None, confidence: float, reason: str, **extra) -> IntentCandidate:
    return IntentCandidate(
        family=family,
        target_id=hit.entity.entity_id if hit else None,
        target_kind=hit.entity.kind if hit else None,
        confidence=confidence,
        reason=reason,
        **extra,
    )


_COMMAND_WORDS = frozenset(
    "attack fight strike hit stab slash shoot punch kick kill charge swing smite assault ambush slay shove tackle "
    "slap go travel walk head return leave enter visit move hurry ride run journey set off out make way".split()
)


def _object_words(words: list[str]) -> list[str]:
    """What the command is aimed at beyond its verb and filler (empty for "attack" or "go")."""
    return [word for word in words if word not in _FILLER and word not in _COMMAND_WORDS and word not in _PRONOUNS]


def _strip_leading(text: str) -> str:
    changed = True
    while changed:
        changed = False
        for prefix in _LEADING:
            if text.startswith(prefix) and len(text) > len(prefix):
                text = text[len(prefix):]
                changed = True
    return text


def _clauses(text: str) -> tuple[str, ...]:
    parts = re.split(r",? (?:and then|then|and afterwards|after that) |; ", text)
    return tuple(part.strip() for part in parts if part.strip())


def _clarify(reason: str) -> IntentCandidate:
    return IntentCandidate(family="clarify", confidence=0.9, reason=reason)


def parse_command(text: str, scene: SceneView) -> IntentCandidate:
    """What ``text`` asks for in ``scene``; ``confidence`` below 0.6 means the grammar is guessing."""
    normalized = _norm(text)
    clauses = _clauses(normalized)
    first = _strip_leading(clauses[0] if clauses else normalized)
    candidate = _parse_clause(first, scene, original=normalized)
    if len(clauses) > 1:
        candidate = IntentCandidate(**{**candidate.__dict__, "clauses": clauses})
    return candidate


_ORDERS = (
    "keep watch", "stand guard", "stand watch", "keep guard", "guard me", "guard the", "wait here", "stay here", "stay back",
    "follow me", "scout ahead", "scout", "hold back", "hold position", "protect me", "cover me", "take point",
)
_STATUS_QUESTIONS = (
    "how hurt", "how am i", "my health", "what am i carrying", "what do i have", "what quests", "my quests",
    "what level", "my level", "how much money do i have", "how much gold do i have", "how much coin do i have",
    "in my pack", "in my bag", "my objectives", "my inventory", "my skills", "what skills", "my xp",
)
_LOOK_QUESTIONS = (
    "what is here", "where am i", "who is around", "who is here", "anyone else here", "anybody here",
    "what is going on", "what do i see", "what can i see", "what is around", "is anyone here",
)
_STATUS_WORDS = (
    "inventory", "status", "stats", "journal", "character sheet", "my quests", "my skills", "my level",
    "my purse", "my gear", "my bag", "my pack", "my health", "my xp", "my objectives", "check my xp",
)


def _question(words: list[str], original: str) -> bool:
    if original.endswith("?"):
        return True
    return bool(words) and words[0] in _QUESTION_WORDS and not _starts(words, "what a", "how nice", "how lovely")


def _ask(words: list[str], scene: SceneView, addressed: _Hit | None) -> IntentCandidate:
    if addressed is not None:
        return _candidate("ask", addressed, 0.85, "asks_someone")
    subject = _first(words, scene, "person", "creature", "place", "item", "offer", "quest", "skill", "group")
    return _candidate("ask", subject, 0.75 if subject else 0.6, "asks")


def _addressed(words: list[str], scene: SceneView) -> _Hit | None:
    """The person spoken to: named first ("Liora, ..."), or after ask/tell/talk to."""
    lead = _find(words[:3], scene.of("person"))
    if lead and lead[0].start <= 1:
        return lead[0]
    if _starts(words, *_SOCIAL) or _has(words, "good morning", "good evening", "good afternoon", "good day",
                                         "hello", "greetings", "and chat", "chat with", "talk with"):
        named = _first(words, scene, "person", here=True) or _first(words, scene, "person")
        if named is None and _has(words, "him", "her", "them"):
            present = scene.of("person", here=True)
            focus = next((entity for entity in present if entity.entity_id == scene.focus_id), None)
            if focus is not None or len(present) == 1:
                return _Hit(focus or present[0], 1.0, 0)
        return named
    return None


def _parse_clause(text: str, scene: SceneView, *, original: str) -> IntentCandidate:  # noqa: C901 - one rule table
    words = _words(text)
    if not words:
        return _clarify("empty")
    question = _question(words, original)

    # No, never mind, not now: the player declines what was offered or proposed.
    if _starts(words, "no", "nope", "never mind", "nevermind", "forget it", "not now", "cancel", "decline",
               "refuse", "no thanks", "don't", "do not") or _has(
            words, "don't want", "do not want", "rather not", "won't", "will not", "decide not", "don't attack",
            "not going to", "choose not"):
        return _candidate("decline", _first(words, scene, "person", "offer", "item", "quest", "creature"), 0.85,
                          "declines")
    if words in (["yes"], ["yeah"], ["ok"], ["okay"], ["sure"], ["do", "it"], ["go"], ["yes", "please"]):
        return _clarify("bare_assent")
    if len(words) == 1 and _starts(words, "attack", "fight", "strike"):
        return _clarify("attack_without_target")  # in a fight, the foe in front of the hero
    if len(words) == 1 and _starts(words, *_BARE_VERBS):
        return _clarify("verb_without_object")
    if _starts(words, *_VAGUE) or (_has(words, "it", "them", "that") and len(words) <= 2):
        return _clarify("vague_reference")
    if _has(words, "not interested", "don't need", "no thanks", "no thank you") or (
            len(words) > 1 and words[1] in {"no", "nope"}):
        return _candidate("decline", _first(words, scene, "person", "offer", "item"), 0.8, "declines")
    if _starts(words, "do nothing", "don't do anything"):
        return _candidate("wait", None, 0.85, "waits")
    if _has(words, "take me to", "bring me to", "lead me to", "guide me to") and _first(words, scene, "place"):
        return _candidate("move", _first(words, scene, "place"), 0.8, "asks_to_be_led")
    if _has(words, "leave the party", "leave my party", "leave the group", "part ways", "go your own way", "dismiss"):
        return _candidate("party", _first(words, scene, "person"), 0.85, "party_leave")
    if _has(words, "join my party", "join the party", "join me", "come with me", "travel with me", "recruit"):
        return _candidate("party", _first(words, scene, "person"), 0.85, "party")
    lead = _find(words[:3], scene.of("person"))
    if not question and lead and lead[0].start <= 1 and _has(words, *_ORDERS):
        # "Liora, keep watch": an order to someone named first; whether they take it is the party rule's to say.
        return _candidate("order", lead[0], 0.85, "orders")

    if question:
        lead = _find(words[:3], scene.of("person"))
        if lead and lead[0].start <= 1:
            return _ask(words, scene, lead[0])
        if _has(words, *_STATUS_QUESTIONS):
            return _candidate("status", None, 0.9, "asks_status")
        if _has(words, *_LOOK_QUESTIONS):
            return _candidate("look", None, 0.85, "asks_surroundings")
        if _has(words, "look like") or (_starts(words, "what is this", "what is that") and _has(words, "for")):
            hit = _first(words, scene, "person", "creature", "item", "place")
            if hit:
                return _candidate("inspect", hit, 0.85, "asks_appearance")
        return _ask(words, scene, _addressed(words, scene))

    if _has(words, "run away", "flee", "escape", "retreat", "get away", "fall back", "run for it"):
        return _candidate("flee", None, 0.9, "flees")
    if _has(words, "defend", "block", "parry", "brace", "defensive", "raise my guard", "guard myself",
            "take cover", "shield myself", "on guard"):
        return _candidate("defend", None, 0.85, "defends")
    if _has(words, *_STATUS_WORDS) and not _has(words, "look at", "examine", "inspect", "drop", "sell", "give"):
        return _candidate("status", None, 0.9, "status")

    addressed = _addressed(words, scene)
    if addressed is None and _starts(words, *_SOCIAL) and _has(words, "him", "her", "them"):
        # "I talk to him" with several people here: the game asks who, rather than a model guessing.
        return _clarify("speech_without_listener")
    if _starts(words, "ask") and addressed is not None:
        return _ask(words, scene, addressed)

    if _starts(words, "take me to", "bring me to", "lead me to", "guide me to"):
        place = _first(words, scene, "place")
        if place:
            return _candidate("move", place, 0.85, "asks_to_be_led")
    if _starts(words, "take in", "listen", "look around", "look about", "glance around", "survey", "scan",
               "observe", "take a look", "peer", "describe the place", "describe the room", "describe where") \
            and not _first(words, scene, "person", "creature", "item"):
        return _candidate("look", None, 0.9, "looks")

    if _has(words, "rest", "sleep", "nap", "lie down", "take a break", "camp", "doze", "catch my breath"):
        return _candidate("rest", None, 0.85, "rests")

    offer = _first(words, scene, "offer")
    if _has(words, "rent", "book", "buy", "purchase", "order") or _starts(
            words, "get me", "sell me", "pay for", "i will take", "one", "two", "give me") or (
            offer is not None and _starts(words, "take", "have", "i will have") and not _has(words, "bite")):
        hit = offer or _first(words, scene, "item")
        seller = _first(words, scene, "person", here=True)
        return _candidate("buy", hit, 0.85 if hit else 0.55, "buys",
                          second_target_id=seller.entity.entity_id if seller else None)
    if offer is not None and offer.entity.here and (words[-1] == "please" or _starts(words, "a", "an", "some")):
        return _candidate("buy", offer, 0.75, "orders")
    if _starts(words, "sell", "pawn", "trade away") or _has(words, "want to sell", "sell my", "sell the"):
        return _candidate("sell", _first(words, scene, "item"), 0.85, "sells")

    if _has(words, "invite", "leave the party", "leave my party", "dismiss", "part ways"):
        return _candidate("party", _first(words, scene, "person"), 0.85, "party")
    if _has(words, "accept", "take on", "take the job", "start the quest", "begin the quest", "turn in",
            "take the quest", "sign up for"):
        hit = _first(words, scene, "quest")
        if hit or _has(words, "quest", "job", "task"):
            return _candidate("quest", hit, 0.85 if hit else 0.6, "quest")
    if _starts(words, "practice", "train", "drill", "hone", "work on") or _has(words, "practice", "train my",
                                                                                "practicing", "training"):
        return _candidate("practice", _first(words, scene, "skill"), 0.85, "practice")
    if (_starts(words, "raise", "increase", "boost") and _has(words, *_ATTRIBUTE_NAMES)) or (
            _starts(words, "learn") and not _has(words, "about", "more", "what", "how", "where", "who", "why")) or (
            _starts(words, "improve") and _has(words, "and")):
        return _candidate("grow", None, 0.85, "level_choice")  # a level's choice (progression.md)
    kind = next((kind for kind, phrases in _CHECKS if _has(words, *phrases)), "")
    if kind and not _has(words, "notice board"):
        # A try decided by a roll (checks.md): persuading someone, sneaking past, climbing, picking a lock...
        target = _first(words, scene, "person", "creature", "item", "place")
        return _candidate("check", target, 0.85, f"check:{kind}")

    if _starts(words, "give", "hand", "offer", "pass", "lend") or _has(words, "give", "hand over"):
        item = _first(words, scene, "item")
        person = _first(words, scene, "person")
        if item is None and _has(words, *_PRONOUNS):
            return _clarify("give_without_item")
        return _candidate("give", item, 0.85 if item else 0.5, "gives",
                          second_target_id=person.entity.entity_id if person else None)
    if _starts(words, "drop", "discard", "toss", "throw away", "dump", "ditch") or _has(
            words, "put down", "set down", "leave it", "leave behind", "drop", "down and leave"):
        return _candidate("drop", _first(words, scene, "item"), 0.85, "drops")
    if _has(words, "take off", "unequip", "remove my", "remove the", "put away", "sheathe", "stow", "holster"):
        return _candidate("unequip", _first(words, scene, "item"), 0.85, "unequips")
    if _starts(words, "equip", "wield", "wear", "put on", "ready", "draw", "don", "brandish") or _has(
            words, "equip", "wield", "put on"):
        return _candidate("equip", _first(words, scene, "item"), 0.85, "equips")
    if _starts(words, "take", "pick up", "grab", "collect", "loot", "snatch", "pocket") or _has(words, "pick up"):
        return _candidate("take", _first(words, scene, "item"), 0.8, "takes")
    # One of the hero's abilities, by name after a verb ("use Aimed Shot on the wolf") or first ("Aimed Shot").
    ability = _first(words, scene, "ability")
    if ability and (ability.start == 0 or _starts(words, "use", "cast", "activate", "invoke", "unleash", "perform",
                                                    "trigger", "channel", "fire off", "try")):
        foe = _first(words, scene, "creature", "person", here=True)
        return _candidate("ability", ability, 0.85, "uses_ability",
                          second_target_id=foe.entity.entity_id if foe else None)
    if _starts(words, "eat", "drink", "consume", "use", "quaff", "apply", "swallow", "sip", "chew", "hold up",
               "have a bite", "take a bite", "nibble", "taste") or _has(words, "eat", "drink", "consume", "quaff"):
        item = _first(words, scene, "item")
        if item or offer is None:
            return _candidate("use_item", item, 0.85 if item else 0.5, "uses")
        return _candidate("buy", offer, 0.7, "orders")

    if _starts(words, "attack", "fight", "strike", "hit", "stab", "slash", "shoot", "punch", "kick", "kill",
               "charge", "swing", "smite", "assault", "ambush", "slay", "shove", "tackle", "slap") or _has(
            words, "attack", "fight"):
        target = _first(words, scene, "creature", "person")
        if target is None:
            # "attack the bandit": a foe the scene list does not know (a spawned one) is the rules' to find.
            if _object_words(words):
                return _candidate("attack", None, 0.6, "attacks_unknown_target")
            return _clarify("attack_without_target")
        return _candidate("attack", target, 0.9, "attacks")

    if _has(words, "wait", "do nothing", "pass time", "pass the time", "idle", "bide", "linger", "stay put",
            "keep watch", "time pass", "while away"):
        return _candidate("wait", None, 0.85, "waits")

    if _starts(words, "go", "travel", "walk", "head", "return", "leave for", "run to", "enter", "visit",
               "make my way", "set off", "set out", "journey", "move to", "move", "leave", "hurry", "ride") or _has(
            words, "head to", "go to", "travel to", "walk to", "return to", "make my way"):
        place = _first(words, scene, "place")
        if place:
            return _candidate("move", place, 0.9, "moves")
        if _object_words(words):
            # "go outside", "head north": the travel rules know places the scene list does not name.
            return _candidate("move", None, 0.6, "moves_somewhere_unnamed")
        if _starts(words, "leave", "go") and not _first(words, scene, "person", "item"):
            return _clarify("move_without_place")

    if _starts(words, "look at", "examine", "inspect", "check", "study", "describe", "read", "look over",
               "look closely", "size up", "watch", "eye", "observe", "peer at", "stare at") or _has(
            words, "look at", "look over", "examine", "inspect", "size up", "over in my hands"):
        hit = _first(words, scene, "item", "person", "creature", "place", "offer")
        if hit:
            return _candidate("inspect", hit, 0.85, "inspects")
        return _candidate("look", None, 0.75, "looks_without_subject")
    if _starts(words, "look", "observe", "survey", "scan") or _has(words, "look around", "where am i"):
        return _candidate("look", None, 0.9, "looks")
    if _starts(words, "open", "close", "shut", "push", "pull", "lock", "unlock", "knock", "climb", "search",
               "light", "lift", "turn", "pry", "kick open"):
        return _candidate("manipulate", _first(words, scene, "item", "place"), 0.75,
                          "searches" if _starts(words, "search") else "manipulates")

    if _starts(words, "ask"):
        return _ask(words, scene, addressed)
    if addressed is not None:
        return _candidate("talk", addressed, 0.85, "talks")
    if words[0] in {"him", "her", "them", "it"} or (_has(words, "him", "her", "them", "it") and len(words) <= 4):
        return _clarify("pronoun_without_antecedent")
    if len(words) == 1 and not scene.of("person", here=True):
        return _clarify("one_word")
    # A remark with nobody named is said to whoever is here.
    present = scene.of("person", here=True)
    return IntentCandidate(
        family="talk",
        target_id=present[0].entity_id if len(present) == 1 else None,
        target_kind="person" if len(present) == 1 else None,
        confidence=0.5,
        reason="remark",
    )


__all__ = ["STATEFUL_FAMILIES", "IntentCandidate", "SceneEntity", "SceneView", "parse_command"]
