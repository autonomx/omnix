"""Report helpers for deterministic RPG memory diagnostics."""
from __future__ import annotations

import json
from html import escape
from typing import Any, Dict, Iterable, Iterator, List, Mapping, Tuple

from .memory_prompt import MEMORY_PROMPT_CONTEXT_VERSION
from .memory_writer import MEMORY_SCHEMA_VERSION, memory_state_from_session

MEMORY_DEBUG_REPORT_VERSION = "rpg_memory_debug_report_v1"
MEMORY_DEBUG_REPORT_SOURCE = "deterministic_memory_debug_report"
MAX_DEBUG_TEXT = 220
MAX_RECENT_WRITES = 8
MAX_RETRIEVAL_ENTRIES = 12
MAX_GROUNDING_FACTS = 12
MAX_WALK_NODES = 400
MAX_WALK_DEPTH = 7


def _safe_dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return str(value) if value is not None else ""


def _clean_text(value: Any, limit: int = MAX_DEBUG_TEXT) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.strip().split())[:limit]


def _clean_id(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()[:120]
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    return ""


def _clean_int(value: Any, default: int = 0) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return default


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)


def _iter_mappings(root: Any) -> Iterator[Mapping[str, Any]]:
    stack: List[Tuple[Any, int]] = [(root, 0)]
    visited = 0
    while stack and visited < MAX_WALK_NODES:
        value, depth = stack.pop()
        if isinstance(value, Mapping):
            visited += 1
            yield value
            if depth >= MAX_WALK_DEPTH:
                continue
            for child in reversed(list(value.values())):
                if isinstance(child, (Mapping, list)):
                    stack.append((child, depth + 1))
        elif isinstance(value, list) and depth < MAX_WALK_DEPTH:
            for child in reversed(value):
                if isinstance(child, (Mapping, list)):
                    stack.append((child, depth + 1))


def _compact_entry(entry: Mapping[str, Any], *, section: str = "") -> Dict[str, Any]:
    compact: Dict[str, Any] = {
        "id": _clean_id(entry.get("id")),
        "kind": _clean_id(entry.get("kind")),
        "text": _clean_text(entry.get("text")),
        "tick": _clean_int(entry.get("tick")),
        "turn_id": _clean_id(entry.get("turn_id")),
        "actor_id": _clean_id(entry.get("actor_id")),
        "subject_id": _clean_id(entry.get("subject_id")),
        "location_id": _clean_id(entry.get("location_id")),
        "visibility": _clean_id(entry.get("visibility")) or "public",
        "salience": _clean_int(entry.get("salience")),
        "tags": [_clean_id(tag) for tag in _safe_list(entry.get("tags")) if _clean_id(tag)][:8],
        "source": _clean_id(entry.get("source")),
    }
    for key in ("event_type", "scope", "scope_id"):
        value = _clean_id(entry.get(key))
        if value:
            compact[key] = value
    if section:
        compact["section"] = section
    return {key: value for key, value in compact.items() if value not in ("", [], None)}


def _memory_state_summary(runtime_state: Mapping[str, Any]) -> Dict[str, Any]:
    runtime_state = _safe_dict(runtime_state)
    raw_memory = _safe_dict(runtime_state.get("memory"))
    memory = memory_state_from_session({"runtime_state": runtime_state})
    entries = [_safe_dict(entry) for entry in _safe_list(memory.get("entries"))]
    by_kind: Dict[str, int] = {}
    for entry in entries:
        kind = _clean_id(entry.get("kind")) or "unknown"
        by_kind[kind] = by_kind.get(kind, 0) + 1
    return {
        "available": bool(raw_memory),
        "version": _clean_id(memory.get("version")) or MEMORY_SCHEMA_VERSION,
        "next_sequence": _clean_int(memory.get("next_sequence"), len(entries) + 1),
        "total_entries": len(entries),
        "by_kind": dict(sorted(by_kind.items())),
        "recent_writes": [
            _compact_entry(entry)
            for entry in entries[-MAX_RECENT_WRITES:]
            if _clean_id(entry.get("id")) or _clean_text(entry.get("text"))
        ],
    }


