from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.platform.chat import ChatSessionStore
from app.composition.gateway.main import create_gateway_app
from app.runtime.config import RuntimeConfig
from app.runtime.feature_catalog import FEATURE_CATALOG, enabled_feature_ids, load_feature
from app.security.service_token import require_service_token
from tests.support.in_memory_jobs import InMemoryJobStore


def _paths(app) -> set[str]:
    return set(app.openapi()["paths"])


def _dependency_closure(feature_id: str) -> frozenset[str]:
    dependencies: set[str] = set()
    pending = list(load_feature(feature_id).depends_on)
    while pending:
        dependency = pending.pop()
        if dependency in dependencies:
            continue
        dependencies.add(dependency)
        pending.extend(load_feature(dependency).depends_on)
    return frozenset(dependencies)


def _provider_free_app(config: RuntimeConfig, path: Path, monkeypatch):
    path.mkdir(parents=True, exist_ok=True)
    registrations: dict[str, list[tuple[object, bool]]] = {}
    original_include_router = FastAPI.include_router
    feature_ids_by_guard = {
        "feature_guard_" + feature_id.replace("-", "_"): feature_id
        for feature_id in FEATURE_CATALOG
    }

    def capture_include_router(app, router, *args, **kwargs):
        for dependency in kwargs.get("dependencies") or ():
            name = getattr(getattr(dependency, "dependency", None), "__name__", "")
            feature_id = feature_ids_by_guard.get(name)
            if feature_id is not None:
                registrations.setdefault(feature_id, []).append(
                    (router, kwargs.get("include_in_schema", True))
                )
        return original_include_router(app, router, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(FastAPI, "include_router", capture_include_router)
        app = create_gateway_app(
            runtime_config=config,
            job_store_factory=lambda: InMemoryJobStore(path / "jobs"),
            chat_store_factory=lambda: ChatSessionStore(path=path / "chat.json"),
        )
    return app, registrations


def test_audiobook_feature_is_in_lazy_catalog() -> None:
    assert FEATURE_CATALOG["audiobook"] == "app.apps.audiobook.feature:FEATURE"
    feature = load_feature("audiobook")
    assert feature.id == "audiobook"
    assert len(feature.routers) == 2
    assert len(feature.background_workers) == 1


def test_audiobook_feature_is_enabled_by_default() -> None:
    config = RuntimeConfig()
    assert "audiobook" in enabled_feature_ids(config)
    app = create_gateway_app(runtime_config=config)
    assert "/api/audiobook/projects" in _paths(app)
    assert "audiobook" in app.state.feature_modules
    client = TestClient(
        app,
        base_url="http://localhost",
        headers={"X-Omnix-Client": "test"},
    )
    with client.websocket_connect(
        "/ws/audiobook", headers={"Host": "localhost"}
    ) as websocket:
        websocket.send_json({"type": "stop"})
        assert websocket.receive_json() == {"type": "stopped"}


def test_audiobook_feature_can_be_disabled_without_affecting_kernel_routes() -> None:
    config = RuntimeConfig(disabled_features=("audiobook",))
    app = create_gateway_app(runtime_config=config)
    paths = _paths(app)
    assert "/health" in paths
    assert "/api/runtime/status" in paths
    assert all(not path.startswith("/api/audiobook") for path in paths)
    assert "audiobook" not in app.state.feature_modules
    client = TestClient(
        app,
        base_url="http://localhost",
        headers={"X-Omnix-Client": "test"},
    )
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(
            "/ws/audiobook", headers={"Host": "localhost"}
        ):
            pass


def test_image_feature_is_mounted_from_its_routers_and_can_be_disabled() -> None:
    enabled = create_gateway_app(runtime_config=RuntimeConfig())
    enabled_paths = _paths(enabled)
    assert "/api/image-generation/references" in enabled_paths
    assert "/api/image-generation/jobs" in enabled_paths
    assert "/api/image-generation/assets" in enabled_paths
    assert "/api/assets/{asset_id}/file" in enabled_paths
    assert "image" in enabled.state.feature_modules

    # Characters implements image's avatar port (ADR-0016), so disabling image
    # disables characters and the features built on it.
    dependents = {feature_id for feature_id in FEATURE_CATALOG if "image" in _dependency_closure(feature_id)}
    disabled = create_gateway_app(runtime_config=RuntimeConfig(disabled_features=("image", *sorted(dependents))))
    disabled_paths = _paths(disabled)
    assert "/health" in disabled_paths
    assert "/api/runtime/status" in disabled_paths
    assert not any(path.startswith("/api/image-generation/") for path in disabled_paths)
    assert "/api/assets/{asset_id}/file" not in disabled_paths
    assert "image" not in disabled.state.feature_modules
    assert "characters" in dependents


def test_unknown_feature_configuration_fails_closed() -> None:
    config = RuntimeConfig(enabled_features=("audiobook", "missing-feature"))
    try:
        enabled_feature_ids(config)
    except ValueError as exc:
        assert "missing-feature" in str(exc)
    else:
        raise AssertionError("unknown feature id must fail startup")


def test_internal_service_token_route_is_hidden_by_feature_composition(monkeypatch) -> None:
    hidden_routers = []
    original_include_router = FastAPI.include_router

    def capture_include_router(app, router, *args, **kwargs):
        if kwargs.get("include_in_schema") is False:
            hidden_routers.append(router)
        return original_include_router(app, router, *args, **kwargs)

    monkeypatch.setattr(FastAPI, "include_router", capture_include_router)
    app = create_gateway_app(runtime_config=RuntimeConfig())
    route = next(
        route
        for router in hidden_routers
        for route in router.routes
        if getattr(route, "path", None) == "/api/hermes/assistant/tools/execute"
    )
    assert "/api/hermes/assistant/tools/execute" not in _paths(app)
    assert any(
        dependency.call is require_service_token
        for dependency in route.dependant.dependencies
    )


def test_every_optional_feature_can_be_disabled_with_its_dependents(
    tmp_path: Path,
    monkeypatch,
) -> None:
    feature_ids = frozenset(FEATURE_CATALOG)
    for feature_id in sorted(feature_ids):
        dependencies = _dependency_closure(feature_id)
        minimal_enabled = dependencies | {feature_id}
        disabled_with_feature = feature_ids - minimal_enabled
        disabled_without_feature = feature_ids - dependencies
        disabled_config = RuntimeConfig(
            enabled_features=tuple(sorted(feature_ids)),
            disabled_features=tuple(sorted(disabled_without_feature)),
        )
        enabled_config = RuntimeConfig(
            enabled_features=tuple(sorted(feature_ids)),
            disabled_features=tuple(sorted(disabled_with_feature)),
        )
        disabled_app, disabled_registrations = _provider_free_app(
            disabled_config,
            tmp_path / "disabled" / feature_id,
            monkeypatch,
        )
        enabled_app, enabled_registrations = _provider_free_app(
            enabled_config,
            tmp_path / "enabled" / feature_id,
            monkeypatch,
        )
        disabled_paths = _paths(disabled_app)
        enabled_paths = _paths(enabled_app)
        feature_paths = enabled_paths - disabled_paths
        feature = load_feature(feature_id)
        exposes_routers = bool(feature.routers or feature.internal_routers)
        if exposes_routers:
            assert feature_id in enabled_registrations
            assert feature_id not in disabled_registrations
            public_paths = {
                re.sub(r"\{([^{}:]+):[^{}]+\}", r"{\1}", route.path)
                for router, include_in_schema in enabled_registrations[feature_id]
                if include_in_schema
                for route in getattr(router, "routes", ())
                if getattr(route, "include_in_schema", True)
                and getattr(route, "path", None)
            }
            if public_paths:
                assert feature_paths, f"disabling {feature_id} did not remove its OpenAPI routes"
        else:
            assert feature_id not in enabled_registrations
            assert not feature_paths, f"route-less feature {feature_id} mounted OpenAPI paths"
        assert feature_id not in disabled_app.state.feature_modules
        assert feature_id in enabled_app.state.feature_modules

        with TestClient(
            disabled_app,
            base_url="http://127.0.0.1",
            headers={"X-Omnix-Client": "test"},
        ) as client:
            assert client.get("/health").status_code == 200
            assert client.get("/api/runtime/status").status_code == 200
