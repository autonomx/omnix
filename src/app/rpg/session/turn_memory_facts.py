from __future__ import annotations

import re

from app.rpg.session.turn_memory_common import s

_TRAIL_NAME_RE = re.compile(
    r"\b(?:my\s+)?trail\s+name\s+is\s+([A-Za-z][A-Za-z0-9' -]{0,40})",
    re.IGNORECASE,
)
_NAME_RE = re.compile(r"\bmy\s+name\s+is\s+([A-Za-z][A-Za-z0-9' -]{0,40})", re.IGNORECASE)


def _clean_fact(value: str) -> str:
    text = value.strip().strip(".?!,;:\"'")
    lower = text.lower()
    cut = len(text)
    for stop in (" and ", " but ", " because ", " when ", " while "):
        index = lower.find(stop)
        if index >= 0:
            cut = min(cut, index)
    return text[:cut].strip().strip(".?!,;:\"'")[:48]


def extract_player_memory_facts(player_input: str) -> list[dict[str, str]]:
    facts: list[dict[str, str]] = []
    for regex, key in ((_TRAIL_NAME_RE, "trail_name"), (_NAME_RE, "name")):
        match = regex.search(s(player_input))
        if match and (value := _clean_fact(match.group(1))):
            facts.append({"type": "identity_alias", "subject": "player", "key": key, "value": value})
    return facts
