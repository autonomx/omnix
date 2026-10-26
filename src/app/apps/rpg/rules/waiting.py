"""How long a wait lasts (the playtest: "I wait until evening" waited half an hour, and the princess who holds court
in Valecourt each evening never came). Pure: it reads the words and the clock (docs/rpg/design/time.md)."""
from __future__ import annotations

import re

A_WHILE = 30  # a wait that names no time
LONGEST_WAIT = 12 * 60
# A time of day waited for, as the minute of the day it comes.
_UNTIL = (
    (("dawn", "daybreak", "sunrise", "first light"), 6 * 60),
    (("morning",), 8 * 60),
    (("noon", "midday"), 12 * 60),
    (("afternoon",), 14 * 60),
    (("dusk", "sunset", "sundown"), 18 * 60),
    (("evening",), 19 * 60),
    (("nightfall", "night", "tonight", "dark"), 21 * 60),
    (("midnight",), 0),
)
_NUMBERS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
            "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "a few": 3, "a couple of": 2, "several": 4, "half an": 0.5}
ALREADY = 3 * 60  # a time of day come within this long is now ("until evening" at 19:30 is a while, not a day)
_FOR = re.compile(r"\b(\d+|a few|a couple of|several|half an|an|a|one|two|three|four|five|six|seven|eight|nine|ten|"
                  r"eleven|twelve)\s+(hours?|minutes?)\b")


def wait_minutes(text: str, minute_of_day: int) -> int:
    """The minutes a wait lasts: until the time of day it names (tomorrow's, when today's has gone by), or for the
    hours or minutes it names, at most ``LONGEST_WAIT``; else ``A_WHILE``."""
    lowered = text.casefold()
    until = re.search(r"\b(?:until|till|til|for)\s+(?:the\s+|tomorrow\s+)?(\w+(?:\s\w+)?)", lowered)
    if until:
        words = until.group(1)
        for names, at in _UNTIL:
            if any(re.match(rf"{name}\b", words) for name in names):
                ahead = (at - minute_of_day) % 1440
                return A_WHILE if ahead == 0 or ahead > 1440 - ALREADY else ahead  # until it comes, however long
    counted = _FOR.search(lowered)
    if counted:
        amount = float(counted.group(1)) if counted.group(1).isdigit() else _NUMBERS[counted.group(1)]
        minutes = amount * (60 if counted.group(2).startswith("hour") else 1)
        return max(10, min(LONGEST_WAIT, int(minutes)))
    return A_WHILE


def said(minutes: int) -> str:
    """A wait's length as the hero's line says it."""
    if minutes < 60:
        return f"{minutes} minutes"
    hours = round(minutes / 60)
    return f"{hours} hour{'s' if hours != 1 else ''}"


__all__ = ["A_WHILE", "LONGEST_WAIT", "said", "wait_minutes"]
