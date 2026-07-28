"""Attach compact machine-readable canon lookups to compiled World Forge facts."""
from __future__ import annotations

import json
from dataclasses import replace
from typing import Any, Mapping

from .world_forge_generation import GeneratedTopic

_STRUCTURED_SOURCE = "profile_structured_fact_compiler_v1"
_LOOKUP_SCHEMA = "rpg_structured_canon_lookup_v1"


def _lookup(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "subject": str(row.get("subject") or ""),
        "predicate": str(row.get("predicate") or row.get("field_id") or ""),
        "object": row.get("object"),
        "value_type": str(row.get("value_type") or ""),
        "semantic_role": str(row.get("semantic_role") or ""),
        "topic_id": str(row.get("topic_id") or ""),
        "entity_refs": [str(value) for value in row.get("entity_refs") or ()],
    }


def attach_structured_canon_lookup(topic: GeneratedTopic) -> GeneratedTopic:
    """Store exact JSON facts for runtime lookup and later generation prompts.

    The existing human-readable sentence is retained as ``display_text``. ``content``
    becomes a compact JSON string because the provider dependency compactor already
    forwards that field to subsequent topic generations. The raw ``lookup`` object is
    persisted alongside it for direct game/runtime access without parsing lore prose.
    """

    facts: list[dict[str, Any]] = []
    lookup_count = 0
    index: dict[str, dict[str, str]] = {}
    for source in topic.facts:
        row = dict(source)
        if str(row.get("source") or "") != _STRUCTURED_SOURCE:
            facts.append(row)
            continue
        lookup = _lookup(row)
        display_text = str(row.get("display_text") or row.get("content") or "").strip()
        row["display_text"] = display_text
        row["lookup_schema"] = _LOOKUP_SCHEMA
        row["lookup"] = lookup
        row["content"] = json.dumps(
            lookup,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        facts.append(row)
        subject = lookup["subject"]
        predicate = lookup["predicate"]
        fact_id = str(row.get("id") or "")
        if subject and predicate and fact_id:
            index.setdefault(subject, {})[predicate] = fact_id
        lookup_count += 1

    if not lookup_count:
        return topic
    return replace(
        topic,
        facts=tuple(facts),
        provenance={
            **dict(topic.provenance),
            "structured_canon_lookup_schema": _LOOKUP_SCHEMA,
            "structured_canon_lookup_count": lookup_count,
            "structured_canon_fact_index": index,
        },
    )


__all__ = ["attach_structured_canon_lookup"]
