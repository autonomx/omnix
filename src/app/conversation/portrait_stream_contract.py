"""The live portrait stream's binary messages (docs/architecture/OMNIX_LIVE_PORTRAIT_ROADMAP.md, Phase 1).

The gateway and the portrait service exchange one websocket per call. Control messages are JSON text.
Binary messages carry audio in and frames out, each as a header and a payload:

    [4-byte big-endian header length][UTF-8 JSON header][payload]

Audio in: header ``{"segment_id": str, "offset": int}`` (the offset in the segment's own samples) and
16-bit little-endian mono PCM. Frames out: header ``{"output_id", "epoch", "segment_id", "offset"}`` and a JPEG.
The idle loop's frames are stamped ``output_id`` and ``segment_id`` ``"idle"``, with the frame's index in the loop
as ``offset``, the loop's length as ``count`` and its frame period as ``frame_ms``.

Remote quality levels (roadmap Phase 3, "Remote quality"): the service encodes only the level the call's client is
on, set by the gateway's ``quality`` message; ``QUALITY_LEVELS[level]`` is (frame size, frame step, JPEG quality),
a frame step of 2 sending every other frame (12.5 frames a second).

Engines: the service renders with one of ``PORTRAIT_ENGINES`` at a time (Settings, Assistant, "Live portrait engine");
the gateway names it when it prepares a portrait, and a portrait's ``latent_key`` belongs to the engine it was
prepared with.

A turn's start hold (roadmap D-5, revised 2026-11-21): the browser's audio holds a reply's first phrase until the
portrait's frames cover ``lead_ms`` of it (or all of a shorter phrase), at most ``hold_ms``; the gateway sends the
call's engine's ``PORTRAIT_START_RULES`` in its ``ready``. FLOAT keeps up from its first frame (lead 0, the 250 ms
cap). FlashHead commits 24 frames a pass and needs a pass's audio before it renders it: started on its first
8 frames, the next pass is late unless TTS runs about 3x real time, so a start waits until the video is a whole pass
ahead (8 + 24 frames, 1.28 s), at most 1.2 s (a near-real-time voice, a group call's guest on 2026-11-21).
"""
from __future__ import annotations

import json
import struct
from typing import Any

MAX_HEADER_BYTES = 1_024
QUALITY_LEVELS: tuple[tuple[int, int, int], ...] = ((512, 1, 85), (512, 1, 70), (384, 1, 70), (384, 2, 70))
PORTRAIT_ENGINES: tuple[str, ...] = ("float", "flashhead-lite")
DEFAULT_PORTRAIT_ENGINE = "float"
# engine: (hold_ms, lead_ms), the start hold's cap and the video it waits for.
PORTRAIT_START_RULES: dict[str, tuple[int, int]] = {"float": (250, 0), "flashhead-lite": (1_200, 1_280)}
_LENGTH = struct.Struct(">I")


class PortraitMessageError(ValueError):
    """A binary message is not a header and a payload."""


def pack(header: dict[str, Any], payload: bytes) -> bytes:
    # UTF-8 as is, not \\u escapes: a 160-character segment id outside the basic plane is 640 bytes, not 1,920.
    encoded = json.dumps(header, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    if len(encoded) > MAX_HEADER_BYTES:
        raise PortraitMessageError("header too long")
    return _LENGTH.pack(len(encoded)) + encoded + payload


def unpack(message: bytes) -> tuple[dict[str, Any], bytes]:
    if len(message) < _LENGTH.size:
        raise PortraitMessageError("message too short")
    (length,) = _LENGTH.unpack_from(message)
    if length > MAX_HEADER_BYTES or _LENGTH.size + length > len(message):
        raise PortraitMessageError("bad header length")
    try:
        header = json.loads(message[_LENGTH.size:_LENGTH.size + length].decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise PortraitMessageError("header is not JSON") from exc
    if not isinstance(header, dict):
        raise PortraitMessageError("header is not an object")
    return header, message[_LENGTH.size + length:]


__all__ = ["DEFAULT_PORTRAIT_ENGINE", "MAX_HEADER_BYTES", "PORTRAIT_ENGINES", "PORTRAIT_START_RULES",
           "PortraitMessageError", "QUALITY_LEVELS", "pack", "unpack"]
