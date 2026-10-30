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

Speculative TTS (roadmap Phase 3, "Keeping the hold near zero"): a prefetch request carrying the call key gets a
``SpeculativeCopy``, which the prefetch thread feeds as it caches each chunk; the copy hops to the call's event
loop and goes to the service as ``spec_start`` and PCM for segment ``spec:<generation_id>``, through a bounded
count of pending sends (past it the copy is dropped and the entry is no longer used for the portrait). When a
phrase replays a copied entry, ``bind`` sends ``spec_bind`` and the phrase's own copy skips the replayed audio
(the prefetch thread already sent it); once the replay's length is known, ``spec_prefix_end`` and the phrase's
fresh audio after it follow. Every way an entry is dropped sends ``spec_drop``.

The copy counts the provider's samples from its first; the browser gets them less the leading silence the
transport drops (``trim``). So a bound phrase stays on the copy's timeline: ``spec_bind`` names the trim, the
phrase's later audio goes at its offset plus the trim, and the service stamps frames back onto the browser's.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from .link import PortraitLink

logger = logging.getLogger(__name__)

LOCAL_PRINCIPAL = "local"
SPEC_COPY_PENDING_LIMIT = 256
SPEC_SEGMENT_PREFIX = "spec:"  # the service's segment for a speculation's audio (services.portrait.scheduler)


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
    # Phrases replaying a copied speculation, by segment: the generation id, the provider samples replayed so far,
    # and the leading samples the transport dropped (the bound phrase's offsets are shifted by it).
    _replaying: dict[str, str] = field(default_factory=dict)
    _replayed: dict[str, int] = field(default_factory=dict)
    _trim: dict[str, int] = field(default_factory=dict)
    loop: asyncio.AbstractEventLoop | None = None

    def attach(self, link: PortraitLink) -> None:
        self.link = link
        with contextlib.suppress(RuntimeError):  # attached from the avatar websocket, on the gateway's loop
            self.loop = asyncio.get_running_loop()
        self._offsets.clear()
        self._replaying.clear()
        self._replayed.clear()
        self._trim.clear()

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

    def pcm(self, segment_id: str, pcm: bytes, replay: tuple[str, int, bool] | None = None) -> None:
        """Copy a phrase's PCM block.

        ``replay`` (generation id, samples replayed so far, whether the replay is over) marks a block of a phrase
        replaying a copied speculation: the replayed part is not copied again.
        """
        offset = self._offsets.get(segment_id, 0)
        samples = len(pcm) // 2
        self._offsets[segment_id] = offset + samples
        trim = self._trim.get(segment_id, 0)
        if segment_id in self._replaying:
            if replay is not None:
                self._replayed[segment_id] = replay[1]
            if replay is None or not replay[2]:
                return  # all replay so far: the prefetch thread copied it
            prefix = replay[1]  # in the provider's samples; the browser's is ``prefix - trim``
            self._end_replay(segment_id, prefix)
            if offset + samples <= prefix - trim:
                return
            start = max(offset, prefix - trim)
            pcm, offset = pcm[(start - offset) * 2:], start
        if self.link is not None and not self.link.closed:
            self.link.send_pcm(segment_id, offset + trim, pcm)

    def phrase_done(self, segment_id: str) -> None:
        if segment_id in self._replaying:  # the phrase was all replay
            self._end_replay(segment_id, self._replayed.get(segment_id, 0))
        self._send({"type": "phrase_done", "segment_id": segment_id})
        self._offsets.pop(segment_id, None)
        self._replayed.pop(segment_id, None)
        self._trim.pop(segment_id, None)

    def close_phrase(self, segment_id: str) -> None:
        """End a phrase that started and was not ended (it failed or was stopped): its audio stops here."""
        if segment_id in self._offsets:
            self.phrase_done(segment_id)

    def bind(self, generation_id: str, epoch: int, segment_id: str, trim: int = 0) -> None:
        """This phrase replays a speculation the portrait already has: its frames become the phrase's.

        ``trim`` is how many of the speculation's first samples the browser never got (leading silence).
        """
        self._replaying[segment_id] = generation_id
        self._trim[segment_id] = max(0, int(trim))
        self._send({"type": "spec_bind", "generation_id": generation_id, "output_id": turn_output(epoch),
                    "epoch": epoch, "segment_id": segment_id, "trim": max(0, int(trim))})

    def _end_replay(self, segment_id: str, samples: int) -> None:
        generation_id = self._replaying.pop(segment_id)
        self._send({"type": "spec_prefix_end", "generation_id": generation_id, "segment_id": segment_id,
                    "samples": samples})

    def speculative_copy(self, generation_id: str) -> SpeculativeCopy | None:
        """A copy of a speculative TTS entry for this call's portrait, or None without one."""
        if self.link is None or self.link.closed or self.loop is None:
            return None
        return SpeculativeCopy(self, generation_id, self.loop)

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


