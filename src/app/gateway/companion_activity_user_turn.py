"""Install Companion Activity enrichment at the authoritative accepted Chat-turn boundary."""
from __future__ import annotations

from functools import wraps

from app.chat.character_store import _CharacterSessionMixin
from app.desktop_companion.chat_activity import record_accepted_chat_activity

_HOOK_MARKER = "_omnix_companion_activity_user_turn_hook_installed"


def install_companion_activity_user_turn_hook() -> None:
    """Record explicit user activity evidence for every Character-aware Chat store."""

    if getattr(_CharacterSessionMixin, _HOOK_MARKER, False):
        return

    original_begin = _CharacterSessionMixin.begin_user_message
    original_append = _CharacterSessionMixin.append_user_message

    @wraps(original_begin)
    def begin_user_message(self, session_id, request, **kwargs):
        result = original_begin(self, session_id, request, **kwargs)
        if result is not None:
            session, user_message = result
            record_accepted_chat_activity(session, user_message)
        return result

    @wraps(original_append)
    def append_user_message(self, session_id, request, **kwargs):
        result = original_append(self, session_id, request, **kwargs)
        if result is not None:
            session, user_message = result
            record_accepted_chat_activity(session, user_message)
        return result

    _CharacterSessionMixin.begin_user_message = begin_user_message
    _CharacterSessionMixin.append_user_message = append_user_message
    setattr(_CharacterSessionMixin, _HOOK_MARKER, True)


__all__ = ["install_companion_activity_user_turn_hook"]
