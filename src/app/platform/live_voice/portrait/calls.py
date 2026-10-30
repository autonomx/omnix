"""Live calls that may carry a portrait, by call key (roadmap Phase 2, "Binding").

The TTS websocket registers each call it accepts and gives the browser a ``hello`` with the call key and an
avatar token. The browser's avatar websocket presents the token; it is accepted only for the same principal
while that TTS connection is open on this gateway (both sockets reach one replica through the call-affinity
cookie). The registry lives on the live-voice feature's runtime state, one per gateway process, and holds
per-connection state only: an entry exists exactly as long as its TTS connection.

``PortraitCall`` is what the TTS route calls as it streams: every method is a no-op until an avatar websocket
has attached a ``PortraitLink``, so calls without a portrait behave exactly as before.

The browser gives every phrase its own output id and the turn's generation as its epoch; a reply is a turn.
The portrait's output is the turn (``turn-<epoch>``), so a reply's phrases are one motion stream across their
clause gaps, and cancelling any of a turn's phrases ends the turn's portrait (a barge-in). Segments stay per
phrase: the browser's audio clock counts in them.
"""
from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass, field

from .link import PortraitLink

LOCAL_PRINCIPAL = "local"


def turn_output(epoch: int) -> str:
    """The portrait output of the turn whose generation is ``epoch``."""
    return f"turn-{epoch}"


@dataclass
class PortraitCall:
    call_key: str
    token: str
    principal: str
    opened_at: float = field(default_factory=time.monotonic)
    link: PortraitLink | None = None
    # Source samples sent per segment (phrase): each PCM block's offset in its phrase.
    _offsets: dict[str, int] = field(default_factory=dict)
    _priority: bool = False

    def attach(self, link: PortraitLink) -> None:
        self.link = link
        self._offsets.clear()

    def detach(self, link: PortraitLink) -> None:
        if self.link is link:
            self.link = None

    def _send(self, message: dict) -> None:
        if self.link is not None and not self.link.closed:
            self.link.send(message)

    def phrase_start(self, output_id: str, epoch: int, segment_id: str, sample_rate: int) -> None:
        self._offsets.setdefault(segment_id, 0)
        self._send({"type": "phrase_start", "output_id": turn_output(epoch), "epoch": epoch,
                    "segment_id": segment_id, "sample_rate": sample_rate})

    def pcm(self, segment_id: str, pcm: bytes) -> None:
        offset = self._offsets.get(segment_id, 0)
        self._offsets[segment_id] = offset + len(pcm) // 2
        if self.link is not None and not self.link.closed:
            self.link.send_pcm(segment_id, offset, pcm)

    def phrase_done(self, segment_id: str) -> None:
        self._send({"type": "phrase_done", "segment_id": segment_id})
        self._offsets.pop(segment_id, None)

    def output_end(self, output_id: str, epoch: int) -> None:
        self._send({"type": "output_end", "output_id": turn_output(epoch), "epoch": epoch})

    def cancel(self, output_id: str, epoch: int) -> None:
        self._send({"type": "cancel", "output_id": turn_output(epoch), "epoch": epoch})

    def play_position(self, segment_id: str, offset: int, round_trip_seconds: float = 0.0) -> None:
        self._send({"type": "play_position", "segment_id": segment_id, "offset": offset,
                    "round_trip_seconds": round_trip_seconds})

    def tts_priority(self, on: bool) -> None:
        """TTS's first chunk of a phrase is pending (on) or out (off); sent only when it changes."""
        if on != self._priority:
            self._priority = on
            self._send({"type": "tts_priority", "on": on})


class PortraitCalls:
    """The calls on this gateway that a portrait may attach to."""

    def __init__(self) -> None:
        self._calls: dict[str, PortraitCall] = {}
        self._lock = threading.Lock()

    def issue(self, principal: str) -> PortraitCall:
        call = PortraitCall(call_key=secrets.token_urlsafe(18), token=secrets.token_urlsafe(32), principal=principal)
        with self._lock:
            self._calls[call.call_key] = call
        return call

    def claim(self, token: str, principal: str) -> PortraitCall | None:
        """The open call this token was issued for, if the same principal presents it."""
        with self._lock:
            for call in self._calls.values():
                if secrets.compare_digest(call.token, token):
                    return call if call.principal == principal else None
        return None

    def remove(self, call: PortraitCall) -> None:
        with self._lock:
            if self._calls.get(call.call_key) is call:
                del self._calls[call.call_key]

    def __len__(self) -> int:
        with self._lock:
            return len(self._calls)


def principal_id(scope: dict) -> str:
    """The caller's user id from the websocket scope, or ``local`` when sign-in is not enforced."""
    from app.security.auth.middleware import principal_from_scope

    principal = principal_from_scope(scope)
    user_id = getattr(principal, "user_id", None) if principal is not None else None
    return str(user_id) if user_id else LOCAL_PRINCIPAL


__all__ = ["LOCAL_PRINCIPAL", "PortraitCall", "PortraitCalls", "principal_id"]
