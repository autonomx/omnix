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
    assert "required" not in schemas["Sparse"]
    # A schema both directions use is split: the response requires its defaults, the request copy does not.
    assert schemas["Shared"]["required"] == ["flag"]
    assert "required" not in schemas["Shared-Input"]
    shared = schema["paths"]["/shared"]["post"]
    assert shared["requestBody"]["content"]["application/json"]["schema"]["$ref"].endswith("/Shared-Input")
    assert shared["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith("/Shared")


def test_a_split_schema_request_copy_references_request_copies():
    def ref(name):
        return {"$ref": f"#/components/schemas/{name}"}

    schema = {
        "components": {"schemas": {
            "Outer": {"properties": {"inner": ref("Inner"), "plain": ref("Plain")}},
            "Inner": {"properties": {"size": {"default": 1}}},
            "Plain": {"properties": {"name": {"type": "string"}}},
            "Create": {"properties": {"inner": ref("Inner")}},
        }},
        "paths": {
            "/x": {"put": {
                "requestBody": {"content": {"application/json": {"schema": ref("Outer")}}},
                "responses": {"200": {"content": {"application/json": {"schema": ref("Outer")}}}},
            }},
            "/create": {"post": {"requestBody": {"content": {"application/json": {"schema": ref("Create")}}}}},
        },
    }

    _require_serialized_defaults(schema)

    schemas = schema["components"]["schemas"]
    assert schemas["Outer-Input"]["properties"]["inner"]["$ref"].endswith("/Inner-Input")
    assert schemas["Outer"]["properties"]["inner"]["$ref"].endswith("/Inner")
    assert "Plain-Input" not in schemas
    # A request-only schema references the request copy as well.
    assert schemas["Create"]["properties"]["inner"]["$ref"].endswith("/Inner-Input")


def test_factory_defaults_count_as_defaults():
    schema = {
        "components": {"schemas": {"Alert": {"properties": {"id": {"type": "string"}, "tags": {"type": "array"}}, "required": ["id"]}}},
        "paths": {"/alerts": {"get": {"responses": {"200": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/Alert"}}}}}}}},
    }

    _require_serialized_defaults(schema, factory_fields={"Alert": frozenset({"tags"})})

    assert schema["components"]["schemas"]["Alert"]["required"] == ["id", "tags"]
