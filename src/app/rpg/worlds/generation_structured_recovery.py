"""Bounded recovery helpers for malformed World Forge structured responses."""
from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from pydantic import BaseModel, ValidationError

from app.providers.base import ChatMessage, ChatResponse
from app.providers.structured import StructuredContract
from app.providers.structured.parsing import canonical_structured_text, decode_json_object
from app.rpg_world_forge_provider import WorldForgeTopicResponse

_COLLECTIONS = (
    "documents",
    "entities",
    "facts",
    "relationships",
    "knowledge_rules",
    "story_threads",
)
_MAX_RETAINED_TEXT = 65_536


class CapturingStructuredProvider:
    """Proxy one provider while retaining its latest non-streaming response."""

    def __init__(self, provider: Any) -> None:
        self._provider = provider
        self.last_response: ChatResponse | None = None

    def __getattr__(self, name: str) -> Any:
        return getattr(self._provider, name)

    def chat_completion(self, *args: Any, **kwargs: Any) -> Any:
        response = self._provider.chat_completion(*args, **kwargs)
        if isinstance(response, ChatResponse):
            self.last_response = response
        return response

    @property
    def raw_text(self) -> str:
        if self.last_response is None:
            return ""
        try:
            return canonical_structured_text(self.last_response)
        except Exception:
            return str(self.last_response.content or "")


@dataclass(frozen=True)
class DeterministicRepair:
    payload: Mapping[str, Any] | None
    codes: tuple[str, ...]


def decode_candidate(raw_text: str) -> Mapping[str, Any] | None:
    if not raw_text.strip():
        return None
    try:
        value = decode_json_object(raw_text)
    except Exception:
        return None
    return dict(value) if isinstance(value, Mapping) else None


def deterministic_repair(
    payload: Mapping[str, Any] | None,
    *,
    expected_topic_id: str,
    allocated_entity_ids: tuple[str, ...],
    expected_entity_kind: str,
) -> DeterministicRepair:
    """Repair only transformations whose intended value is authoritative."""

    if payload is None:
        return DeterministicRepair(None, ())
    value: dict[str, Any] = copy.deepcopy(dict(payload))
    codes: list[str] = []

    for wrapper in ("response", "result", "output"):
        wrapped = value.get(wrapper)
        if len(value) == 1 and isinstance(wrapped, Mapping):
            value = copy.deepcopy(dict(wrapped))
            codes.append(f"unwrap_{wrapper}")
            break

    topic_id = str(value.get("topic_id") or "")
    if topic_id in set(allocated_entity_ids):
        value["topic_id"] = expected_topic_id
        codes.append("root_topic_id_from_entity_id")
    elif not topic_id:
        for alias in ("domain_id", "topic"):
            if value.get(alias) == expected_topic_id:
                value["topic_id"] = expected_topic_id
                value.pop(alias, None)
                codes.append(f"root_topic_id_from_{alias}")
                break

    for collection in _COLLECTIONS:
        current = value.get(collection)
        if isinstance(current, Mapping):
            value[collection] = [copy.deepcopy(dict(current))]
            codes.append(f"wrap_single_{collection}")
        elif current is None:
            value[collection] = []
            codes.append(f"add_empty_{collection}")
    if not isinstance(value.get("provenance"), Mapping):
        value["provenance"] = {}
        codes.append("add_empty_provenance")

    entities = value.get("entities")
    if isinstance(entities, list):
        repaired_entities: list[Any] = []
        allowed = set(allocated_entity_ids)
        for item in entities:
            if not isinstance(item, Mapping):
                repaired_entities.append(item)
                continue
            entity = copy.deepcopy(dict(item))
            entity_id = str(entity.get("id") or "")
            alias_id = str(entity.get("entity_id") or "")
            if not entity_id and alias_id in allowed:
                entity["id"] = alias_id
                codes.append("entity_id_from_entity_id_alias")
            if not entity.get("kind") and entity.get("type") == expected_entity_kind:
                entity["kind"] = expected_entity_kind
                entity.pop("type", None)
                codes.append("entity_kind_from_type_alias")
            repaired_entities.append(entity)
        value["entities"] = repaired_entities

    return DeterministicRepair(value, tuple(dict.fromkeys(codes)))


def validate_payload(
    contract: StructuredContract[Any],
    payload: Mapping[str, Any] | None,
) -> tuple[BaseModel | None, Exception | None]:
    if payload is None:
        return None, ValueError("structured_candidate_not_decodable")
    try:
        candidate = contract.output_model.model_validate(payload)
    except ValidationError as exc:
        return None, exc
    if contract.semantic_validator is not None:
        try:
            contract.semantic_validator(candidate)
        except Exception as exc:
            return None, exc
    return candidate, None


def _error_rows(error: Exception) -> list[dict[str, Any]]:
    if isinstance(error, ValidationError):
        return [dict(row) for row in error.errors(include_url=False)]
    rows = []
    for issue in getattr(error, "issues", ()):
        method = getattr(issue, "as_dict", None)
        rows.append(method() if callable(method) else {"message": str(issue)})
    return rows or [{"type": type(error).__name__, "message": str(error)}]


