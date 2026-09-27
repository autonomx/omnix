from __future__ import annotations

from fastapi.routing import APIWebSocketRoute

from app.gateway.main import create_gateway_app
from app.runtime.config import RuntimeConfig
from app.runtime.feature_catalog import FEATURE_CATALOG, enabled_feature_ids, load_feature


def _paths(app) -> set[str]:
    return set(app.openapi()["paths"])


def _websocket_paths(app) -> set[str]:
    return {
        route.path
        for route in app.router.routes
        if isinstance(route, APIWebSocketRoute)
    }


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


def test_unknown_feature_configuration_fails_closed() -> None:
    config = RuntimeConfig(enabled_features=("audiobook", "missing-feature"))
    try:
        enabled_feature_ids(config)
    except ValueError as exc:
        assert "missing-feature" in str(exc)
    else:
        raise AssertionError("unknown feature id must fail startup")
