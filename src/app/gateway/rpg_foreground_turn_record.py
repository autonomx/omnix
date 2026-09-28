"""Compatibility exports for RPG-owned foreground turn records."""
from app.rpg.foreground_turn_record import (
    FOREGROUND_TURN_RECORD_MAX_BYTES,
    FOREGROUND_TURN_RECORD_VERSION,
    build_foreground_turn_record,
)

__all__ = [
    "FOREGROUND_TURN_RECORD_MAX_BYTES",
    "FOREGROUND_TURN_RECORD_VERSION",
    "build_foreground_turn_record",
]
