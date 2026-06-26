"""Diegetic fallback for meaningful direct-dialogue input.

The generic clarification line remains available for true parse noise or client
payload corruption. Meaningful roleplay should receive an in-world response.
"""
from __future__ import annotations

from functools import wraps
from typing import Any

_HOOK_SENTINEL = "_omnix_diegetic_fallback_hook_installed"
_GENERIC_CLARIFICATION_LINE = "Ask that plainly again, and I will answer as best I can."
_CLIENT_CORRUPTION_MARKERS = {"object object", "undefined", "null"}


def install_diegetic_fallback_hook() -> None:
    from app.rpg.session import interactive_first_call_runtime as runtime

    if getattr(runtime, _HOOK_SENTINEL, False):
        return

    original_fallback = runtime._safe_dialogue_fallback_line

    @wraps(original_fallback)
    def patched_fallback(*, speaker: str, profile: dict[str, Any], player_input: str) -> tuple[str, str]:
        topic, line = original_fallback(speaker=speaker, profile=profile, player_input=player_input)
        if line != _GENERIC_CLARIFICATION_LINE:
            return topic, line
        diegetic_topic, diegetic_line = _diegetic_line(speaker=speaker, profile=profile, player_input=player_input)
        if diegetic_line:
            return diegetic_topic, diegetic_line
        return topic, line

    runtime._safe_dialogue_fallback_line = patched_fallback
    setattr(runtime, _HOOK_SENTINEL, True)


def _diegetic_line(*, speaker: str, profile: dict[str, Any], player_input: str) -> tuple[str, str]:
    text = _s(player_input).casefold()
    normalized = _norm(text)
    if not _looks_like_meaningful_text(normalized):
        return "", ""

    speaker_name = _s(speaker).strip() or "NPC"
    role = _s(_d(profile).get("role") or _d(profile).get("occupation") or _d(profile).get("title")).strip()
    role_phrase = f" as {role}" if role else ""

    if any(term in text for term in ("trouble", "troubles", "problem", "problems", "concern", "concerns", "wrong", "worry", "worries")):
        return (
            "concern_inquiry",
            f"I can answer that{role_phrase}, but I will not turn guesses into facts. There have been enough concerns nearby that I would listen carefully, ask what you want to know, and separate rumor from what I have seen.",
        )
    if any(term in text for term in ("rumor", "rumour", "news", "gossip", "heard", "word")):
        return (
            "rumor_inquiry",
            f"I hear pieces of news{role_phrase}, but I trust only some of them. Ask about a person, place, or road, and I will tell you what sounds solid.",
        )
    if any(term in text for term in ("think", "thought", "opinion", "feel")):
        return (
            "opinion_question",
            f"My opinion{role_phrase} is worth only what I have lived and heard, but I can give it plainly if you name the matter.",
        )
    if any(term in text for term in ("where", "place", "road", "town", "tavern", "local")):
        return (
            "local_knowledge",
            f"I can tell you what I know of the local roads and people{role_phrase}, but I will keep it to what belongs in this place and this moment.",
        )
    if any(term in text for term in ("jump", "climb", "lift", "run", "dance", "prove", "show me")):
        return (
            "capability_response",
            "I can answer in-world, but I will not pretend a feat happened just because it was requested. Say what outcome you want, and I will tell you what seems possible here.",
        )
    if any(term in text for term in ("sing", "nonsense", "odd", "strange")):
        return (
            "diegetic_reaction",
            f"{speaker_name} treats that as something happening in the room, not as a command failure. The moment is awkward, but it remains part of the world.",
        )
    if any(term in text for term in ("i ", "you ", "we ", "tell ", "ask ", "say ")):
        return (
            "diegetic_response",
            "I can answer that as something said or attempted here, but I will keep it grounded in what is known and possible rather than inventing a new fact.",
        )
    return (
        "information_inquiry",
        f"{speaker_name} considers the moment before answering from what they know, not from guesswork. Make the next part concrete, and they will answer directly.",
    )


def _looks_like_meaningful_text(text: str) -> bool:
    if not text or text in _CLIENT_CORRUPTION_MARKERS:
        return False
    if len(text) < 3:
        return False
    alpha = sum(1 for char in text if char.isalpha())
    return alpha >= max(3, len(text) // 3)


def _norm(value: Any) -> str:
    import re

    return re.sub(r"[^a-z0-9]+", " ", _s(value).casefold()).strip()


def _d(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _s(value: Any) -> str:
    return str(value) if value is not None else ""
