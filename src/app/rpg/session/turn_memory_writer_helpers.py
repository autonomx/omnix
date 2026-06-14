from __future__ import annotations

import re
from typing import Any, Mapping

from app.rpg.session.turn_memory_common import d, first, s

_ALIAS_RE = re.compile(
    r"\b(?:my\s+)?(?P<key>trail\s+name|name)\s+is\s+"
    r"(?P<value>[A-Za-z][A-Za-z0-9' -]{0,40})",
    re.I,
)
_STOP_RE = re.compile(r"\s+(?:and|but|because|when|while)\s+")


def memory_facts(text: str) -> list[dict[str, str]]:
    match = _ALIAS_RE.search(s(text))
    if not match:
        return []
    value = _STOP_RE.split(match.group("value"))[0]
    value = value.strip().strip(".?!,;:\"'")[:48]
    key = "trail_name" if "trail" in match.group("key").lower() else "name"
    if not value:
        return []
    return [{
        "type": "identity_alias",
        "subject": "player",
        "key": key,
        "value": value,
    }]


def memory_npc(result: Mapping[str, Any] | None) -> dict[str, str]:
    result_dict, nested = d(result), d(d(result).get("result"))
    for candidate in (d(result_dict.get("npc")), d(nested.get("npc"))):
        speaker = first(candidate.get("speaker"), candidate.get("name"))
        npc_id = first(candidate.get("id"), candidate.get("npc_id"))
        if speaker or npc_id:
            return {
                "id": npc_id or f"npc:{speaker.lower()}",
                "speaker": speaker,
                "line": first(candidate.get("line"), candidate.get("text")),
            }
    return {"id": "", "speaker": "", "line": ""}
