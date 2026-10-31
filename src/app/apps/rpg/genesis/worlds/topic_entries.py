"""A world's entries as its editor holds them, carried into its canon (evolution roadmap EV-6).

A world written by hand or installed from a bundle has nothing to recompile its canon from: no generation run, no
imported topics (``launch_repair_service._republished_latest``). Its editor shows each topic's lists of entries (the
people of ``characters``, the things of ``items``) and writes them there. When such a world is published again, each
entry its draft topics hold goes into the canon list of the same name, by id: an entry the canon has takes the
editor's fields over its own (the canon's other fields stay), and a new one is added, with its id in the entity
manifest and the release's index. A topic list the canon has no list of (a bestiary's creatures, which play reads
from its play sections) is the editor's alone. An entry added or changed may name only what the canon or the entries
hold (``unresolved``), and the republished revision records the entries it was made from (``entries_hash``), so a
launch reuses it only while the editor holds the same.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

# The release index of each canon list's ids, where the release keeps one.
_INDEXES = {"characters": "character_ids", "factions": "faction_ids", "quests": "quest_ids"}
# What the editor keeps on an entry for itself (``entity_authoring``: an entry waiting on one it names), not lore.
_EDITOR_FIELDS = frozenset({"authoring_status", "stale_reason"})
# A topic whose entries are the author's: written and ready, or waiting on a dependency that changed (still theirs).
_PUBLISHED_STATUSES = frozenset({"ready", "stale"})


def _rows(value: Any) -> list[dict[str, Any]]:
    return [dict(row) for row in value or () if isinstance(row, Mapping)] if isinstance(value, list) else []


def _entries(topic_rows: list[Mapping[str, Any]], canon: Mapping[str, Any] | None) -> dict[str, list[dict[str, Any]]]:
    """The draft topics' entries by the canon list they belong to, in topic order (every list of entries, with no
    ``canon``)."""
    entries: dict[str, list[dict[str, Any]]] = {}
    for topic in sorted(topic_rows, key=lambda row: str(row.get("topic_id") or "")):
        if str(topic.get("status") or "") not in _PUBLISHED_STATUSES:
            continue
        for key, value in dict(topic.get("content") or {}).items():
            rows = [{field: entry for field, entry in row.items() if field not in _EDITOR_FIELDS}
                    for row in _rows(value) if str(row.get("id") or "")]
            if rows and (canon is None or isinstance(canon.get(key), list)):
                entries.setdefault(key, []).extend(rows)
    return entries


def with_topic_entries(canon: Mapping[str, Any], manifest: Mapping[str, Any], indexes: Mapping[str, Any],
                       topic_rows: list[Mapping[str, Any]]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """``canon``, its entity ``manifest`` and the release's ``indexes`` with the draft topics' entries written in."""
    canon, manifest, indexes = dict(canon), dict(manifest), dict(indexes)
    for key, rows in _entries(topic_rows, canon).items():
        merged = _rows(canon.get(key))
        position = {str(row.get("id") or ""): index for index, row in enumerate(merged)}
        added: list[str] = []
        for row in rows:
            entry_id = str(row["id"])
            if entry_id in position:
                merged[position[entry_id]] = {**merged[position[entry_id]], **row}
            else:
                position[entry_id] = len(merged)
                merged.append(row)
                added.append(entry_id)
        canon[key] = merged
        if added and isinstance(manifest.get(key), list):
            manifest[key] = [*manifest[key], *(entry_id for entry_id in added if entry_id not in manifest[key])]
        index = _INDEXES.get(key, "")
        if added and isinstance(indexes.get(index), list):
            indexes[index] = [*indexes[index], *(entry_id for entry_id in added if entry_id not in indexes[index])]
    return canon, manifest, indexes


def holds_topic_entries(canon: Mapping[str, Any], topic_rows: list[Mapping[str, Any]]) -> bool:
    """Whether ``canon`` already holds every entry of the draft topics as the editor has it."""
    return with_topic_entries(canon, {}, {}, topic_rows)[0] == dict(canon)


def entries_hash(topic_rows: list[Mapping[str, Any]]) -> str:
    """Every entry the editor holds, as one hash (whatever lists a canon keeps, before or after its play sections)."""
    text = json.dumps(_entries(topic_rows, None), sort_keys=True, separators=(",", ":"), default=str)
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def unresolved(canon: Mapping[str, Any], manifest: Mapping[str, Any], topic_rows: list[Mapping[str, Any]]) -> list[str]:
    """Each reference an added or changed entry makes to what neither the canon nor the entries hold."""
    from .entity_authoring import validate_entity_references

    known = {str(row.get("id")) for value in canon.values() for row in _rows(value) if row.get("id")}
    known |= {str(entry_id) for value in manifest.values() if isinstance(value, list) for entry_id in value}
    entries = _entries(topic_rows, canon)
    known |= {str(row["id"]) for rows in entries.values() for row in rows}
    stood = {str(row.get("id") or ""): row for value in canon.values() for row in _rows(value)}
    found: list[str] = []
    for rows in entries.values():
        for row in rows:
            before = stood.get(str(row["id"]))
            if before is not None and all(before.get(field) == value for field, value in row.items()):
                continue  # as the canon holds it: nothing new to check
            try:
                validate_entity_references(row, known)
            except ValueError as problem:
                found.append(f"{row['id']}:{problem}")
    return found


def carries_entries(revision_document: Mapping[str, Any], topic_rows: list[Mapping[str, Any]]) -> bool:
    """Whether a published revision holds the entries the editor holds now: by the entries it recorded, or (one made
    before it recorded them, as a bundle installs) by its canon."""
    canon = dict(revision_document.get("canon") or {})
    recorded = str(dict(revision_document.get("provenance") or {}).get("topic_entries") or "")
    return recorded == entries_hash(topic_rows) if recorded else holds_topic_entries(canon, topic_rows)


__all__ = ["carries_entries", "entries_hash", "holds_topic_entries", "unresolved", "with_topic_entries"]
