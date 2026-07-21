"""Readable projections for document-style world authoring topics."""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from .authoring_presentations import entity_card, rows, text

_RESERVED_DETAIL_FIELDS = {
    "id",
    "fact_id",
    "relationship_id",
    "rule_id",
    "thread_id",
    "name",
    "title",
    "label",
    "statement",
    "content",
    "description",
    "summary",
    "full_text",
    "body",
    "text",
    "visibility",
    "authority",
    "approved_authority",
    "entity_refs",
    "entities",
}


def _references(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    resolved: list[dict[str, str]] = []
    for item in value:
        if isinstance(item, Mapping):
            entity_id = text(item.get("id") or item.get("entity_id") or item.get("ref"))
            role = text(item.get("role") or item.get("relationship") or item.get("kind"))
        else:
            entity_id = text(item)
            role = ""
        if entity_id:
            resolved.append({"id": entity_id, "role": role})
    return resolved


def _details(row: Mapping[str, Any]) -> list[dict[str, Any]]:
    details: list[dict[str, Any]] = []
    for key, value in row.items():
        if key in _RESERVED_DETAIL_FIELDS or value in (None, "", [], {}, ()):
            continue
        details.append({"label": key.replace("_", " ").title(), "value": value})
    return details


def _badges(row: Mapping[str, Any]) -> list[Any]:
    return [
        value
        for value in (
            row.get("visibility"),
            row.get("approved_authority") or row.get("authority"),
            row.get("status"),
        )
        if value not in (None, "", [], {})
    ]


def _item(
    row: Mapping[str, Any],
    *,
    index: int,
    fallback_label: str,
    value_fields: Sequence[str],
) -> dict[str, Any]:
    label = text(
        row.get("title")
        or row.get("name")
        or row.get("label")
        or row.get("fact_id")
        or row.get("relationship_id")
        or row.get("rule_id")
        or row.get("thread_id")
        or row.get("id"),
        f"{fallback_label} {index + 1}",
    )
    value = ""
    for field in value_fields:
        value = text(row.get(field))
        if value:
            break
    return {
        "label": label,
        "value": value or "No description was provided.",
        "badges": _badges(row),
        "references": _references(row.get("entity_refs") or row.get("entities")),
        "details": _details(row),
    }


def document_blocks(content: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Project provider-shaped topic data into stable, readable page blocks."""

    blocks: list[dict[str, Any]] = []
    for document in rows(content.get("documents")):
        title = text(document.get("title") or document.get("name"), "Lore")
        body = text(
            document.get("full_text")
            or document.get("body")
            or document.get("text")
            or document.get("summary")
        )
        if body:
            blocks.append(
                {
                    "kind": "section",
                    "title": title,
                    "body": body,
                    "items": [
                        {
                            "label": "Visibility",
                            "value": document.get("visibility"),
                        },
                        {
                            "label": "Keywords",
                            "value": document.get("keywords") or [],
                        },
                    ],
                }
            )

    collections = (
        (
            "facts",
            "Canon facts",
            "Fact",
            ("statement", "content", "fact", "object", "description"),
        ),
        (
            "relationships",
            "Relationships",
            "Relationship",
            ("description", "content", "statement", "object", "predicate"),
        ),
        (
            "knowledge_rules",
            "Knowledge rules",
            "Rule",
            ("description", "content", "statement", "rule", "condition"),
        ),
        (
            "story_threads",
            "Story threads",
            "Thread",
            ("premise", "summary", "description", "content", "statement"),
        ),
    )
    for key, title, fallback, value_fields in collections:
        source_rows = rows(content.get(key))
        if not source_rows:
            continue
        blocks.append(
            {
                "kind": "facts" if key == "facts" else "records",
                "title": title,
                "items": [
                    _item(
                        row,
                        index=index,
                        fallback_label=fallback,
                        value_fields=value_fields,
                    )
                    for index, row in enumerate(source_rows)
                ],
            }
        )

    if not blocks:
        blocks.append(
            {"kind": "json", "title": "Structured canon", "value": dict(content)}
        )
    return blocks


def related_entity_cards(
    content: Mapping[str, Any],
    *,
    topic_id: str,
) -> list[dict[str, Any]]:
    """Expose document-topic entities as readable related cards."""

    entity_rows = rows(content.get("entities"))
    cards: list[dict[str, Any]] = []
    for index, row in enumerate(entity_rows):
        kind = text(row.get("kind"), topic_id.rstrip("s") or "entity")
        cards.append(
            entity_card(
                row,
                card_type=kind,
                kind=kind,
                index=index,
                content=content,
            )
        )
    return cards
