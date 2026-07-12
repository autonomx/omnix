"""Replay append-only interaction events whenever a durable session is loaded."""
from __future__ import annotations

from functools import wraps
from typing import Any, Callable

from .interaction_event_store import load_and_replay_interaction_events

_SENTINEL = "_omnix_interaction_event_store_hook_installed"


def install_interaction_event_store_hook() -> None:
    from app.rpg.session import service

    if getattr(service, _SENTINEL, False):
        return

    original_load_session: Callable[..., Any] = service.load_session

    @wraps(original_load_session)
    def load_session_with_interaction_replay(session_id: str, *args: Any, **kwargs: Any) -> Any:
        session = original_load_session(session_id, *args, **kwargs)
        if not isinstance(session, dict):
            return session
        return load_and_replay_interaction_events(session_id, session)

    service.load_session = load_session_with_interaction_replay
    setattr(service, _SENTINEL, True)
