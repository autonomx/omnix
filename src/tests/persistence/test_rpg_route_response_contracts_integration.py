"""Real RPG and Hermes responses match the 200 response their routes publish (WP-8.6).

The published models (``web_contracts``, ``route_contracts``) document and never
validate a response, so nothing else notices when a builder drifts from its
model. These routes run against PostgreSQL with the real services, and each
response is validated against the model its route publishes.
"""
from __future__ import annotations

import os
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from pydantic import TypeAdapter

from app.apps.rpg.edge.api.feature_routes.rpg_debug_routes import register_rpg_debug_routes
from app.apps.rpg.edge.api.feature_routes.rpg_progressive_map_routes import (
    register_rpg_progressive_map_routes,
)
from app.apps.rpg.edge.api.feature_routes.rpg_world_authoring_routes import (
    register_rpg_world_authoring_routes,
)
from app.apps.rpg.edge.api.feature_routes.rpg_world_routes import register_rpg_world_routes
from app.apps.rpg.edge.hermes.api import router as hermes_router
from app.apps.rpg.edge.hermes.approved_routes import hermes_rpg_approved_bp
from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.identity_service import ensure_local_identity
from app.persistence.migrations import apply_migrations
from app.runtime.tenant_context import install_process_tenant
from tests.support.routers import effective_routes, include_router_registrar

pytestmark = pytest.mark.skipif(
    not os.environ.get("OMNIX_TEST_DATABASE_URL"),
    reason="OMNIX_TEST_DATABASE_URL is required for PostgreSQL integration tests",
)


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch):
    database = PostgresDatabase(
        DatabaseSettings(
            url=os.environ["OMNIX_TEST_DATABASE_URL"],
            pool_min=1,
            pool_max=3,
            connect_timeout_seconds=10,
            statement_timeout_ms=30_000,
            application_name="omnix-rpg-route-contracts",
        )
    )
    apply_migrations(database)
    with database.transaction() as connection:
        connection.execute(
            "TRUNCATE omnix_rpg_world_generation_runs, omnix_rpg_map_blueprint_revisions, "
            "omnix_rpg_campaign_world_bindings, omnix_rpg_scenario_revisions, "
            "omnix_rpg_scenarios, omnix_rpg_world_releases, omnix_rpg_world_revisions, "
            "omnix_rpg_world_topics, omnix_rpg_worlds CASCADE"
        )
    install_process_tenant(ensure_local_identity(database))
    monkeypatch.setenv("RPG_TEST_MODE", "deterministic")
    monkeypatch.setattr(
        "app.apps.rpg.genesis.worlds.postgres_service.kick_world_generation_worker",
        lambda **_kwargs: False,
    )
    app = FastAPI()
    for registrar in (
        register_rpg_world_routes,
        register_rpg_world_authoring_routes,
        register_rpg_progressive_map_routes,
        register_rpg_debug_routes,
    ):
        include_router_registrar(app, registrar)
    app.include_router(hermes_router)
    app.include_router(hermes_rpg_approved_bp)
    try:
        yield app, TestClient(app)
    finally:
        database.close()


def _published_model(app: FastAPI, method: str, path: str) -> Any:
    for effective in effective_routes(app):
        route = effective.original_route
        if isinstance(route, APIRoute) and effective.path == path and method in (route.methods or ()):
            return route.responses[200]["model"]
    raise AssertionError(f"no route {method} {path}")


def _call(app: FastAPI, client: TestClient, method: str, template: str, **kwargs: Any) -> dict[str, Any]:
    path_params = kwargs.pop("path", {})
    response = client.request(method, template.format(**path_params), **kwargs)
    assert response.status_code == 200, (method, template, response.text)
    body = response.json()
    TypeAdapter(_published_model(app, method, template)).validate_python(body)
    return body


