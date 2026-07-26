"""Independent validation fallback for recovered profile-typed World Forge payloads."""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from app.rpg_world_forge_provider import WorldForgeTopicResponse

_PRESENTATION_FIELDS = frozenset(
    {
        "id",
        "kind",
        "entity_id",
        "name",
        "short_summary",
        "dossier",
        "registry_role",
        "registry_distinction",
    }
)


def _sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))


def _valid_value(value: Any, definition: Mapping[str, Any]) -> bool:
    value_type = str(definition.get("value_type") or "string")
    if value_type == "string":
        return isinstance(value, str)
    if value_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if value_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if value_type == "boolean":
        return isinstance(value, bool)
    if value_type == "enum":
        return isinstance(value, str) and value in {
            str(item) for item in definition.get("enum_values") or ()
        }
    if value_type == "entity_ref":
        return isinstance(value, str) and bool(value.strip())
    if value_type == "entity_ref_list":
        return _sequence(value) and all(
            isinstance(item, str) and bool(item.strip()) for item in value
        )
    if value_type == "structured_object":
        return isinstance(value, Mapping) or _sequence(value)
    return True


def validate_recovered_profile_payload(
    payload: Mapping[str, Any] | None,
    *,
    field_definitions: Sequence[Mapping[str, Any]],
    expected_topic_id: str,
    allocated_entity_ids: tuple[str, ...],
    expected_entity_kind: str,
    semantic_validator: Any = None,
) -> tuple[WorldForgeTopicResponse | None, Exception | None]:
    """Validate recovered lore without relying on a reused dynamic model class."""

    if payload is None:
        return None, ValueError("structured_candidate_not_decodable")
    try:
        candidate = WorldForgeTopicResponse.model_validate(payload)
    except Exception as exc:
        return None, exc
    if candidate.topic_id != expected_topic_id:
        return None, ValueError(
            f"topic_id_mismatch:{candidate.topic_id}:{expected_topic_id}"
        )
    rows = tuple(entity.model_dump(mode="python") for entity in candidate.entities)
    actual_ids = tuple(str(row.get("id") or "") for row in rows)
    if set(actual_ids) != set(allocated_entity_ids) or len(actual_ids) != len(set(actual_ids)):
        return None, ValueError(
            f"entity_id_set_mismatch:{actual_ids}:{allocated_entity_ids}"
        )
    definitions = {
        str(definition.get("field_id") or ""): dict(definition)
        for definition in field_definitions
        if str(definition.get("field_id") or "")
    }
    allowed_fields = _PRESENTATION_FIELDS | set(definitions)
    for row in rows:
        if str(row.get("kind") or "") != expected_entity_kind:
            return None, ValueError(
                f"profile_entity_kind_mismatch:{row.get('id')}:{row.get('kind')}"
            )
        unknown = set(row) - allowed_fields
        if unknown:
            return None, ValueError(
                f"unknown_profile_fields:{row.get('id')}:{','.join(sorted(unknown))}"
            )
        for field_id, definition in definitions.items():
            value = row.get(field_id)
            required = bool(definition.get("required", False))
            missing = value is None or value == "" or (
                required and _sequence(value) and not value
            )
            if missing:
                if required:
                    return None, ValueError(
                        f"missing_required_profile_field:{row.get('id')}:{field_id}"
                    )
                continue
            if not _valid_value(value, definition):
                return None, ValueError(
                    f"invalid_profile_field_type:{row.get('id')}:{field_id}"
                )
    if semantic_validator is not None:
        try:
            semantic_validator(candidate)
        except Exception as exc:
            return None, exc
    return candidate, None


__all__ = ["validate_recovered_profile_payload"]
