from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from app.gateway.main import create_gateway_app


_ROUTE_SURFACE_KEYS = ("openapi", "info", "paths")
_INTERNAL_JOB_LIST_PARAMETERS = {"limit", "full"}


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
    surface = {key: schema.get(key) for key in _ROUTE_SURFACE_KEYS}
    paths = surface.get("paths")
    jobs_get = paths.get("/api/jobs", {}).get("get") if isinstance(paths, dict) else None
    if isinstance(jobs_get, dict):
        parameters = jobs_get.get("parameters")
        if isinstance(parameters, list):
            public_parameters = [
                parameter
                for parameter in parameters
                if not (
                    isinstance(parameter, dict)
                    and parameter.get("in") == "query"
                    and parameter.get("name") in _INTERNAL_JOB_LIST_PARAMETERS
                )
            ]
            if public_parameters:
                jobs_get["parameters"] = public_parameters
            else:
                jobs_get.pop("parameters", None)
                responses = jobs_get.get("responses")
                if isinstance(responses, dict):
                    responses.pop("422", None)
    return surface


def test_generated_gateway_openapi_schema_is_current() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    generated_path = repo_root / "src" / "apps" / "web" / "src" / "api" / "generated" / "openapi.json"

    generated_schema = _normalize_openapi(_route_surface(json.loads(generated_path.read_text(encoding="utf-8"))))
    current_schema = _normalize_openapi(_route_surface(create_gateway_app().openapi()))

    if generated_schema != current_schema:
        print(
            "Generated gateway OpenAPI route surface is stale. "
            "Run `npm --workspace @omnix/web run api:schema` and commit the result.",
            file=sys.stderr,
        )

    assert generated_schema == current_schema
