"""A campaign document stored in parts (roadmap §7 Q-13; F2).

Most of a long campaign's document is the same from one turn to the next (the campaign bible's projection, an
archive), yet each commit rewrote all of it. The document is stored as its head (``omnix_rpg_campaigns.state_jsonb``)
and its parts (``omnix_rpg_campaign_parts``, a row each): an entry of a top-level section (``/runtime_state/
player_journal``) whose text is ``PART_MIN_BYTES`` or longer is a part, and a write stores only the parts it changed.
``manifest`` and what SQL reads in place (``HEAD_PATHS``) stay in the head.

The document's hash (``e1:``) is the hash of its entries' hashes, whichever are parts, so a commit hashes what changed
and takes the rest from the parts' stored hashes. A hash without the prefix is the sha256 of the document's canonical
text, as documents were hashed before; history holds both, and ``hash_matches`` checks either.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping

HASH_PREFIX = "e1:"
PART_MIN_BYTES = 4096
WHOLE_SECTIONS = frozenset({"manifest"})
# Read in place by SQL, so never parts: the list summary trigger (migration 0157), the launch gate and the seed
# (``PostgresRpgRepository``), the harnesses' current map instance.
HEAD_PATHS = frozenset({
    "/state/world", "/state/scene", "/state/location", "/state/current_location", "/state/current_location_id",
    "/state/current_location_name", "/state/published_world", "/state/environment_snapshot", "/state/player",
    "/state/campaign_bible", "/state/current_map_instance_id",
    "/simulation_state/player_state", "/simulation_state/location", "/simulation_state/campaign_end",
    "/simulation_state/rng_seed",
    "/runtime_state/campaign_launch_gate",
    "/setup_payload/world_forge",
})
_OBJECT = "{}"  # the entry hash of a section that is an object (its entries are hashed one by one)
STALE = ""  # the stored hash of a part the head overrides: rewritten or removed by the next write


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _token(key: Any) -> str:
    return str(key).replace("~", "~0").replace("/", "~1")


def _untoken(token: str) -> str:
    return token.replace("~1", "/").replace("~0", "~")


def _sectioned(name: str, value: Any) -> bool:
    return isinstance(value, dict) and name not in WHOLE_SECTIONS


def _jsonb_key(key: str) -> tuple[int, bytes]:
    encoded = key.encode("utf-8")
    return len(encoded), encoded


def _jsonb_ordered(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """An object's keys in the order JSONB keeps them (shorter first, then bytewise): the order a read returns, and
    the order the game's iterations then follow."""
    return dict(sorted(pairs, key=lambda pair: _jsonb_key(pair[0])))


def _loads(text: str) -> Any:
    return json.loads(text, object_pairs_hook=_jsonb_ordered)


def _digest(hashes: Mapping[str, str]) -> str:
    return HASH_PREFIX + _sha(canonical_json(sorted(hashes.items())))


@dataclass(frozen=True)
class StoredForm:
    """A document as it is stored: its head's text, its hash, its parts and what of them a write changes."""

    head: str
    digest: str
    part_hashes: dict[str, str]  # every part of the document: path -> hash
    written: dict[str, tuple[str, str]]  # the parts to write: path -> (text, hash)
    removed: tuple[str, ...]  # stored parts that are parts no longer


