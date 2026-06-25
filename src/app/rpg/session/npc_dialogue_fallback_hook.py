"""Small safe-dialogue fallback improvements for addressed NPC questions."""
from __future__ import annotations

from functools import wraps
from typing import Any

_HOOK_SENTINEL = "_omnix_npc_dialogue_fallback_hook_installed"


def install_npc_dialogue_fallback_hook() -> None:
    from app.rpg.session import interactive_first_call_runtime as runtime

    if getattr(runtime, _HOOK_SENTINEL, False):
        return

    original = runtime._safe_dialogue_fallback_line

    @wraps(original)
    def patched_safe_dialogue_fallback_line(*, speaker: str, profile: dict[str, Any], player_input: str) -> tuple[str, str]:
        text = str(player_input or "").casefold()
        speaker_text = str(speaker or "").strip()
        if _is_trouble_inquiry(text):
            if speaker_text.casefold() == "bran":
                return (
                    "trouble_inquiry",
                    "Trouble comes through a tavern door in small boots and heavy ones alike. Lately I have heard too many mutters about rough hands on the road, and too few guards with time to listen.",
                )
            return (
                "trouble_inquiry",
                "There has been some trouble lately, though I would rather speak plainly about what I know than dress it up as rumor.",
            )
        return original(speaker=speaker, profile=profile, player_input=player_input)

    runtime._safe_dialogue_fallback_line = patched_safe_dialogue_fallback_line
    setattr(runtime, _HOOK_SENTINEL, True)


def _is_trouble_inquiry(text: str) -> bool:
    if not text:
        return False
    trouble_terms = (
        "any trouble",
        "any troubles",
        "trouble lately",
        "troubles lately",
        "trouble recently",
        "troubles recently",
        "problems lately",
        "problems recently",
        "anything wrong",
        "anything happened",
        "what's wrong",
        "what is wrong",
    )
    return any(term in text for term in trouble_terms)
