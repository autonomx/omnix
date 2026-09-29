from __future__ import annotations

import re
from pathlib import Path

from fastapi.routing import APIWebSocketRoute, APIRoute
from fastapi.testclient import TestClient

from app.chat import ChatSessionStore
from app.gateway.main import create_gateway_app
from app.runtime.config import RuntimeConfig
from app.runtime.feature_catalog import FEATURE_CATALOG, enabled_feature_ids, load_feature
from app.security.service_token import require_service_token
from tests.support.in_memory_jobs import InMemoryJobStore


def _paths(app) -> set[str]:
    return set(app.openapi()["paths"])


def _websocket_paths(app) -> set[str]:
    return {
        route.path
        for route in app.router.routes
        if isinstance(route, APIWebSocketRoute)
    }


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


def _http_paths(app) -> set[str]:
    return {
        re.sub(r"\{([^{}:]+):[^{}]+\}", r"{\1}", route.path)
        for route in app.routes
        if isinstance(route, APIRoute)
    }


def _provider_free_app(config: RuntimeConfig, path: Path):
    path.mkdir(parents=True, exist_ok=True)
    return create_gateway_app(
        runtime_config=config,
        job_store_factory=lambda: InMemoryJobStore(path / "jobs"),
        chat_store_factory=lambda: ChatSessionStore(path=path / "chat.json"),
    )


def test_audiobook_feature_is_in_lazy_catalog() -> None:
    assert FEATURE_CATALOG["audiobook"] == "app.audiobook.feature:FEATURE"
    feature = load_feature("audiobook")
    assert feature.id == "audiobook"
    assert len(feature.routers) == 2
    assert len(feature.background_workers) == 1


def test_audiobook_feature_is_enabled_by_default() -> None:
    config = RuntimeConfig()
    assert "audiobook" in enabled_feature_ids(config)
    app = create_gateway_app(runtime_config=config)
    assert "/api/audiobook/projects" in _paths(app)
    assert "/ws/audiobook" in _websocket_paths(app)
    assert "audiobook" in app.state.feature_modules


def test_audiobook_feature_can_be_disabled_without_affecting_kernel_routes() -> None:
    config = RuntimeConfig(disabled_features=("audiobook",))
    app = create_gateway_app(runtime_config=config)
    paths = _paths(app)
    assert "/health" in paths
    assert "/api/runtime/status" in paths
    assert all(not path.startswith("/api/audiobook") for path in paths)
    assert "/ws/audiobook" not in _websocket_paths(app)
    assert "audiobook" not in app.state.feature_modules


def test_image_feature_is_mounted_from_its_routers_and_can_be_disabled() -> None:
    enabled = create_gateway_app(runtime_config=RuntimeConfig())
    enabled_paths = _paths(enabled)
    assert "/api/image-generation/references" in enabled_paths
    assert "/api/image-generation/jobs" in enabled_paths
    assert "/api/image-generation/assets" in enabled_paths
    assert "/api/assets/{asset_id}/file" in enabled_paths
    assert "image" in enabled.state.feature_modules

    disabled = create_gateway_app(runtime_config=RuntimeConfig(disabled_features=("image",)))
    disabled_paths = _paths(disabled)
    assert "/health" in disabled_paths
    assert "/api/runtime/status" in disabled_paths
    assert not any(path.startswith("/api/image-generation/") for path in disabled_paths)
    assert "/api/assets/{asset_id}/file" not in disabled_paths
    assert "image" not in disabled.state.feature_modules


def test_unknown_feature_configuration_fails_closed() -> None:
    config = RuntimeConfig(enabled_features=("audiobook", "missing-feature"))
    try:
        enabled_feature_ids(config)
    except ValueError as exc:
        assert "missing-feature" in str(exc)
    else:
        raise AssertionError("unknown feature id must fail startup")


def test_internal_service_token_route_is_hidden_by_feature_composition() -> None:
    app = create_gateway_app(runtime_config=RuntimeConfig())
    route = next(
        route
        for route in app.routes
        if isinstance(route, APIRoute)
        and route.path == "/api/hermes/assistant/tools/execute"
    )
    assert "/api/hermes/assistant/tools/execute" not in _paths(app)
    assert any(
        dependency.call is require_service_token
        for dependency in route.dependant.dependencies
    )


def test_every_optional_feature_can_be_disabled_with_its_dependents(
    tmp_path: Path,
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
        disabled_app = _provider_free_app(
            disabled_config,
            tmp_path / "disabled" / feature_id,
        )
        enabled_app = _provider_free_app(
            enabled_config,
            tmp_path / "enabled" / feature_id,
        )
        disabled_paths = _http_paths(disabled_app) | _websocket_paths(disabled_app)
        enabled_paths = _http_paths(enabled_app) | _websocket_paths(enabled_app)
        feature_paths = enabled_paths - disabled_paths
        feature = load_feature(feature_id)
        exposes_routers = bool(feature.routers or feature.internal_routers)
        if exposes_routers:
            assert feature_paths, f"disabling {feature_id} did not remove any feature routes"
        else:
            assert not feature_paths, f"route-less feature {feature_id} mounted HTTP or WebSocket paths"
        assert feature_id not in disabled_app.state.feature_modules
        assert feature_id in enabled_app.state.feature_modules

        with TestClient(
            disabled_app,
            base_url="http://127.0.0.1",
            headers={"X-Omnix-Client": "test"},
        ) as client:
            assert client.get("/health").status_code == 200
            assert client.get("/api/runtime/status").status_code == 200

        # The public OpenAPI surface follows the same feature boundary.
        disabled_openapi_paths = _paths(disabled_app)
        enabled_openapi_paths = _paths(enabled_app)
        unowned_openapi_paths = enabled_openapi_paths - disabled_openapi_paths - feature_paths
        assert not unowned_openapi_paths, (
            f"{feature_id} OpenAPI paths escaped the feature route delta: "
            f"{sorted(unowned_openapi_paths)}"
        )
