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
"""
from __future__ import annotations

import json
import struct
from typing import Any

MAX_HEADER_BYTES = 1_024
QUALITY_LEVELS: tuple[tuple[int, int, int], ...] = ((512, 1, 85), (512, 1, 70), (384, 1, 70), (384, 2, 70))
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


__all__ = ["MAX_HEADER_BYTES", "PortraitMessageError", "QUALITY_LEVELS", "pack", "unpack"]
