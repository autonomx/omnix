"""What may be said: the one filter between a world's secrets and anything shown to the player or sent to a model.

A secret is a person's ``secrets`` or a lore entity's ``hidden_truth``. A sentence repeats one when it holds it
whole, holds every meaning word of a short one, or most of the words of a long one (``names_a_secret``). Text is
filtered sentence by sentence and keeps its own formatting (``sayable``); a whole campaign canon is filtered with
every secret it holds (``public_canon``), the secrets themselves kept only in their own fields. Pure.
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
_SENTENCE_BREAK = re.compile(r"((?<=[.!?])\s+)")
# Where a world keeps its secrets: the only fields a filtered canon leaves as written.
SECRET_FIELDS = frozenset({"secrets", "secret", "hidden_truth", "hidden_truths"})


def meaning_words(text: str) -> set[str]:
    """The words that carry meaning, a possessive's "'s" aside ("his daughter's memory" is about the daughter)."""
    words = (re.sub(r"'s?$", "", word) for word in _WORD.findall(text.casefold().replace("’", "'")))
    return {word for word in words if word not in _STOP and len(word) > 2}


def _secret_sentences(secrets: Iterable[str]) -> list[str]:
    """Each secret, a sentence at a time: a description may tell one sentence of a longer truth."""
    return [part.strip() for secret in secrets for part in _SENTENCE_BREAK.split(str(secret or ""))[::2] if part.strip()]


class _Secrets:
    """Secrets indexed by their words, so a canon's every sentence is checked against hundreds of them at once."""

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
        """``text`` without the sentences that repeat a secret, as written otherwise."""
        if not self._rows or not text:
            return text
        parts = _SENTENCE_BREAK.split(text)  # sentence, break, sentence, break, ...
        kept, dropped = [], False
        for index in range(0, len(parts), 2):
            if self.told_by(parts[index]):
                dropped = True
                continue
            kept.append(parts[index] + (parts[index + 1] if index + 1 < len(parts) else ""))
        return "".join(kept).strip() if dropped else text


def names_a_secret(text: str, secrets: Iterable[str]) -> bool:
    return _Secrets(secrets).told_by(text)


def sayable(text: str, secrets: Iterable[str]) -> str:
    """The sentences of ``text`` that repeat none of ``secrets``: what of an author's description may be shown or
    sent to the model."""
    return _Secrets(secrets).sayable(text)


def _held(value: Any) -> Iterable[str]:
    """Every secret a canon holds, wherever an entity, a character or a place keeps one."""
    if isinstance(value, Mapping):
        for key, item in value.items():
            if key in SECRET_FIELDS:
                yield from ([item] if isinstance(item, str) else [str(row) for row in item or () if row])
            else:
                yield from _held(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _held(item)


def public_canon(canon: Mapping[str, Any]) -> dict[str, Any]:
    """``canon`` with every sentence that tells one of its secrets taken out of everything else: descriptions, facts,
    pages, cards (the review: a world written as lore keeps each entity's hidden truth in its description, and the
    lore panel and the narrator's evidence showed it). The secrets stay in their own fields, for the rules that keep
    them."""
    secrets = _Secrets(_held(canon))
    if not secrets:
        return dict(canon)

    def clean(value: Any, key: str = "") -> Any:
        if key in SECRET_FIELDS:
            return value
        if isinstance(value, str):
            return secrets.sayable(value) if " " in value else value
        if isinstance(value, Mapping):
            return {name: clean(item, str(name)) for name, item in value.items()}
        if isinstance(value, list):
            return [clean(item) for item in value]
        return value

    return clean(dict(canon))


__all__ = ["SECRET_FIELDS", "meaning_words", "names_a_secret", "public_canon", "sayable"]
