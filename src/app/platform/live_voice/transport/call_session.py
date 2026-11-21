"""A call's chat as the caller's tenant sees it, and as one of its members sees it.

The avatar websocket, the members' idle loops and the speech proxy's call roster all name a chat the browser sent;
each reads it through the tenant-scoped chat store, so a chat that is not the caller's is None.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any


def load_session(chat_store_factory: Callable[[], Any], session_id: str) -> Any:
    """The session, as the caller's tenant sees it (None when it is not theirs)."""
    return chat_store_factory().get_session(session_id)


def speaker_session(session: Any, speaker_id: str) -> Any:
    """The session as the speaking member sees it (the host's, or a seated guest's); None for anyone else."""
    from app.platform.chat.contracts import speaker_view

    return speaker_view(session, speaker_id)


__all__ = ["load_session", "speaker_session"]
