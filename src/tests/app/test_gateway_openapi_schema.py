from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from app.gateway.main import create_gateway_app


_ROUTE_SURFACE_KEYS = ("openapi", "info", "paths")


def _normalize_openapi(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _normalize_openapi(item) for key, item in sorted(value.items())}
    if isinstance(value, list):
        normalized_items = [_normalize_openapi(item) for item in value]
        if all(isinstance(item, str) for item in normalized_items):
            return sorted(normalized_items)
        return normalized_items
    return value


def _route_surface(schema: dict[str, Any]) -> dict[str, Any]:
    return {key: schema.get(key) for key in _ROUTE_SURFACE_KEYS}


def test_generated_gateway_openapi_schema_is_current() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    generated_path = repo_root / "apps" / "web" / "src" / "api" / "generated" / "openapi.json"

    generated_schema = _normalize_openapi(_route_surface(json.loads(generated_path.read_text(encoding="utf-8"))))
    current_openapi = create_gateway_app().openapi()
    current_schema = _normalize_openapi(_route_surface(current_openapi))

    if generated_schema != current_schema:
        # Emit the exact generator output once so the stale base artifact can be repaired.
        print("OMNIX_OPENAPI_SCHEMA_BEGIN")
        print(json.dumps(current_openapi, indent=2, sort_keys=True))
        print("OMNIX_OPENAPI_SCHEMA_END")
        print(
            "Generated gateway OpenAPI route surface is stale. "
            "Run `npm --workspace @omnix/web run api:schema` and commit the result.",
            file=sys.stderr,
        )

    assert generated_schema == current_schema