class SpeculativeCopy:
    """A speculative TTS entry's copy into a call's portrait, fed on the prefetch thread."""

    def __init__(self, call: PortraitCall, generation_id: str, loop: asyncio.AbstractEventLoop,
                 pending_limit: int = SPEC_COPY_PENDING_LIMIT) -> None:
        self.call, self.generation_id, self.loop = call, generation_id, loop
        self.pending_limit = pending_limit
        self.usable = True
        self._offset = 0
        self._started = False
        self._pending = 0
        self._lock = threading.Lock()

    def chunk(self, pcm: bytes, sample_rate: int) -> None:
        """One cached chunk (prefetch thread, under the entry's condition, before replay can see it)."""
        with self._lock:
            if not self.usable:
                return
            if self._pending >= self.pending_limit:
                self.usable = False
                logger.info("Speculative portrait copy %s fell behind; dropped", self.generation_id)
                self._post(self.call._send, {"type": "spec_drop", "generation_id": self.generation_id})
                return
            self._pending += 1
            first, self._started = not self._started, True
            offset, self._offset = self._offset, self._offset + len(pcm) // 2
        self._post(self._deliver, first, sample_rate, offset, pcm)

    def drop(self) -> None:
        """The entry will never be replayed: the portrait can forget it."""
        with self._lock:
            started, self.usable = self._started, False
        if started:
            self._post(self.call._send, {"type": "spec_drop", "generation_id": self.generation_id})

    def _deliver(self, first: bool, sample_rate: int, offset: int, pcm: bytes) -> None:
        with self._lock:
            self._pending -= 1
        if first:
            self.call._send({"type": "spec_start", "generation_id": self.generation_id, "sample_rate": sample_rate})
        link = self.call.link
        if link is not None and not link.closed:
            link.send_pcm(SPEC_SEGMENT_PREFIX + self.generation_id, offset, pcm)

    def _post(self, callback: Any, *args: Any) -> None:
        with contextlib.suppress(RuntimeError):  # the call's loop has closed: so has its portrait
            self.loop.call_soon_threadsafe(callback, *args)


class PortraitCalls:
    """The calls on this gateway that a portrait may attach to."""

    def __init__(self) -> None:
        self._calls: dict[str, PortraitCall] = {}
        self._lock = threading.Lock()

    def issue(self, principal: str, call_key: str | None = None) -> PortraitCall:
        call = PortraitCall(call_key=call_key or new_call_key(), token=secrets.token_urlsafe(32), principal=principal)
        with self._lock:
            self._calls[call.call_key] = call
        return call

    def get(self, call_key: str, principal: str) -> PortraitCall | None:
        """The open call with this key, if it is the principal's."""
        with self._lock:
            call = self._calls.get(call_key)
        return call if call is not None and call.principal == principal else None

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


def new_call_key() -> str:
    """A live call's key: its speech lease's holder, its portrait's binding and its speculation's owner."""
    return secrets.token_urlsafe(18)


def portrait_call_registry(state: Any) -> PortraitCalls:
    """The live calls a portrait may attach to: one registry per gateway process, on the feature's state."""
    calls = getattr(state, "live_portrait_calls", None)
    if calls is None:
        calls = PortraitCalls()
        state.live_portrait_calls = calls
    return calls


def principal_id(scope: dict) -> str:
    """The caller's user id from the websocket scope, or ``local`` when sign-in is not enforced."""
    from app.security.auth.middleware import principal_from_scope

    principal = principal_from_scope(scope)
    user_id = getattr(principal, "user_id", None) if principal is not None else None
    return str(user_id) if user_id else LOCAL_PRINCIPAL


__all__ = ["LOCAL_PRINCIPAL", "PortraitCall", "PortraitCalls", "SpeculativeCopy", "new_call_key",
           "portrait_call_registry", "principal_id"]
