from __future__ import annotations

from tests.support.routers import effective_routes

import json
import sys
from pathlib import Path
from typing import Any

from fastapi.routing import APIRoute

from app.composition.gateway.main import create_gateway_app
from app.runtime.feature_catalog import FEATURE_CATALOG
from scripts.export_gateway_openapi import KERNEL_OWNER, ROUTE_OWNERS_FILE, normalize_contract, route_owners


_ROUTE_SURFACE_KEYS = ("openapi", "info", "paths")
_INTERNAL_JOB_LIST_PARAMETERS = {"limit", "full"}
_DOCUMENTED_NON_JSON_RESPONSES = {
    ("DELETE", "/api/trading/notifications/email"),
    ("DELETE", "/api/trading/notifications/push/subscriptions/{subscription_id}"),
    ("GET", "/api/trading/snapshots/{snapshot_id}.png"),
    ("DELETE", "/api/trading/snapshots/{snapshot_id}"),
    ("DELETE", "/api/audiobook/projects/{project_id}"),
    ("GET", "/api/audiobook/projects/{project_id}/source/download"),
    ("GET", "/api/audiobook/projects/{project_id}/cover"),
    ("GET", "/api/audiobook/projects/{project_id}/previews/{job_id}/audio"),
    ("GET", "/api/audiobook/projects/{project_id}/exports/{export_id}/download"),
    ("GET", "/api/assistant/tools/connect/google/callback"),
    ("GET", "/api/assistant/tools/connect/github/callback"),
    ("GET", "/api/assets/{asset_id}/audio"),
    ("GET", "/api/assets/{asset_id}/download"),
    ("GET", "/api/auth/local/callback"),
    ("GET", "/api/auth/oidc/login"),
    ("GET", "/api/auth/oidc/callback"),
    ("POST", "/api/auth/logout"),
    ("POST", "/api/auth/email"),
    ("POST", "/api/auth/invites/{invite_id}/revoke"),
    ("GET", "/api/auth/google/login"),
    ("GET", "/api/auth/google/callback"),
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
    ("GET", "/events"),
    ("POST", "/api/assistant/context/chat/sessions/{session_id}/messages/stream"),
    ("POST", "/api/chat/sessions/{session_id}/live-call/greeting/stream"),
    ("POST", "/api/live/speculation/sessions/{session_id}/stream"),
    ("POST", "/api/live/speculation/sessions/{session_id}/{generation_id}/stream"),
    ("POST", "/api/live/speculation/sessions/{session_id}/start-stream"),
    ("GET", "/metrics"),
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
    generated_path = repo_root / "web" / "src" / "api" / "generated" / "openapi.json"

    generated_schema = _normalize_openapi(_route_surface(json.loads(generated_path.read_text(encoding="utf-8"))))
    app = create_gateway_app()
    live_schema = normalize_contract(app.openapi(), app)
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

    checked = 0
    for effective in effective_routes(app):
        route = effective.original_route
        if not isinstance(route, APIRoute) or not effective.include_in_schema:
            continue
        checked += 1
        route_path = effective.path.replace(":path}", "}")
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

    assert checked > 100, "route walk must see the composed feature routes"
    assert model_less_routes <= _DOCUMENTED_NON_JSON_RESPONSES


def test_generated_route_owners_are_current() -> None:
    generated_dir = Path(__file__).resolve().parents[3] / "web" / "src" / "api" / "generated"
    generated = json.loads((generated_dir / ROUTE_OWNERS_FILE).read_text(encoding="utf-8"))["operations"]
    app = create_gateway_app()
    current = route_owners(normalize_contract(app.openapi(), app), app.state.route_owners)

    assert generated == current, "route owners are stale; run `npm --workspace @omnix/web run api:schema`"
    assert set(current.values()) <= {KERNEL_OWNER, *FEATURE_CATALOG}
    assert current["GET /api/trading/paper/accounts/{account_id}/protections/{instrument_id}"] == "trading"
    assert current["POST /api/jobs"] == KERNEL_OWNER