def recovery_messages(
    *,
    contract: StructuredContract[Any],
    raw_text: str,
    decoded_payload: Mapping[str, Any] | None,
    error: Exception,
    expected_topic_id: str,
    allocated_entity_ids: tuple[str, ...],
    expected_entity_kind: str,
) -> list[ChatMessage]:
    payload: dict[str, Any] = {
        "task": "extract_existing_information_into_required_schema",
        "rules": [
            "Do not invent, enrich, summarise, or regenerate lore.",
            "Preserve all usable prose, names, dates, identifiers, and relationships.",
            "Only rename fields, move values, wrap or unwrap containers, and correct fixed identities.",
            "The root topic_id and allocated entity IDs are authoritative.",
            "Return exactly one JSON object and no explanation.",
        ],
        "identity": {
            "root_topic_id": expected_topic_id,
            "allocated_entity_ids": list(allocated_entity_ids),
            "entity_kind": expected_entity_kind,
        },
        "validation_errors": _error_rows(error),
        "required_schema": contract.output_model.model_json_schema(),
        "invalid_candidate": (
            dict(decoded_payload) if decoded_payload is not None else raw_text
        ),
    }
    return [
        ChatMessage(
            role="system",
            content=(
                "You are a loss-minimising JSON recovery transformer. The candidate already "
                "contains the author's lore. Extract that information into the supplied schema "
                "without writing replacement lore. Correct structure, field placement, aliases, "
                "and authoritative IDs only."
            ),
        ),
        ChatMessage(
            role="user",
            content="WORLD_FORGE_STRUCTURED_RECOVERY:\n"
            + json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str),
        ),
    ]


def merge_diagnostics(
    primary: Mapping[str, Any],
    secondary: Mapping[str, Any] | None,
    *,
    method: str,
    repair_codes: Sequence[str],
    raw_text: str,
    error: Exception,
) -> dict[str, Any]:
    first = dict(primary)
    second = dict(secondary or {})
    merged = {**first, **second}
    for key in (
        "provider_calls",
        "transport_retries",
        "format_downgrades",
        "validation_regenerations",
        "latency_ms",
        "raw_response_length",
    ):
        merged[key] = float(first.get(key) or 0) + float(second.get(key) or 0)
        if key != "latency_ms":
            merged[key] = int(merged[key])
    usage: dict[str, Any] = {}
    for source in (first.get("usage"), second.get("usage")):
        if not isinstance(source, Mapping):
            continue
        for key, item in source.items():
            if isinstance(item, (int, float)) and not isinstance(item, bool):
                usage[key] = usage.get(key, 0) + item
    merged["usage"] = usage
    merged["structured_recovery"] = {
        "method": method,
        "repair_codes": list(dict.fromkeys(str(code) for code in repair_codes)),
        "original_error_type": type(error).__name__,
        "original_error": str(error),
        "original_candidate_hash": hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
        if raw_text
        else "",
        "requires_manual_review": True,
    }
    return merged


def retained_topic_response(
    *,
    expected_topic_id: str,
    decoded_payload: Mapping[str, Any] | None,
    raw_text: str,
    error: Exception,
) -> WorldForgeTopicResponse:
    payload = dict(decoded_payload or {})

    def rows(name: str) -> list[dict[str, Any]]:
        current = payload.get(name)
        if isinstance(current, Mapping):
            return [dict(current)]
        if isinstance(current, Sequence) and not isinstance(
            current, (str, bytes, bytearray)
        ):
            return [dict(item) for item in current if isinstance(item, Mapping)]
        return []

    provenance = dict(payload.get("provenance") or {})
    provenance["structured_recovery_retained_candidate"] = {
        "error_type": type(error).__name__,
        "error": str(error),
        "decoded_candidate": payload if decoded_payload is not None else None,
        "raw_text": raw_text[:_MAX_RETAINED_TEXT] if decoded_payload is None else "",
        "truncated": decoded_payload is None and len(raw_text) > _MAX_RETAINED_TEXT,
    }
    return WorldForgeTopicResponse(
        topic_id=expected_topic_id,
        documents=rows("documents"),
        entities=rows("entities"),
        facts=rows("facts"),
        relationships=rows("relationships"),
        knowledge_rules=rows("knowledge_rules"),
        story_threads=rows("story_threads"),
        provenance=provenance,
    )


def recovery_review(topic_id: str, records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    methods = tuple(str(row.get("method") or "unknown") for row in records)
    issues = [
        {
            "code": f"structured_recovery_{method}",
            "topic_id": topic_id,
            "entity_id": "",
            "field_id": "",
            "message": (
                "The original provider response required automatic structural recovery; "
                "review the recovered candidate before promotion."
            ),
            "expected": "manual review",
            "allowed_domains": [],
            "candidates": [],
            "supplied_value": None,
        }
        for method in methods
    ]
    return {
        "schema_version": "rpg_world_generation_review_v1",
        "status": "needs_review",
        "blocking": True,
        "error_type": "StructuredRecoveryApplied",
        "reason_codes": sorted({issue["code"] for issue in issues}),
        "issues": issues,
        "summary": "Automatic structural recovery produced a reviewable lore candidate.",
    }


__all__ = [
    "CapturingStructuredProvider",
    "decode_candidate",
    "deterministic_repair",
    "merge_diagnostics",
    "recovery_messages",
    "recovery_review",
    "retained_topic_response",
    "validate_payload",
]
