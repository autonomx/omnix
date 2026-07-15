"""Route direct-dialogue publication through the Unified Narrative Engine."""
from __future__ import annotations

from functools import wraps
from typing import Any

from .narrative_engine_bridge import canonicalize_direct_dialogue_result

_FIRST_CALL_SENTINEL = "_omnix_narrative_engine_direct_dialogue"
_FALLBACK_SENTINEL = "_omnix_narrative_engine_dialogue_fallback"


def _session_id(session: dict[str, Any]) -> str:
    manifest = session.get("manifest") if isinstance(session.get("manifest"), dict) else {}
    return str(
        manifest.get("session_id")
        or manifest.get("id")
        or session.get("session_id")
        or session.get("id")
        or "runtime"
    )


def _install_first_call_wrapper() -> None:
    from app.rpg.session import first_call_dialogue

    original = first_call_dialogue.build_non_stateful_dialogue_result
    if getattr(original, _FIRST_CALL_SENTINEL, False):
        return

    @wraps(original)
    def wrapped(*args: Any, **kwargs: Any):
        result = original(*args, **kwargs)
        if isinstance(result, dict) and result.get("consumed") is True:
            session = kwargs.get("session") if isinstance(kwargs.get("session"), dict) else {}
            result = canonicalize_direct_dialogue_result(
                result,
                session_id=_session_id(session),
                player_input=str(kwargs.get("player_input") or ""),
            )
        return result

    setattr(wrapped, _FIRST_CALL_SENTINEL, True)
    first_call_dialogue.build_non_stateful_dialogue_result = wrapped


def install_interactive_direct_dialogue_cutover(interactive_module: Any | None = None) -> None:
    """Install one-way wrappers on first-call and safe-fallback publishers."""

    _install_first_call_wrapper()
    if interactive_module is None:
        return
    first_call = interactive_module.build_non_stateful_dialogue_result
    if not getattr(first_call, _FIRST_CALL_SENTINEL, False):
        from app.rpg.session import first_call_dialogue

        interactive_module.build_non_stateful_dialogue_result = first_call_dialogue.build_non_stateful_dialogue_result

    original_fallback = getattr(interactive_module, "_safe_dialogue_fallback_result", None)
    if not callable(original_fallback) or getattr(original_fallback, _FALLBACK_SENTINEL, False):
        return

    @wraps(original_fallback)
    def wrapped_fallback(*args: Any, **kwargs: Any):
        result = original_fallback(*args, **kwargs)
        session = kwargs.get("session") if isinstance(kwargs.get("session"), dict) else {}
        return canonicalize_direct_dialogue_result(
            result,
            session_id=_session_id(session),
            player_input=str(kwargs.get("player_input") or ""),
        )

    setattr(wrapped_fallback, _FALLBACK_SENTINEL, True)
    interactive_module._safe_dialogue_fallback_result = wrapped_fallback
