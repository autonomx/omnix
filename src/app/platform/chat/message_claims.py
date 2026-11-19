"""Conditions for a claim on a message's metadata: merge a patch only while the message is still as it was read.

A claim (``claim_message_metadata`` on the chat stores) is how two writers settle who goes first without a lost update,
such as a spoken "confirm" and the Confirm button on one proposal: each claims ``pending -> executing`` and only the
winner runs it. A condition is a field equal to a JSON value, or a field that is missing (``ABSENT``); a missing key is
never compared as a null.
"""
from __future__ import annotations

from typing import Any


class _Absent:
    _instance: _Absent | None = None

    def __new__(cls) -> _Absent:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "ABSENT"


ABSENT: Any = _Absent()


def conditions_hold(metadata: dict[str, Any], require: dict[str, Any]) -> bool:
    """Whether every condition holds on this metadata."""
    for key, expected in require.items():
        if expected is ABSENT:
            if key in metadata:
                return False
        elif key not in metadata or metadata[key] != expected:
            return False
    return True


__all__ = ["ABSENT", "conditions_hold"]
