"""What may be said: the one filter between a world's secrets and anything shown to the player or sent to a model.

A secret is a person's ``secrets`` or a lore entity's ``hidden_truth``. Two tests, for two kinds of text:

- A line a model wrote may paraphrase a secret: it repeats one when it holds it whole, every meaning word of a short
  one, or most of the words of a long one (``names_a_secret``, ``sayable``: the dialogue plan's).
- An author's own text tells a secret in the secret's own words: a sentence does when it repeats a run of five of its
  words in order, or a short one whole (``without_secrets``, ``public_canon``). Sharing a few nouns with a secret is
  no telling (the review: the starter town's quest objective, "find ... the old quarry, and what the sealed crates
  carry", shares them with the innkeeper's secret).

Text is filtered sentence by sentence (a line break ends one too) and keeps its own formatting. A whole campaign canon
is filtered with every secret its things hold, the secrets kept only in their own fields. Pure.
"""
from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable, Mapping
from typing import Any

_WORD = re.compile(r"[a-z0-9']+")
_STOP = frozenset("a an the and or of to in on at for with about from is are was were be you your me my i we "
                  "what who where when why how do does did can could would will tell ask know heard any some this "
                  "that there here it its she he his her him hers they them their has have had not no".split())
_SENTENCE_BREAK = re.compile(r"((?<=[.!?])\s+|\s*\n\s*)")
# Where a world keeps its secrets: the only fields a filtered canon leaves as written.
SECRET_FIELDS = frozenset({"secrets", "secret", "hidden_truth", "hidden_truths"})
# A row that is a thing of the world (a person, a place, an entity): only such a row's secret fields hold secrets
# (the review: a search index's "secrets" entry, a list of card ids, is no secret).
_THING_KEYS = ("id", "name", "npc_id", "entity_id")
RUN = 5  # the words in order an author's sentence repeats of a secret to tell it


def meaning_words(text: str) -> set[str]:
    """The words that carry meaning, a possessive's "'s" aside ("his daughter's memory" is about the daughter)."""
    words = (re.sub(r"'s?$", "", word) for word in _WORD.findall(text.casefold().replace("’", "'")))
    return {word for word in words if word not in _STOP and len(word) > 2}


def _tokens(text: str) -> list[str]:
    return [re.sub(r"'s?$", "", word) for word in _WORD.findall(text.casefold().replace("’", "'"))]


def _secret_sentences(secrets: Iterable[str]) -> list[str]:
    """Each secret, a sentence at a time: a description may tell one sentence of a longer truth."""
    return [part.strip() for secret in secrets for part in _SENTENCE_BREAK.split(str(secret or ""))[::2] if part.strip()]


def _without(text: str, told: Any) -> str:
    """``text`` without the sentences ``told`` says tell a secret, as written otherwise."""
    parts = _SENTENCE_BREAK.split(text)  # sentence, break, sentence, break, ...
    kept, dropped = [], False
    for index in range(0, len(parts), 2):
        if told(parts[index]):
            dropped = True
            continue
        kept.append(parts[index] + (parts[index + 1] if index + 1 < len(parts) else ""))
    return "".join(kept).strip() if dropped else text


