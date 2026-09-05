from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.agent_runtime.semantic_task import SemanticTask
from app.providers.structured.contracts import StructuredMode
from app.providers.structured.schema_projection import project_provider_schema


def _assert_all_object_properties_required(node: Any) -> None:
    if isinstance(node, list):
        for value in node:
            _assert_all_object_properties_required(value)
        return
    if not isinstance(node, Mapping):
        return

    properties = node.get("properties")
    if isinstance(properties, Mapping):
        assert node.get("required") == list(properties.keys())
    for value in node.values():
        _assert_all_object_properties_required(value)


def test_chatgpt_codex_semantic_task_schema_requires_every_property_recursively() -> None:
    schema = project_provider_schema(
        SemanticTask.model_json_schema(),
        mode=StructuredMode.JSON_SCHEMA,
        provider_name="chatgpt_codex",
        schema_profile="local",
    )

    _assert_all_object_properties_required(schema)

    subjects = schema["properties"]["subjects"]["items"]
    assert "kind" in subjects["properties"]
    assert "kind" in subjects["required"]
    assert any(
        branch.get("type") == "null"
        for branch in subjects["properties"]["kind"]["anyOf"]
    )

    operations = schema["properties"]["operations"]["items"]
    assert "subject_reference" in operations["required"]

    dependencies = schema["properties"]["data_dependencies"]["items"]
    assert {
        "target",
        "freshness",
        "as_of_date",
        "subject_reference",
        "required",
        "retrieval_mode",
    } <= set(dependencies["required"])


def test_chatgpt_codex_projection_preserves_defs_and_drops_lookarounds() -> None:
    source = {
        "type": "object",
        "properties": {
            "item": {"$ref": "#/$defs/Item"},
        },
        "required": ["item"],
        "$defs": {
            "Item": {
                "type": "object",
                "properties": {
                    "value": {
                        "type": "string",
                        "pattern": "^(?=x).+$",
                    },
                    "safe": {
                        "type": "string",
                        "pattern": "^[a-z]+$",
                    },
                },
            }
        },
    }

    schema = project_provider_schema(
        source,
        mode=StructuredMode.JSON_SCHEMA,
        provider_name="chatgpt_codex",
    )

    assert "$defs" in schema
    item = schema["$defs"]["Item"]
    assert set(item["required"]) == {"value", "safe"}
    assert "pattern" not in item["properties"]["value"]
    assert item["properties"]["safe"]["pattern"] == "^[a-z]+$"


def test_lmstudio_projection_does_not_force_optional_fields_required() -> None:
    schema = project_provider_schema(
        SemanticTask.model_json_schema(),
        mode=StructuredMode.JSON_SCHEMA,
        provider_name="lmstudio",
        schema_profile="local",
    )

    subjects = schema["properties"]["subjects"]["items"]
    assert "kind" in subjects["properties"]
    assert "kind" not in subjects.get("required", [])
