"""Auditable pronunciation overlay. Source text is never modified in place."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from .hashing import object_hash


SPEECH_PLAN_VERSION = "audiobook-speech-v1"
_SMALL = (
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
    "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen",
    "seventeen", "eighteen", "nineteen",
)
_TENS = ("", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety")
_MONTHS = ("", "January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December")
_ORDINAL = {1: "first", 2: "second", 3: "third", 4: "fourth", 5: "fifth", 6: "sixth", 7: "seventh", 8: "eighth", 9: "ninth", 10: "tenth", 11: "eleventh", 12: "twelfth", 13: "thirteenth", 14: "fourteenth", 15: "fifteenth", 16: "sixteenth", 17: "seventeenth", 18: "eighteenth", 19: "nineteenth", 20: "twentieth", 21: "twenty-first", 22: "twenty-second", 23: "twenty-third", 24: "twenty-fourth", 25: "twenty-fifth", 26: "twenty-sixth", 27: "twenty-seventh", 28: "twenty-eighth", 29: "twenty-ninth", 30: "thirtieth", 31: "thirty-first"}


@dataclass(frozen=True, slots=True)
class Transformation:
    rule: str
    source_start: int
    source_end: int
    source: str
    spoken: str


@dataclass(frozen=True, slots=True)
class SpeechPlan:
    source_text: str
    tts_input_text: str
    transformations: tuple[Transformation, ...]
    version: str
    hash: str


def _number(value: int) -> str:
    if value < 20:
        return _SMALL[value]
    if value < 100:
        tens, remainder = divmod(value, 10)
        return _TENS[tens] + (f"-{_SMALL[remainder]}" if remainder else "")
    if value < 1000:
        hundreds, remainder = divmod(value, 100)
        return _SMALL[hundreds] + " hundred" + (f" {_number(remainder)}" if remainder else "")
    if value < 10000:
        thousands, remainder = divmod(value, 1000)
        return _SMALL[thousands] + " thousand" + (f" {_number(remainder)}" if remainder else "")
    return str(value)


def _date(match: re.Match[str]) -> str | None:
    try:
        parsed = date.fromisoformat(match.group())
    except ValueError:
        return None
    return f"{_MONTHS[parsed.month]} {_ORDINAL[parsed.day]}, {_number(parsed.year)}"


def _currency(match: re.Match[str]) -> str:
    dollars = int(match.group(1).replace(",", ""))
    cents = int((match.group(2) or "").ljust(2, "0"))
    value = f"{_number(dollars)} {'dollar' if dollars == 1 else 'dollars'}"
    if cents:
        value += f" and {_number(cents)} {'cent' if cents == 1 else 'cents'}"
    return value


_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_CURRENCY = re.compile(r"\$(\d[\d,]*)(?:\.(\d{1,2}))?\b")
_ABBREVIATION = re.compile(r"\b(?:Dr|Mr|Mrs|Ms|Prof|St)\.", re.IGNORECASE)
_ABBREVIATIONS = {"dr": "Doctor", "mr": "Mister", "mrs": "Missus", "ms": "Miss", "prof": "Professor", "st": "Saint"}
_NUMBER = re.compile(r"\b\d{1,4}\b")
_ACRONYM = re.compile(r"\b[A-Z]{2,5}\b")
_ROMAN = re.compile(r"(?<=Chapter )\b[IVXLCDM]+\b")


def build_speech_plan(source_text: str, *, overrides: dict[str, str] | None = None) -> SpeechPlan:
    """Choose non-overlapping substitutions against immutable source offsets."""
    rules: list[tuple[str, re.Pattern[str], object]] = []
    for term, spoken in sorted((overrides or {}).items(), key=lambda item: (-len(item[0]), item[0])):
        if not term or not spoken:
            raise ValueError("pronunciation terms and spoken forms must be non-empty")
        rules.append(("override", re.compile(rf"(?<!\w){re.escape(term)}(?!\w)"), spoken))
    rules.extend([
        ("date", _DATE, _date),
        ("currency", _CURRENCY, _currency),
        ("abbreviation", _ABBREVIATION, lambda m: _ABBREVIATIONS[m.group()[:-1].lower()]),
        ("roman_numeral", _ROMAN, lambda m: _number(_roman_value(m.group()))),
        ("number", _NUMBER, lambda m: _number(int(m.group()))),
        ("acronym", _ACRONYM, lambda m: " ".join(m.group())),
    ])
    candidates: list[Transformation] = []
    for rule, pattern, replacement in rules:
        for match in pattern.finditer(source_text):
            spoken = replacement(match) if callable(replacement) else replacement
            if spoken and spoken != match.group():
                candidates.append(Transformation(rule, match.start(), match.end(), match.group(), str(spoken)))
    # Earlier rules win at the same start. This keeps user overrides authoritative.
    candidates.sort(key=lambda item: (item.source_start, next(i for i, rule in enumerate(rules) if rule[0] == item.rule), -(item.source_end - item.source_start)))
    selected: list[Transformation] = []
    cursor = 0
    for item in candidates:
        if item.source_start >= cursor:
            selected.append(item)
            cursor = item.source_end
    pieces: list[str] = []
    cursor = 0
    for item in selected:
        pieces.extend((source_text[cursor:item.source_start], item.spoken))
        cursor = item.source_end
    pieces.append(source_text[cursor:])
    tts_text = "".join(pieces)
    plan_hash = object_hash({"version": SPEECH_PLAN_VERSION, "tts_input_text": tts_text,
                             "transformations": [(item.rule, item.source_start, item.source_end, item.spoken) for item in selected]})
    return SpeechPlan(source_text, tts_text, tuple(selected), SPEECH_PLAN_VERSION, plan_hash)


def _roman_value(value: str) -> int:
    values = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
    total = 0
    previous = 0
    for character in reversed(value):
        current = values[character]
        total += -current if current < previous else current
        previous = current
    return total
