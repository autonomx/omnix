"""How the world graph audits read compiled topics: a topic's rows, the candidate a row carries, every topic's
entities, and a record's fingerprint.

An audit that reads a topic differently (keeps strings, accepts one mapping as a row, fingerprints ASCII-escaped
JSON) keeps its own reader, because its report depends on that reading.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any


def mapping(value: Any) -> dict[str, Any]:
    """``value`` copied as a dict, or an empty one when it is not a mapping."""
    return dict(value) if isinstance(value, Mapping) else {}


def rows(value: Any) -> tuple[dict[str, Any], ...]:
    """The mappings in a list, each copied; nothing for a string, a mapping or anything else that is not a list."""
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ()
    return tuple(dict(item) for item in value if isinstance(item, Mapping))


def candidate(row: Mapping[str, Any]) -> dict[str, Any]:
    """What a topic row proposes: its ``candidate``, else its ``content``, else the row itself."""
    for key in ("candidate", "content"):
        value = row.get(key)
        if isinstance(value, Mapping):
            return dict(value)
    return dict(row)


def topic_entities(topic_rows: Sequence[Mapping[str, Any]]) -> tuple[tuple[str, int, dict[str, Any]], ...]:
    """Every topic's entities as ``(topic_id, index, entity)``; a topic without an id is ``topic:<n>``, from 1."""
    values: list[tuple[str, int, dict[str, Any]]] = []
    for topic_index, raw in enumerate(topic_rows, 1):
        topic = mapping(raw)
        proposed = candidate(topic)
        topic_id = str(topic.get("topic_id") or proposed.get("topic_id") or f"topic:{topic_index}")
        values.extend((topic_id, index, entity) for index, entity in enumerate(rows(proposed.get("entities"))))
    return tuple(values)


def fingerprint(value: Mapping[str, Any]) -> str:
    """``sha256:`` and the digest of ``value`` as sorted, compact JSON with its text unescaped."""
    encoded = json.dumps(dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


__all__ = ["candidate", "fingerprint", "mapping", "rows", "topic_entities"]
