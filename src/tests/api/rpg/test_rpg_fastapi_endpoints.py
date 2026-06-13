"""Smoke and contract tests for RPG FastAPI endpoints.

These tests intentionally avoid starting uvicorn or external LLM/image/TTS
services. They import the real FastAPI app, inspect the mounted route table, and
exercise safe endpoints with missing or fake session ids.
"""

from __future__ import annotations

import sys
from collections import Counter
from functools import lru_cache
from pathlib import Path

import pytest
from starlette.testclient import TestClient


SRC_DIR = Path(__file__).resolve().parents[3]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


@lru_cache(maxsize=1)
def _app():
    import run_app

    return run_app.app


def _client() -> TestClient:
    return TestClient(_app(), raise_server_exceptions=False)


def _route_pairs() -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for route in _app().routes:
        path = getattr(route, "path", "")
        methods = getattr(route, "methods", set()) or set()
        for method in methods:
            pairs.add((str(method).upper(), path))
    return pairs


REQUIRED_RPG_ROUTES = {
    # Legacy game-management API.
    ("GET", "/api/rpg/games"),
    ("POST", "/api/rpg/games"),
    ("POST", "/api/rpg/games/stream"),
    ("GET", "/api/rpg/games/{session_id}"),
    ("DELETE", "/api/rpg/games/{session_id}"),
    ("POST", "/api/rpg/games/{session_id}/turn"),
    ("POST", "/api/rpg/games/{session_id}/turn/stream"),
    ("GET", "/api/rpg/games/{session_id}/player"),
    ("GET", "/api/rpg/games/{session_id}/world"),
    ("GET", "/api/rpg/games/{session_id}/npcs"),
    ("GET", "/api/rpg/games/{session_id}/quests"),
    ("GET", "/api/rpg/games/{session_id}/history"),
    ("GET", "/api/rpg/games/{session_id}/replay"),
    ("POST", "/api/rpg/games/{session_id}/replay"),
    # Runtime session API used by the live RPG UI.
    ("POST", "/api/rpg/session/get"),
    ("POST", "/api/rpg/session/list"),
    ("POST", "/api/rpg/session/update"),
    ("POST", "/api/rpg/session/settings"),
    ("POST", "/api/rpg/session/delete"),
    ("POST", "/api/rpg/session/menu_action"),
    ("POST", "/api/rpg/session/idle_tick"),
    ("POST", "/api/rpg/session/world_events"),
    ("POST", "/api/rpg/session/world_behavior"),
    ("POST", "/api/rpg/session/world_behavior/update"),
}

SAFE_SESSION_CONTRACTS = [
    (
        "/api/rpg/session/world_events",
        {"session_id": "__missing__"},
        {
            "ok",
            "error",
            "recent_world_event_rows",
            "player_world_view_rows",
            "player_local_world_view_rows",
            "player_global_world_view_rows",
            "debug_world_events",
        },
    ),
    (
        "/api/rpg/session/idle_tick",
        {"session_id": "__missing__", "count": 1, "reason": "heartbeat"},
        {
            "ok",
            "error",
            "updates",
            "latest_seq",
            "ticks_applied",
            "idle_debug_trace",
            "idle_seconds",
            "idle_gate_open",
            "settings",
        },
    ),
    (
        "/api/rpg/session/get",
        {"session_id": "__missing__"},
        {"ok", "error", "session_id"},
    ),
]


@pytest.mark.api
def test_required_rpg_fastapi_routes_are_registered():
    """The launcher app must mount every core RPG route used by the UI."""
    missing = sorted(REQUIRED_RPG_ROUTES - _route_pairs())
    assert not missing, "Missing RPG FastAPI routes: " + ", ".join(
        f"{method} {path}" for method, path in missing
    )


