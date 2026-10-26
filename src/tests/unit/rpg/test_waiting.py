"""A wait lasts as long as its words say (rules/waiting.py; the playtest: "I wait until evening" waited half an hour)."""
from __future__ import annotations

import pytest

from app.apps.rpg.rules.waiting import A_WHILE, LONGEST_WAIT, said, wait_minutes


@pytest.mark.parametrize(("text", "now", "minutes"), [
    ("I wait until evening.", 10 * 60, 9 * 60),  # 10:00 to 19:00
    ("wait till dusk", 10 * 60, 8 * 60),
    ("I wait until morning", 20 * 60, LONGEST_WAIT),  # 20:00 to 08:00 is twelve hours, the longest
    ("wait until noon", 13 * 60, A_WHILE),  # noon came an hour ago: it is noon, a while (the review)
    ("wait until dawn", 15 * 60, 15 * 60),  # until it comes, however long: 15:00 to 06:00
    ("I wait until evening", 19 * 60 + 30, A_WHILE),  # evening is here
    ("wait until tomorrow morning", 20 * 60, 12 * 60),
    ("wait until tonight", 12 * 60, 9 * 60),
    ("wait until midnight", 23 * 60, 60),
    ("I wait for three hours", 9 * 60, 180),
    ("wait 2 hours", 9 * 60, 180 - 60),
    ("I wait for 45 minutes by the well", 9 * 60, 45),
    ("wait for a few hours", 9 * 60, 180),
    ("wait a day", 9 * 60, A_WHILE),  # no time this reads: a while
    ("I wait for Seraphine", 9 * 60, A_WHILE),
    ("wait", 9 * 60, A_WHILE),
])
def test_a_wait_lasts_as_long_as_its_words_say(text: str, now: int, minutes: int) -> None:
    assert wait_minutes(text, now) == minutes


def test_its_length_reads_as_the_hero_hears_it() -> None:
    assert (said(45), said(60), said(540)) == ("45 minutes", "1 hour", "9 hours")


def test_tomorrows_time_is_the_next_days() -> None:
    assert wait_minutes("wait until tomorrow morning", 7 * 60) == 25 * 60  # not today's, an hour off
    assert wait_minutes("wait for the night watch to pass", 9 * 60) == A_WHILE  # no time of day waited for
