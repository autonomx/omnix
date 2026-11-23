"""The canonical forms trading evidence is hashed, timed and priced in.

``canonical_sha256`` is the digest stored beside handoffs, predictions, market-data
windows and session evidence. Its bytes are a stored contract: changing the JSON form
(key order, separators, ``default=str``, ASCII escaping) changes every recorded digest.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json


def canonical_json(payload: object) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def canonical_sha256(payload: object) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def require_utc(value: datetime, *, error: str = "timestamp_must_be_timezone_aware") -> datetime:
    """``value`` in UTC; a naive timestamp is refused, never guessed."""
    if value.tzinfo is None:
        raise ValueError(error)
    return value.astimezone(timezone.utc)


def optional_decimal(value: object) -> Decimal | None:
    """A decimal read leniently: ``None``, ``""`` and anything unparsable read as no value."""
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


__all__ = ["canonical_json", "canonical_sha256", "optional_decimal", "require_utc"]
