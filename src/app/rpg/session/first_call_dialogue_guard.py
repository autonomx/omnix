"""Guard first-call NPC dialogue against placeholder/meta text leaks."""
from __future__ import annotations

from copy import deepcopy
from functools import wraps
from typing import Any

_PLACEHOLDER_MARKERS = (
    "npc line will be filled",
    "filled upon runtime resolution",
    "intent is to ask",
    "runtime resolution",
    "placeholder",
    "todo",
)


def is_placeholder_npc_line(value: Any) -> bool:
    text = str(value or "").casefold().strip()
    if not text:
        return False
    bracketed = text.startswith("[") and text.endswith("]")
    return bracketed and any(marker in text for marker in _PLACEHOLDER_MARKERS)


def install_first_call_dialogue_placeholder_guard() -> None:
    """Reject meta placeholder dialogue before it reaches the visible UI."""

    from app.rpg.session import first_call_dialogue as target

    sentinel = "_omnix_first_call_dialogue_placeholder_guard_installed"
    if getattr(target, sentinel, False):
        return

    original = target.choose_first_call_visible_response

    @wraps(original)
    def guarded(*args: Any, **kwargs: Any) -> dict[str, Any]:
        selected = original(*args, **kwargs)
        if not _selection_has_placeholder_line(selected):
            return selected
        copied = deepcopy(selected)
        source = str(copied.get("source") or "first_call_dialogue_v1")
        reason = f"{source}:placeholder_npc_line"
        return {
            "consumable": False,
            "reason": "no_safe_non_stateful_visible_response",
            "rejection_reasons": [reason],
            "rejected_visible_response": deepcopy(copied.get("visible_response") or {}),
            "source": "first_call_dialogue_placeholder_guard_v1",
        }

    target.choose_first_call_visible_response = guarded
    setattr(target, sentinel, True)


def _selection_has_placeholder_line(selection: Any) -> bool:
    if not isinstance(selection, dict) or not selection.get("consumable"):
        return False
    visible = selection.get("visible_response") if isinstance(selection.get("visible_response"), dict) else {}
    npc = visible.get("npc") if isinstance(visible.get("npc"), dict) else {}
    line = npc.get("line") or (selection.get("npc") if isinstance(selection.get("npc"), dict) else {}).get("line")
    return is_placeholder_npc_line(line)