@pytest.mark.api
def test_rpg_fastapi_routes_do_not_duplicate_required_ui_endpoints():
    """Critical live UI endpoints must not be mounted twice with the same method."""
    critical_pairs = {
        ("POST", "/api/rpg/session/world_events"),
        ("POST", "/api/rpg/session/idle_tick"),
        ("POST", "/api/rpg/session/get"),
    }
    counts: Counter[tuple[str, str]] = Counter()
    for route in _app().routes:
        path = getattr(route, "path", "")
        methods = getattr(route, "methods", set()) or set()
        for method in methods:
            pair = (str(method).upper(), path)
            if pair in critical_pairs:
                counts[pair] += 1

    duplicates = sorted(pair for pair, count in counts.items() if count > 1)
    assert not duplicates, "Duplicate critical RPG routes: " + ", ".join(
        f"{method} {path}" for method, path in duplicates
    )


@pytest.mark.api
@pytest.mark.parametrize(("path", "body", "expected_keys"), SAFE_SESSION_CONTRACTS)
def test_safe_rpg_session_endpoints_return_json_contracts(path, body, expected_keys):
    """Safe session endpoints should return JSON contracts, not route 404s."""
    response = _client().post(path, json=body)

    assert response.status_code == 200
    assert "application/json" in response.headers.get("content-type", "")
    payload = response.json()
    assert expected_keys.issubset(payload.keys())


@pytest.mark.api
def test_rpg_session_list_route_is_registered_but_not_called_in_smoke_suite():
    """Session-list can scan disk state; route-table coverage is enough here."""
    assert ("POST", "/api/rpg/session/list") in _route_pairs()


@pytest.mark.api
@pytest.mark.parametrize(
    "path",
    [
        "/api/rpg/session/world_events",
        "/api/rpg/session/idle_tick",
    ],
)
def test_live_polling_endpoints_reject_missing_session_id_with_400(path):
    """Polling endpoints should distinguish malformed requests from missing sessions."""
    response = _client().post(path, json={})

    assert response.status_code == 400
    assert response.json()["error"] == "session_id_required"


@pytest.mark.api
def test_idle_tick_returns_safe_contract_when_runtime_tick_raises(monkeypatch):
    """Idle polling must not surface runtime tick exceptions as HTTP 500s."""
    from app.rpg.api import rpg_session_management_routes as routes

    def fake_load_runtime_session(session_id):
        return {
            "session_id": session_id,
            "runtime_state": {},
            "simulation_state": {},
        }

    def fake_capture(session):
        return session

    class BrokenRuntime:
        @staticmethod
        def apply_idle_ticks(session_id, count, reason="heartbeat"):
            raise RuntimeError("boom")

    monkeypatch.setattr(routes, "load_runtime_session", fake_load_runtime_session)
    monkeypatch.setattr(routes, "save_runtime_session", lambda session: session)
    monkeypatch.setattr(routes, "capture_semantic_state_change_proposals_for_session", fake_capture)
    monkeypatch.setitem(sys.modules, "app.rpg.session.runtime", BrokenRuntime)

    response = _client().post(
        "/api/rpg/session/idle_tick",
        json={"session_id": "runtime-error", "count": 1, "reason": "heartbeat"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is False
    assert payload["error"] == "idle_tick_failed"
    assert payload["updates"] == []


@pytest.mark.api
@pytest.mark.parametrize(
    ("method", "path", "expected_status", "expected_error"),
    [
        ("GET", "/api/rpg/games/__missing__", 404, "Game not found"),
        ("GET", "/api/rpg/games/__missing__/player", 404, "Game not found"),
        ("GET", "/api/rpg/games/__missing__/world", 404, "Game not found"),
        ("GET", "/api/rpg/games/__missing__/npcs", 404, "Game not found"),
        ("GET", "/api/rpg/games/__missing__/quests", 404, "Game not found"),
        ("GET", "/api/rpg/games/__missing__/history", 404, "Game not found"),
        ("GET", "/api/rpg/games/__missing__/replay", 410, "replay_disabled"),
    ],
)
def test_legacy_game_query_endpoints_return_expected_missing_state(method, path, expected_status, expected_error):
    """Legacy RPG game query endpoints should fail with stable JSON responses."""
    response = _client().request(method, path)

    assert response.status_code == expected_status
    payload = response.json()
    assert payload["success"] is False
    assert payload["error"] == expected_error