def _runtime_state_from_turn(turn_payload: Mapping[str, Any]) -> Dict[str, Any]:
    for mapping in _iter_mappings(turn_payload):
        runtime_state = mapping.get("runtime_state")
        if isinstance(runtime_state, Mapping):
            return _safe_dict(runtime_state)
    return {}


def _is_relevant_memory_context(value: Mapping[str, Any]) -> bool:
    return _clean_id(value.get("format_version")) == MEMORY_PROMPT_CONTEXT_VERSION


def _relevant_memory_from_turn(turn_payload: Mapping[str, Any]) -> Dict[str, Any]:
    for mapping in _iter_mappings(turn_payload):
        if _is_relevant_memory_context(mapping):
            return _safe_dict(mapping)
        relevant = mapping.get("relevant_memory")
        if isinstance(relevant, Mapping) and _is_relevant_memory_context(relevant):
            return _safe_dict(relevant)
    return {}


def _retrieval_summary(relevant_memory: Mapping[str, Any]) -> Dict[str, Any]:
    relevant_memory = _safe_dict(relevant_memory)
    sections = {
        "recent": _safe_list(relevant_memory.get("recent")),
        "actors": _safe_list(relevant_memory.get("actors")),
        "world": _safe_list(relevant_memory.get("world")),
    }
    entries: List[Dict[str, Any]] = []
    ids: List[str] = []
    for section, raw_entries in sections.items():
        for raw_entry in raw_entries:
            entry = _compact_entry(_safe_dict(raw_entry), section=section)
            entry_id = _clean_id(entry.get("id"))
            if entry:
                entries.append(entry)
            if entry_id and entry_id not in ids:
                ids.append(entry_id)
            if len(entries) >= MAX_RETRIEVAL_ENTRIES:
                break
    return {
        "available": bool(relevant_memory),
        "format_version": _clean_id(relevant_memory.get("format_version")),
        "query": _safe_dict(relevant_memory.get("query")),
        "counts": {key: len(value) for key, value in sections.items()},
        "ids": ids[:MAX_RETRIEVAL_ENTRIES],
        "entries": entries[:MAX_RETRIEVAL_ENTRIES],
    }


def _collect_grounding_validations(turn_payload: Mapping[str, Any]) -> List[Dict[str, Any]]:
    validations: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for mapping in _iter_mappings(turn_payload):
        candidates: Iterable[Any] = []
        if "memory_grounding_validation" in mapping:
            candidates = [mapping.get("memory_grounding_validation")]
        elif _clean_id(mapping.get("source")) == "memory_narration_grounding_guard" and "evidence" in mapping:
            candidates = [mapping]
        for candidate in candidates:
            validation = _safe_dict(candidate)
            if not validation:
                continue
            key = _json_dumps(validation)[:500]
            if key in seen:
                continue
            seen.add(key)
            validations.append(validation)
            if len(validations) >= 6:
                return validations
    return validations


def _grounding_summary(validations: List[Dict[str, Any]]) -> Dict[str, Any]:
    memory_ids: List[str] = []
    used_facts: List[Dict[str, Any]] = []
    authoritative_facts: List[str] = []
    violation_count = 0
    original_violation_count = 0
    ok_values: List[bool] = []
    for validation in validations:
        if isinstance(validation.get("ok"), bool):
            ok_values.append(bool(validation.get("ok")))
        violation_count += len(_safe_list(validation.get("violations")))
        original_violation_count += len(_safe_list(validation.get("original_violations")))
        evidence = _safe_dict(validation.get("evidence"))
        for memory_id in _safe_list(evidence.get("memory_ids")):
            clean = _clean_id(memory_id)
            if clean and clean not in memory_ids:
                memory_ids.append(clean)
        for entry in _safe_list(evidence.get("entries")):
            compact = _compact_entry(_safe_dict(entry), section=_clean_id(_safe_dict(entry).get("section")))
            entry_id = _clean_id(compact.get("id"))
            if compact and not any(_clean_id(existing.get("id")) == entry_id for existing in used_facts):
                used_facts.append(compact)
            if len(used_facts) >= MAX_GROUNDING_FACTS:
                break
        for fact in _safe_list(evidence.get("authoritative_facts")):
            text = _clean_text(fact)
            if text and text not in authoritative_facts:
                authoritative_facts.append(text)
            if len(authoritative_facts) >= MAX_GROUNDING_FACTS:
                break
    return {
        "available": bool(validations),
        "validation_count": len(validations),
        "ok": all(ok_values) if ok_values else None,
        "memory_ids": memory_ids[:MAX_GROUNDING_FACTS],
        "used_facts": used_facts[:MAX_GROUNDING_FACTS],
        "authoritative_facts": authoritative_facts[:MAX_GROUNDING_FACTS],
        "violation_count": violation_count,
        "original_violation_count": original_violation_count,
    }