class _Secrets:
    """Secrets indexed by their words, so a sentence is checked against hundreds of them at once (a model's line)."""

    def __init__(self, secrets: Iterable[str]) -> None:
        self._rows = [(secret.casefold(), meaning_words(secret)) for secret in dict.fromkeys(_secret_sentences(secrets))]
        self._by_word: dict[str, list[int]] = {}
        for index, (_, words) in enumerate(self._rows):
            for word in words:
                self._by_word.setdefault(word, []).append(index)
        self._wordless = [index for index, (_, words) in enumerate(self._rows) if not words]

    def __bool__(self) -> bool:
        return bool(self._rows)

    def told_by(self, sentence: str) -> bool:
        """Whether ``sentence`` repeats a secret: whole; every word of a short one ("the shrine word is Heronglass"
        in "keep the shrine word Heronglass"); or most of the words of one with four or more."""
        lowered, said = sentence.casefold(), meaning_words(sentence)
        shared = Counter(index for word in said for index in self._by_word.get(word, ()))
        for index in [*shared, *self._wordless]:
            secret, words = self._rows[index]
            overlap = shared.get(index, 0)
            if secret in lowered or (words and len(words) < 4 and overlap == len(words)) or (
                    len(words) >= 4 and overlap >= max(4, len(words) * 2 // 3)):
                return True
        return False

    def sayable(self, text: str) -> str:
        return _without(text, self.told_by) if self._rows and text else text


class _Told:
    """Secrets as the runs of their own words, to find an author's sentence that tells one (strict)."""

    def __init__(self, secrets: Iterable[str]) -> None:
        self._runs: set[tuple[str, ...]] = set()
        self._short: list[str] = []
        for secret in dict.fromkeys(_secret_sentences(secrets)):
            tokens = _tokens(secret)
            if len(tokens) < RUN:
                if tokens:
                    self._short.append(" ".join(tokens))
                continue
            for start in range(len(tokens) - RUN + 1):
                run = tuple(tokens[start:start + RUN])
                if sum(word not in _STOP and len(word) > 2 for word in run) >= 2:  # not "at the end of the"
                    self._runs.add(run)

    def __bool__(self) -> bool:
        return bool(self._runs or self._short)

    def told_by(self, sentence: str) -> bool:
        tokens = _tokens(sentence)
        if any(tuple(tokens[start:start + RUN]) in self._runs for start in range(len(tokens) - RUN + 1)):
            return True
        joined = f" {' '.join(tokens)} "
        return any(f" {short} " in joined for short in self._short)

    def without(self, text: str) -> str:
        if not text or " " not in text or not self.told_by(text):  # most text tells nothing: one pass, unchanged
            return text
        return _without(text, self.told_by)


def names_a_secret(text: str, secrets: Iterable[str]) -> bool:
    return _Secrets(secrets).told_by(text)


def sayable(text: str, secrets: Iterable[str]) -> str:
    """The sentences of ``text`` that repeat none of ``secrets``, paraphrased or not: what of a description may go
    into a speaker's own line."""
    return _Secrets(secrets).sayable(text)


def without_secrets(text: str, secrets: Iterable[str]) -> str:
    """The sentences of an author's ``text`` that tell none of ``secrets`` in their own words."""
    return _Told(secrets).without(text)


def secrets_held(value: Any) -> Iterable[str]:
    """Every secret a canon holds, wherever one of its things (an entity, a character, a place) keeps one."""
    if isinstance(value, Mapping):
        # A thing names itself in text ("name": "Mara Vey"); a search index's "name" is a list of card ids.
        thing = any(isinstance(value.get(key), str) for key in _THING_KEYS)
        for key, item in value.items():
            if key in SECRET_FIELDS:
                if thing:
                    yield from ([item] if isinstance(item, str) else [str(row) for row in item or () if row])
            else:
                yield from secrets_held(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from secrets_held(item)


def public_canon(canon: Mapping[str, Any]) -> dict[str, Any]:
    """``canon`` with every sentence that tells one of its secrets taken out of everything else: descriptions, facts,
    pages, cards (the review: a world written as lore keeps each entity's hidden truth in its description, and the
    lore panel and the narrator's evidence showed it). The secrets stay in their own fields, for the rules that keep
    them."""
    told = _Told(secrets_held(canon))
    if not told:
        return dict(canon)

    def clean(value: Any, key: str = "") -> Any:
        if key in SECRET_FIELDS:
            return value
        if isinstance(value, str):
            return told.without(value)
        if isinstance(value, Mapping):
            return {name: clean(item, str(name)) for name, item in value.items()}
        if isinstance(value, list):
            return [clean(item) for item in value]
        return value

    return clean(dict(canon))


__all__ = ["SECRET_FIELDS", "meaning_words", "names_a_secret", "public_canon", "sayable", "secrets_held",
           "without_secrets"]
