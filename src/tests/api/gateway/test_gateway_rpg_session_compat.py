"""RPG session compatibility routes exposed through the gateway."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient


SRC_DIR = Path(__file__).resolve().parents[3]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


def _client() -> TestClient:
    from app.gateway.main import create_gateway_app

    return TestClient(create_gateway_app(), raise_server_exceptions=False)


def test_gateway_rpg_session_list_returns_legacy_envelope() -> None:
    with patch("app.rpg.session.service.list_sessions", return_value=[{"session_id": "rpg-1"}]):
        response = _client().post("/api/rpg/session/list")

    assert response.status_code == 200
    assert response.json() == {"ok": True, "sessions": [{"session_id": "rpg-1"}]}


def test_gateway_rpg_session_get_requires_session_id() -> None:
    response = _client().post("/api/rpg/session/get", json={})

    assert response.status_code == 200
    assert response.json() == {"ok": False, "error": "missing_session_id"}


def test_gateway_rpg_session_get_preserves_missing_session_contract() -> None:
    with patch("app.rpg.session.runtime.load_runtime_session", return_value=None):
        response = _client().post("/api/rpg/session/get", json={"session_id": "missing"})

    assert response.status_code == 200
    assert response.json() == {
        "ok": False,
        "error": "session_not_found",
        "session_id": "missing",
    }


def test_gateway_rpg_session_get_returns_bootstrap_payload() -> None:
    with (
        patch("app.rpg.session.runtime.load_runtime_session", return_value={"session_id": "rpg-1"}),
        patch(
            "app.rpg.session.runtime.build_frontend_bootstrap_payload",
            return_value={"session_id": "session:unknown", "title": "Example"},
        ),
    ):
        response = _client().post("/api/rpg/session/get", json={"session_id": "rpg-1"})

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "game": {"session_id": "rpg-1", "title": "Example"},
    }
