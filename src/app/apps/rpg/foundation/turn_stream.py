"""A turn's events, in order, for the play screen's stream (RQ-6.2; roadmap §4.7).

The turn route publishes what happens to a submission as it happens: ``accepted`` when the turn is taken,
``committed`` when its unit of work commits, ``outcome`` (the turn's TurnOutcome, so the outcome card renders at
once), ``narration.delta`` as the narrative writer publishes its draft (the text so far), ``narration.final`` when
the narrative response is inserted, and ``error`` when the turn or its narration fails. The stream route replays a
submission's events after the client's last event id and waits for the rest, so a reconnect resumes.

Events are display transport, never game state: like the narration drafts they live in this process's memory for
minutes and are scoped to the user and workspace that submitted the turn. What a client missed (another process,
an expired stream) is in the campaign itself: the turn's response and the narration table.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Iterator

_TTL_SECONDS = 600.0
_MAX_STREAMS = 256
TERMINAL = frozenset({"narration.final", "error"})

StreamKey = tuple[str, str, str, str]  # user, workspace, session, submission


@dataclass
class _Stream:
    events: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    updated: float = 0.0

    @property
    def done(self) -> bool:
        return bool(self.events) and self.events[-1][0] in TERMINAL


_STREAMS: dict[StreamKey, _Stream] = {}
_CHANGED = threading.Condition()


def stream_key(session_id: str, submission_id: str) -> StreamKey | None:
    """The stream of ``submission_id`` for the current user and workspace; ``None`` outside a tenant."""
    from app.runtime.tenant_context import current_tenant

    try:
        tenant = current_tenant()
    except RuntimeError:
        return None
    if not session_id or not submission_id:
        return None
    return (tenant.user_id, tenant.workspace_id, session_id, submission_id)


def _prune(now: float) -> None:
    for key in [key for key, stream in _STREAMS.items() if now - stream.updated > _TTL_SECONDS]:
        _STREAMS.pop(key, None)
    while len(_STREAMS) > _MAX_STREAMS:
        _STREAMS.pop(min(_STREAMS, key=lambda key: _STREAMS[key].updated), None)


def publish(key: StreamKey | None, event: str, data: dict[str, Any]) -> None:
    """Append ``event`` to the submission's stream; a terminal event closes it, and later events are dropped."""
    if key is None:
        return
    with _CHANGED:
        now = time.monotonic()
        stream = _STREAMS.setdefault(key, _Stream())
        if stream.done or (stream.events and stream.events[-1] == (event, data)):
            return
        stream.events.append((event, data))
        stream.updated = now
        _prune(now)
        _CHANGED.notify_all()


def events(key: StreamKey, after: int = -1, *, timeout_s: float = 120.0) -> Iterator[tuple[int, str, dict[str, Any]]]:
    """The submission's events after index ``after``, as they come, until a terminal one or ``timeout_s``."""
    deadline = time.monotonic() + timeout_s
    sent = after
    while True:
        with _CHANGED:
            stream = _STREAMS.get(key)
            rows = list(stream.events) if stream else []
            done = stream.done if stream else False
            fresh = [(index, name, data) for index, (name, data) in enumerate(rows) if index > sent]
            if not fresh and not done:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return
                _CHANGED.wait(min(remaining, 1.0))
                continue
        for index, name, data in fresh:
            sent = index
            yield index, name, data
            if name in TERMINAL:
                return
        if done:
            return


def has_stream(key: StreamKey | None) -> bool:
    with _CHANGED:
        return key is not None and key in _STREAMS


def reset_for_tests() -> None:
    with _CHANGED:
        _STREAMS.clear()


__all__ = ["TERMINAL", "events", "has_stream", "publish", "reset_for_tests", "stream_key"]