def test_world_library_and_authoring_responses_match_their_published_models(client) -> None:
    app, http = client
    world = _call(app, http, "POST", "/api/rpg/worlds", json={"title": "The Glass Sea", "seed": 3})["world"]
    world_id = {"world_id": world["id"]}
    _call(app, http, "GET", "/api/rpg/worlds")
    world = _call(
        app, http, "PATCH", "/api/rpg/worlds/{world_id}", path=world_id,
        json={"expected_draft_revision": world["draft_revision"], "tone": "quiet wonder"},
    )["world"]
    content = {"entities": [{"id": "location:harbor", "kind": "location", "name": "Harbor"}]}
    _call(
        app, http, "POST", "/api/rpg/worlds/{world_id}/topics", path=world_id,
        json={"topic_id": "locations", "content": content},
    )
    topic = {**world_id, "topic_id": "locations"}
    _call(app, http, "GET", "/api/rpg/worlds/{world_id}/topics/{topic_id}", path=topic)
    _call(
        app, http, "GET", "/api/rpg/worlds/{world_id}/topics/{topic_id}/entities/{entity_id}",
        path={**topic, "entity_id": "location:harbor"},
    )
    _call(app, http, "GET", "/api/rpg/worlds/{world_id}/topic-history", path=world_id)
    _call(
        app, http, "GET", "/api/rpg/worlds/{world_id}/authoring-sections/{section_id}",
        path={**world_id, "section_id": "overview"},
    )
    _call(app, http, "GET", "/api/rpg/worlds/{world_id}/authorship-audit", path=world_id)
    _call(
        app, http, "POST", "/api/rpg/worlds/{world_id}/authorship-audit/remediate", path=world_id,
        json={"queue_regeneration": False},
    )
    _call(app, http, "GET", "/api/rpg/worlds/{world_id}/map-blueprints", path=world_id)
    _call(app, http, "POST", "/api/rpg/worlds/{world_id}/map-blueprints/materialize", path=world_id)
    _call(app, http, "GET", "/api/rpg/worlds/{world_id}/materialization-jobs", path=world_id)
    _call(app, http, "GET", "/api/rpg/world-generation/diagnostics")

    scenario = _call(
        app, http, "POST", "/api/rpg/scenarios", json={"world_id": world["id"], "title": "First Light"},
    )["scenario"]
    scenario_id = {"scenario_id": scenario["id"]}
    _call(app, http, "POST", "/api/rpg/scenarios/{scenario_id}/archive", path=scenario_id)
    _call(app, http, "POST", "/api/rpg/scenarios/{scenario_id}/restore", path=scenario_id)
    _call(app, http, "POST", "/api/rpg/worlds/{world_id}/archive", path=world_id)
    restored = _call(app, http, "POST", "/api/rpg/worlds/{world_id}/restore", path=world_id)
    assert restored["idempotent"] is False


def test_debug_and_hermes_responses_match_their_published_models(client) -> None:
    app, http = client
    _call(app, http, "GET", "/api/rpg/debug/log-status")
    _call(app, http, "POST", "/api/rpg/debug/event", json={"event": "client.contract_check"})
    _call(app, http, "GET", "/api/hermes/capabilities")
    _call(app, http, "GET", "/api/hermes/capabilities", params={"mode": "rpg"})
    _call(app, http, "POST", "/api/hermes/adapter/preview", json={"mode": "rpg", "intent": "suggest"})
    _call(app, http, "POST", "/api/hermes/lookup", json={"name": "unknown_readout", "args": {}})
    _call(app, http, "POST", "/api/hermes/rpg/context", json={"session_id": ""})
    _call(
        app, http, "POST", "/api/hermes/rpg/context-pack",
        json={"session": {"session_id": "session:contract", "state": {"location": "Harbor"}}},
    )
    _call(app, http, "POST", "/api/hermes/rpg/sequence/plan", json={"sequence": {"items": []}})
    _call(app, http, "POST", "/api/hermes/rpg/sequence/execute-step", json={})
