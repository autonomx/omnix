"""Compatibility exports for the audiobook-owned websocket transport."""
from app.audiobook.streaming import (
    AUDIOBOOK_FRAME_BYTES,
    AUDIOBOOK_SAMPLE_RATE,
    MAX_SENTENCE_CHARS,
    create_audiobook_streaming_router,
    register_audiobook_websocket,
)

__all__ = [
    "AUDIOBOOK_FRAME_BYTES",
    "AUDIOBOOK_SAMPLE_RATE",
    "MAX_SENTENCE_CHARS",
    "create_audiobook_streaming_router",
    "register_audiobook_websocket",
]
