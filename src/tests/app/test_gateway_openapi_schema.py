from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from fastapi.routing import APIRoute

from app.gateway.main import create_gateway_app
from scripts.export_gateway_openapi import _stabilize_equivalent_io_schemas


_ROUTE_SURFACE_KEYS = ("openapi", "info", "paths")
_INTERNAL_JOB_LIST_PARAMETERS = {"limit", "full"}
_DOCUMENTED_NON_JSON_RESPONSES = {
    ("DELETE", "/api/audiobook/projects/{project_id}"),
    ("GET", "/api/audiobook/projects/{project_id}/source/download"),
    ("GET", "/api/audiobook/projects/{project_id}/cover"),
    ("GET", "/api/audiobook/projects/{project_id}/previews/{job_id}/audio"),
    ("GET", "/api/audiobook/projects/{project_id}/exports/{export_id}/download"),
    ("GET", "/api/assistant/tools/connect/google/callback"),
    ("GET", "/api/assistant/tools/connect/github/callback"),
    ("GET", "/api/agent-runs/{run_id}/events/stream"),
    ("GET", "/api/agent-runs/{run_id}/workspace-preview/{asset_path}"),
    ("GET", "/api/task-graph-runs/{run_id}/events/stream"),
    ("GET", "/api/character-live2d/runtime/{filename}"),
    ("GET", "/api/character-live2d/assets/{asset_id}/{asset_path}"),
    ("GET", "/api/assets/{asset_id}/file"),
    ("GET", "/api/voice/cues/{voice_id}/{cue_id}/{variant_id}.wav"),
    ("GET", "/api/rpg/worlds/{world_id}/export"),
    ("DELETE", "/api/trading/strategies/{strategy_id}"),
    ("POST", "/api/chat/sessions/{session_id}/messages/stream"),
    ("GET", "/api/jobs/events"),
}


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
    live_schema = create_gateway_app().openapi()
    _stabilize_equivalent_io_schemas(live_schema)
    current_schema = _normalize_openapi(_route_surface(live_schema))

    if generated_schema != current_schema:
        print(
            "Generated gateway OpenAPI route surface is stale. "
            "Run `npm --workspace @omnix/web run api:schema` and commit the result.",
            file=sys.stderr,
        )

    assert generated_schema == current_schema


def test_browser_routes_have_typed_contracts_or_documented_transport_responses() -> None:
    app = create_gateway_app()
    schema = app.openapi()
    repo_root = Path(__file__).resolve().parents[3]
    transport_inventory = (repo_root / "docs" / "architecture" / "api-transport-exceptions.md").read_text(
        encoding="utf-8"
    )
    model_less_routes: set[tuple[str, str]] = set()

    for route in app.routes:
        if not isinstance(route, APIRoute) or not route.include_in_schema:
            continue
        route_path = route.path.replace(":path}", "}")
        methods = route.methods or {"GET"}
        for method in methods:
            operation = schema["paths"].get(route_path, {}).get(method.lower())
            assert operation is not None, f"missing OpenAPI operation for {method} {route_path}"
            request_body = operation.get("requestBody")
            if request_body is not None:
                body_content = request_body.get("content", {})
                assert body_content, f"request body has no media schema for {method} {route_path}"
                assert all(
                    isinstance(media.get("schema"), dict) and media["schema"]
                    for media in body_content.values()
                ), f"request body has an empty schema for {method} {route_path}"
            if route.response_model is None:
                key = (method.upper(), route_path)
                model_less_routes.add(key)
                assert key in _DOCUMENTED_NON_JSON_RESPONSES
                assert route_path in transport_inventory

    assert model_less_routes <= _DOCUMENTED_NON_JSON_RESPONSES
