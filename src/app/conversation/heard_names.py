"""Names as speech recognition hears them (companion, 2026-11-20/21).

Recognition spells a name it does not know as it hears it: "Aphra" or "Afro" for Afra, "Jenks" for Jinx. Boosting
the call's names in the decoder helps, but a name whose first sounds an everyday word shares can still lose. A word
*sounds like* a name when the two have the same consonants and are at most about a letter in four apart; it is
*said as* a name when it is written or set off the way an address is. ``repair_heard_names`` writes such a word as
the name it stands for, and the call scene uses the same reading to tell who was addressed.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

# Spelling to sound, in order: a heard word and a name that differ only in how a sound is written match.
_SOUND_SPELLINGS: tuple[tuple[str, str], ...] = (
    (r"^kn", "n"), (r"^wr", "r"), (r"ph", "f"), (r"ck", "k"), (r"qu", "kw"), (r"x", "ks"), (r"sch", "sk"),
    (r"[sc]h", "1"), (r"th", "t"), (r"gh", "g"), (r"wh", "w"), (r"c(?=[eiy])", "s"), (r"c", "k"), (r"q", "k"),
    (r"z", "s"), (r"h", ""), (r"y(?![aeiou])", "i"), (r"(.)\1+", r"\1"),
)
# A name heard this short ("Bea", "Theo") sounds like too many everyday words to be matched by sound.
_MIN_SOUND_KEY = 4
# A name shorter than this is never one a full name is called by on its own.
_MIN_FIRST_NAME = 3
# Titles a full name may start with ("Dr Abhishek Kumar" is called Abhishek).
_NAME_TITLES = frozenset({"dr", "mr", "mrs", "ms", "mx", "miss", "sir", "dame", "lady", "lord", "prof", "professor",
                          "captain", "capt"})
_WORD = re.compile(r"[^\W\d_]+")


def _sound_spelling(word: str) -> str:
    spelled = re.sub(r"[^a-z]", "", word.lower())
    for pattern, replacement in _SOUND_SPELLINGS:
        spelled = re.sub(pattern, replacement, spelled)
    return spelled


def _sound_key(spelled: str) -> str:
    # Vowels are what recognition gets wrong most, then "s" for "sh" ("Abhisek").
    return re.sub(r"[aeiou]+", "a", spelled).replace("1", "s")


def _edit_distance(left: str, right: str) -> int:
    previous = list(range(len(right) + 1))
    for row, left_char in enumerate(left, start=1):
        current = [row]
        for column, right_char in enumerate(right, start=1):
            current.append(min(previous[column] + 1, current[column - 1] + 1,
                               previous[column - 1] + (left_char != right_char)))
        previous = current
    return previous[-1]


def sounds_like(heard: str, name: str) -> bool:
    """``heard`` is ``name`` as recognition might spell it: the same consonants, at most a vowel or so apart."""
    heard_spelled, name_spelled = _sound_spelling(heard), _sound_spelling(name)
    key = _sound_key(name_spelled)
    if len(key) < _MIN_SOUND_KEY or _sound_key(heard_spelled) != key:
        return False
    return _edit_distance(heard_spelled, name_spelled) <= max(1, len(name_spelled) // 4)


# Words said set off by commas that sound like names ("Like, I don't know" and Luke): never taken as one.
_SOUND_FILLERS = frozenset({"like", "well", "right", "sure", "maybe", "please", "okay", "anyway", "really", "nice",
                            "fine", "mine", "though", "mate", "dude", "yeah", "yes", "nope"})
_GREETINGS = frozenset({"hey", "hi", "hello", "thanks", "ok", "okay", "oh", "and"})


def said_as_name(text: str, start: int, end: int) -> bool:
    """Whether the word at ``text[start:end]`` is used as a name, not as the everyday word it may also be.

    Recognition writes a name it hears as a name ("what do you think, Aphra?"), so a capitalised word inside a
    sentence counts; so does a word set off as an address ("afro, what's yours?", "and you, afro?"). "I like
    that" never names Luke, nor "make it shorter" Mike.
    """
    word = text[start:end]
    if word.lower() in _SOUND_FILLERS:
        return False
    if re.match(r"['’]s\b", text[end:]):
        return True  # "Aphra's turn": a word is owned only as a name
    before = text[:start].rstrip()
    sentence_start = not before or before[-1] in ".!?"
    if word[0].isupper() and not sentence_start:
        return True
    previous = re.search(r"([^\W\d_]+)$", before)
    set_off_before = sentence_start or before[-1] == "," or (
        previous is not None and previous.group(1).lower() in _GREETINGS)
    after = text[end:].lstrip()
    set_off_after = not after or after[0] in ",?!"
    return set_off_before and set_off_after


def called_by(names: Iterable[str]) -> list[str]:
    """The one-word names the people ``names`` lists are called by: a one-word name, and a full name's first word."""
    words: list[str] = []
    for name in names:
        parts = _WORD.findall(name)
        if len(parts) > 1:
            parts = [part for part in parts if part.lower() not in _NAME_TITLES]
            if not parts or len(parts[0]) < _MIN_FIRST_NAME:
                continue
        if not parts:
            continue
        word = parts[0]
        if word not in words:
            words.append(word)
    return words


def repair_heard_names(text: str, names: Iterable[str]) -> str:
    """``text`` with each word said as a name and heard as one of ``names`` written as that name.

    Only a word that sounds like exactly one of the names is written over ("Jenks" for Jinx); one that sounds like
    two stays as heard, and so does an everyday word used as one ("don't jinx it", "I like that" beside Luke).
    """
    words = called_by(names)
    if not words or not text:
        return text
    pieces: list[str] = []
    kept = 0
    for found in _WORD.finditer(text):
        heard = found.group(0)
        if heard in words:
            continue
        matches = {word for word in words if heard.lower() == word.lower() or sounds_like(heard, word)}
        if len(matches) != 1 or not said_as_name(text, found.start(), found.end()):
            continue
        pieces += [text[kept:found.start()], matches.pop()]
        kept = found.end()
    return "".join(pieces) + text[kept:] if pieces else text
