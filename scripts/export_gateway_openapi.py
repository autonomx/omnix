"""Export the thin Omnix gateway OpenAPI schema to disk."""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _stabilize_integral_json_numbers(value: object) -> object:
    """Canonicalize whole-valued floats so generated OpenAPI is byte-stable.

    Pydantic may emit numeric constraints such as 0 or 0.0 depending on the
    runtime path that constructed an equivalent core schema. JSON Schema
    treats those values identically, but Omnix checks the generated contract
    byte-for-byte. Normalize only exact whole-valued floats; non-integral
    values, booleans, strings, and all schema structure remain unchanged.
    """

    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, list):
        return [_stabilize_integral_json_numbers(item) for item in value]
    if isinstance(value, dict):
        return {
            key: _stabilize_integral_json_numbers(item)
            for key, item in value.items()
        }
    return value

def _stabilize_equivalent_io_schemas(schema: dict[str, object]) -> None:
    """Preserve legacy input/output component identities when they are equivalent.

    FastAPI/Pydantic releases can deduplicate a model's validation and
    serialization schemas when their structures are identical. Omnix commits the
    generated gateway contract, so that implementation-level optimization would
    otherwise create unrelated contract churn even though the public schema did
    not change.

    AssistantToolsConfigPayload historically has explicit ``-Input`` and
    ``-Output`` components, and the two structures are intentionally identical.
    If the generator collapses them to one equivalent component, expand that
    component back to the stable checked-in identities. This changes names only;
    it never rewrites fields, requirements, types, or endpoint paths.
    """

    components = schema.get("components")
    if not isinstance(components, dict):
        return
    schemas = components.get("schemas")
    if not isinstance(schemas, dict):
        return

    canonical_name = "AssistantToolsConfigPayload"
    input_name = f"{canonical_name}-Input"
    output_name = f"{canonical_name}-Output"
    value = schemas.get(canonical_name)
    if (
        not isinstance(value, dict)
        or input_name in schemas
        or output_name in schemas
    ):
        return

    # Keep this normalization deliberately narrow. If future input/output
    # contracts genuinely diverge, FastAPI will emit distinct components and
    # this branch will not run.
    schemas[input_name] = copy.deepcopy(value)
    schemas[output_name] = copy.deepcopy(value)
    del schemas[canonical_name]

    canonical_ref = f"#/components/schemas/{canonical_name}"

    def rewrite(value: object, *, request: bool = False) -> None:
        if isinstance(value, list):
            for item in value:
                rewrite(item, request=request)
        elif isinstance(value, dict):
            if value.get("$ref") == canonical_ref:
                value["$ref"] = f"#/components/schemas/{input_name if request else output_name}"
            for key, item in value.items():
                rewrite(item, request=request or key == "requestBody")

    rewrite(schema)


_SCHEMA_REF = "#/components/schemas/"


def _referenced_schemas(value: object) -> set[str]:
    names: set[str] = set()
    if isinstance(value, dict):
        reference = value.get("$ref")
        if isinstance(reference, str) and reference.startswith(_SCHEMA_REF):
            names.add(reference[len(_SCHEMA_REF):])
        for item in value.values():
            names |= _referenced_schemas(item)
    elif isinstance(value, list):
        for item in value:
            names |= _referenced_schemas(item)
    return names


def _closure(roots: set[str], schemas: dict[str, object]) -> set[str]:
    seen: set[str] = set()
    pending = list(roots)
    while pending:
        name = pending.pop()
        if name in seen or name not in schemas:
            continue
        seen.add(name)
        pending.extend(_referenced_schemas(schemas[name]) - seen)
    return seen


def _require_serialized_defaults(
    schema: dict[str, object],
    lenient_operations: frozenset[tuple[str, str]] = frozenset(),
) -> None:
    """Mark fields with defaults as required in schemas only responses use (WP-9.3).

    Pydantic omits fields with defaults from ``required``, which is right for
    request bodies (callers may leave them out) but not for responses: the
    gateway always serializes them. Clients generated from the contract would
    otherwise treat every defaulted response field as possibly missing.
    Schemas reachable from a request body or parameter keep Pydantic's view, and
    so do responses of operations that drop unset, None or default fields
    (``lenient_operations``, as ``(METHOD, path)``).
    """

    components = schema.get("components")
    schemas = components.get("schemas") if isinstance(components, dict) else None
    paths = schema.get("paths")
    if not isinstance(schemas, dict) or not isinstance(paths, dict):
        return
    inputs: set[str] = set()
    outputs: set[str] = set()
    lenient: set[str] = set()
    for path, operations in paths.items():
        if not isinstance(operations, dict):
            continue
        for method, operation in operations.items():
            if not isinstance(operation, dict):
                continue
            inputs |= _referenced_schemas(operation.get("requestBody")) | _referenced_schemas(operation.get("parameters"))
            responses = _referenced_schemas(operation.get("responses"))
            outputs |= responses
            if (method.upper(), path) in lenient_operations:
                lenient |= responses
    response_only = _closure(outputs, schemas) - _closure(inputs, schemas) - _closure(lenient, schemas)
    for name in sorted(response_only):
        component = schemas[name]
        properties = component.get("properties") if isinstance(component, dict) else None
        if not isinstance(properties, dict):
            continue
        required = list(component.get("required", []))
        required += [key for key, value in properties.items() if isinstance(value, dict) and "default" in value and key not in required]
        if required:
            component["required"] = required


def _lenient_operations(app: object) -> frozenset[tuple[str, str]]:
    from fastapi.routing import APIRoute

    operations: set[tuple[str, str]] = set()
    for route in getattr(app, "routes", []):
        if isinstance(route, APIRoute) and (
            route.response_model_exclude_unset
            or route.response_model_exclude_none
            or route.response_model_exclude_defaults
        ):
            operations.update((method, route.path) for method in route.methods)
    return frozenset(operations)


def export_schema() -> dict[str, object]:
    """Return the gateway OpenAPI document exactly as the web contract stores it."""
    src_dir = _repo_root() / "src"
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))

    from app.gateway.main import create_gateway_app

    app = create_gateway_app()
    schema = app.openapi()
    _stabilize_equivalent_io_schemas(schema)
    _require_serialized_defaults(schema, _lenient_operations(app))
    return _stabilize_integral_json_numbers(schema)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: python scripts/export_gateway_openapi.py <output-json>", file=sys.stderr)
        return 2

    output_path = (_repo_root() / argv[1]).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    schema = export_schema()
    output_path.write_text(
        json.dumps(schema, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
