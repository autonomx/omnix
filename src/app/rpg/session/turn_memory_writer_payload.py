from __future__ import annotations

from copy import deepcopy
from typing import Any


def written_payload(
    turn: dict[str, Any],
    dialogue: dict[str, Any] | None,
    facts: list[dict[str, str]],
) -> dict[str, Any]:
    return {
        "recent_turn": deepcopy(turn),
        "dialogue_memory": deepcopy(dialogue),
        "facts": deepcopy(facts),
    }
