"""Non-mutating hypothetical and counterfactual world-resolution support."""
from __future__ import annotations

import re
from functools import wraps
from typing import Any

HYPOTHETICAL_INTENT = "hypothetical_counterfactual"


def looks_like_hypothetical_input(player_input: str) -> bool:
    text = _norm(player_input)
    if not text:
        return False
    return bool(
        re.search(r"\b(if|suppose|what if|imagine)\b", text)
        or re.search(r"\bwould you\b", text)
        or re.search(r"\bif i became\b", text)
        or re.search(r"\bif .* attacked\b", text)
    )


def install_hypothetical_world_resolution() -> None:
    """Install additive hypothetical classification for interpretive world resolution."""

    from app.rpg.session import interpretive_adjudication as adjudication

    sentinel = "_omnix_hypothetical_world_resolution_installed"
    if getattr(adjudication, sentinel, False):
        return

    adjudication.INTENT_FAMILIES[HYPOTHETICAL_INTENT] = "hypothetical"
    original_classify = adjudication.classify_interpretive_intent
    original_line = adjudication._line_for_intent
    original_narration = adjudication._narration_for_intent

    @wraps(original_classify)
    def classify_with_hypothetical(*args: Any, **kwargs: Any) -> str:
        player_input = _s(kwargs.get("player_input"))
        if not player_input and args:
            player_input = _s(args[0])
        if looks_like_hypothetical_input(player_input):
            return HYPOTHETICAL_INTENT
        return original_classify(*args, **kwargs)

    @wraps(original_line)
    def line_with_hypothetical(*args: Any, **kwargs: Any) -> str:
        intent = _s(kwargs.get("intent"))
        if intent == HYPOTHETICAL_INTENT:
            return (
                "I can answer that as a possibility, not as a fact that has happened. "
                "I will keep it separate from what is known here and now."
            )
        return original_line(*args, **kwargs)

    @wraps(original_narration)
    def narration_with_hypothetical(*args: Any, **kwargs: Any) -> str:
        intent = _s(kwargs.get("intent"))
        speaker = _s(kwargs.get("speaker") or "The answer")
        if intent == HYPOTHETICAL_INTENT:
            return f"{speaker} treats the question as a possibility, not a change to the world."
        return original_narration(*args, **kwargs)

    adjudication.classify_interpretive_intent = classify_with_hypothetical
    adjudication._line_for_intent = line_with_hypothetical
    adjudication._narration_for_intent = narration_with_hypothetical
    setattr(adjudication, sentinel, True)


def _norm(value: Any) -> str:
    return _s(value).casefold().strip()


def _s(value: Any) -> str:
    return str(value) if value is not None else ""