def stored_form(document: Mapping[str, Any], *, before: Mapping[str, Any] | None = None,
                stored_parts: Mapping[str, str] | None = None) -> StoredForm:
    """``document`` as head and parts. ``before`` and ``stored_parts`` are the stored document and its parts' hashes
    (``assembled``): a part equal to its stored self is neither serialized nor written."""
    before = before or {}
    stored_parts = stored_parts or {}
    hashes: dict[str, str] = {}
    part_hashes: dict[str, str] = {}
    written: dict[str, tuple[str, str]] = {}
    head: list[str] = []
    for key in sorted(document, key=str):
        value, name = document[key], str(key)
        path = "/" + _token(name)
        if not _sectioned(name, value):
            text = canonical_json(value)
            hashes[path] = _sha(text)
            head.append(f"{json.dumps(name, ensure_ascii=False)}:{text}")
            continue
        hashes[path] = _OBJECT
        previous = before.get(key)
        previous = previous if isinstance(previous, Mapping) else {}
        inner: list[str] = []
        for entry_key in sorted(value, key=str):
            entry, entry_name = value[entry_key], str(entry_key)
            entry_path = f"{path}/{_token(entry_name)}"
            stored = stored_parts.get(entry_path)
            if stored and entry_key in previous and type(previous[entry_key]) is type(entry) \
                    and previous[entry_key] == entry:
                hashes[entry_path] = part_hashes[entry_path] = stored
                continue
            text = canonical_json(entry)
            hashes[entry_path] = digest = _sha(text)
            if entry_path not in HEAD_PATHS and len(text) >= PART_MIN_BYTES:
                part_hashes[entry_path] = digest
                if stored != digest:
                    written[entry_path] = (text, digest)
            else:
                inner.append(f"{json.dumps(entry_name, ensure_ascii=False)}:{text}")
        head.append(f"{json.dumps(name, ensure_ascii=False)}:{{{','.join(inner)}}}")
    return StoredForm(head="{" + ",".join(head) + "}", digest=_digest(hashes), part_hashes=part_hashes,
                      written=written, removed=tuple(sorted(set(stored_parts) - set(part_hashes))))


def assembled(head: Mapping[str, Any], parts: Mapping[str, Any] | None) -> tuple[dict[str, Any], dict[str, str]]:
    """The document from its stored head and parts (``{path: [hash, value]}``), and its parts' hashes. A part the
    head overrides (a document written whole, out of band) is ``STALE``: the next write rewrites or removes it."""
    document = dict(head)
    hashes: dict[str, str] = {}
    filled: set[int] = set()
    for path, (digest, value) in sorted((parts or {}).items()):
        section, _, entry = path[1:].partition("/")
        holder = document.get(_untoken(section))
        name = _untoken(entry)
        if not isinstance(holder, dict) or name in holder:
            hashes[path] = STALE
            continue
        holder[name] = value
        hashes[path] = str(digest)
        filled.add(id(holder))
    for key, holder in list(document.items()):  # a section with parts put in: in its stored order, as stored whole
        if id(holder) in filled:
            document[key] = _jsonb_ordered(list(holder.items()))
    return document, hashes


def stored_document(form: StoredForm, before: Mapping[str, Any]) -> dict[str, Any] | None:
    """The document as storage holds it once ``form`` is written over ``before`` (the stored document it was formed
    against): what a read of it returns, in JSON's own types. None when ``before`` lacks a part ``form`` kept."""
    document = _loads(form.head)
    filled: set[str] = set()
    for path in form.part_hashes:
        section, _, entry = (_untoken(token) for token in path[1:].partition("/"))
        if path in form.written:
            value = _loads(form.written[path][0])
        else:
            previous = before.get(section)
            if not isinstance(previous, Mapping) or entry not in previous:
                return None
            value = previous[entry]
        holder = document.get(section)
        if not isinstance(holder, dict):
            return None
        holder[entry] = value
        filled.add(section)
    for section in filled:
        document[section] = _jsonb_ordered(list(document[section].items()))
    return document


def state_hash(document: Mapping[str, Any]) -> str:
    """The document's hash (``e1:``)."""
    return stored_form(document).digest


def hash_matches(document: Mapping[str, Any], recorded: str) -> bool:
    """Whether ``recorded`` is ``document``'s hash, in either scheme."""
    if recorded.startswith(HASH_PREFIX):
        return state_hash(document) == recorded
    return _sha(canonical_json(document)) == recorded


__all__ = ["HASH_PREFIX", "HEAD_PATHS", "PART_MIN_BYTES", "STALE", "StoredForm", "assembled", "canonical_json",
           "hash_matches", "state_hash", "stored_document", "stored_form"]