def build_memory_debug_report_payload(turn_payload: Mapping[str, Any]) -> Dict[str, Any]:
    """Return a bounded report/UI payload for memory writes and retrieval."""
    turn_payload = _safe_dict(turn_payload)
    memory_state = _memory_state_summary(_runtime_state_from_turn(turn_payload))
    retrieval = _retrieval_summary(_relevant_memory_from_turn(turn_payload))
    grounding = _grounding_summary(_collect_grounding_validations(turn_payload))
    return {
        "format_version": MEMORY_DEBUG_REPORT_VERSION,
        "source": MEMORY_DEBUG_REPORT_SOURCE,
        "available": bool(
            memory_state.get("available")
            or retrieval.get("available")
            or grounding.get("available")
        ),
        "memory_state": memory_state,
        "retrieval": retrieval,
        "grounding": grounding,
    }


def _entry_list_html(entries: Iterable[Mapping[str, Any]], empty_label: str) -> str:
    rows = []
    for entry in entries:
        rows.append(
            "<li>"
            f"<code>{escape(_clean_id(entry.get('id')) or 'memory')}</code>"
            f" [{escape(_clean_id(entry.get('kind')) or _clean_id(entry.get('section')) or 'memory')}] "
            f"{escape(_clean_text(entry.get('text')))}"
            "</li>"
        )
    return "".join(rows) or f"<li>{escape(empty_label)}</li>"


def render_memory_debug_report_html(payload: Mapping[str, Any]) -> str:
    """Render a compact collapsed HTML panel for campaign reports."""
    payload = _safe_dict(payload)
    memory_state = _safe_dict(payload.get("memory_state"))
    retrieval = _safe_dict(payload.get("retrieval"))
    grounding = _safe_dict(payload.get("grounding"))
    if not payload.get("available"):
        return "\n".join(
            [
                "<details><summary>RPG memory debug</summary>",
                "<p>No memory state, retrieval context, or grounding evidence was attached to this turn.</p>",
                f"<pre>{escape(_json_dumps(payload))}</pre>",
                "</details>",
            ]
        )
    return "\n".join(
        [
            "<details><summary>RPG memory debug</summary>",
            "<ul>",
            f"<li>memory entries: {escape(_safe_str(memory_state.get('total_entries')))}</li>",
            f"<li>retrieved ids: {escape(', '.join(_safe_list(retrieval.get('ids'))) or 'none')}</li>",
            f"<li>grounding ok: {escape(_safe_str(grounding.get('ok')))}</li>",
            f"<li>grounding original violations: {escape(_safe_str(grounding.get('original_violation_count')))}</li>",
            "</ul>",
            "<h4>Memory writes</h4><ul>",
            _entry_list_html(_safe_list(memory_state.get("recent_writes")), "none"),
            "</ul>",
            "<h4>Retrieved memory</h4><ul>",
            _entry_list_html(_safe_list(retrieval.get("entries")), "none"),
            "</ul>",
            "<h4>Grounding used facts</h4><ul>",
            _entry_list_html(_safe_list(grounding.get("used_facts")), "none"),
            "</ul>",
            f"<pre>{escape(_json_dumps(payload))}</pre>",
            "</details>",
        ]
    )
