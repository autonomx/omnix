from scripts.export_gateway_openapi import _require_serialized_defaults, _stabilize_equivalent_io_schemas
import json
from pathlib import Path


def test_config_schema_aliases_rewrite_request_and_response_references():
    reference = {"$ref": "#/components/schemas/AssistantToolsConfigPayload"}
    schema = {
        "components": {"schemas": {"AssistantToolsConfigPayload": {"type": "object"}}},
        "paths": {"/config": {"post": {
            "requestBody": {"content": {"application/json": {"schema": dict(reference)}}},
            "responses": {"200": {"content": {"application/json": {"schema": dict(reference)}}}},
        }}},
    }
    _stabilize_equivalent_io_schemas(schema)
    operation = schema["paths"]["/config"]["post"]
    assert operation["requestBody"]["content"]["application/json"]["schema"]["$ref"].endswith("AssistantToolsConfigPayload-Input")
    assert operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith("AssistantToolsConfigPayload-Output")
    assert "AssistantToolsConfigPayload" not in schema["components"]["schemas"]


def test_generated_gateway_schema_has_no_unresolved_local_references():
    path = Path(__file__).resolve().parents[3] / "src/apps/web/src/api/generated/openapi.json"
    schema = json.loads(path.read_text(encoding="utf-8"))

    def check(value):
        if isinstance(value, dict):
            reference = value.get("$ref", "")
            if reference.startswith("#/"):
                target = schema
                for key in reference[2:].split("/"):
                    target = target[key.replace("~1", "/").replace("~0", "~")]
            for child in value.values():
                check(child)
        elif isinstance(value, list):
            for child in value:
                check(child)

    check(schema)


def test_response_only_schemas_require_their_defaulted_fields():
    def ref(name):
        return {"$ref": f"#/components/schemas/{name}"}

    def body(name):
        return {"content": {"application/json": {"schema": ref(name)}}}

    defaulted = {"properties": {"id": {"type": "string"}, "status": {"default": "queued"}, "note": {"default": None}}, "required": ["id"]}
    schema = {
        "components": {"schemas": {
            "Job": {**defaulted, "properties": {**defaulted["properties"], "stage": ref("Stage")}},
            "Stage": {"properties": {"label": {"default": ""}}},
            "Create": {"properties": {"priority": {"default": 0}}},
            "Shared": {"properties": {"flag": {"default": False}}},
            "Sparse": {"properties": {"extra": {"default": None}}},
        }},
        "paths": {
            "/jobs": {"post": {"requestBody": body("Create"), "responses": {"200": body("Job")}}},
            "/shared": {"post": {"requestBody": body("Shared"), "responses": {"200": body("Shared")}}},
            "/sparse": {"get": {"responses": {"200": body("Sparse")}}},
        },
    }

    _require_serialized_defaults(schema, frozenset({("GET", "/sparse")}))

    schemas = schema["components"]["schemas"]
    assert schemas["Job"]["required"] == ["id", "status", "note"]
    assert schemas["Stage"]["required"] == ["label"]
    assert "required" not in schemas["Create"]
    assert "required" not in schemas["Shared"]
    assert "required" not in schemas["Sparse"]
