from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.gateway import rpg_session_routes


def _coverage_session(session_id: str) -> dict[str, object]:
    return {
        "manifest": {"id": session_id},
        "state": {
            "session_id": session_id,
            "ability_tree": {
                "abilities": [
                    {
                        "ability_id": "recon_read_room",
                        "kind": "active",
                        "name": "Read the Room",
                        "capability": "recon",
                        "purpose": "information_gathering",
                        "dimensions": ["information"],
                    }
                ]
            },
            "ability_state": {"unlocked": ["recon_read_room"]},
            "mechanics": {
                "ability_effect_trace": [
                    {
                        "ability_id": "recon_read_room",
                        "ability_name": "Read the Room",
                        "dimension": "information",
                        "op": "reveal_clue",
                        "applied": True,
                    }
                ]
            },
        },
    }


def test_clean_rpg_session_routes_expose_presets_and_new_game(monkeypatch) -> None:
    app = FastAPI(title="test")
    rpg_session_routes.register_rpg_session_routes(app)

    monkeypatch.setattr(
        rpg_session_routes,
        "list_rpg_presets",
        lambda: {"ok": True, "presets": [{"preset_id": "demo_glimmerdeep_pass_lvl14"}]},
    )
    monkeypatch.setattr(
        rpg_session_routes,
        "create_new_game_session",
        lambda request: {"ok": True, "session_id": "rpg_test", "status": "ready", "game": {"player": {"name": request.player.name}}},
    )

    client = TestClient(app)

    assert client.get("/api/rpg/presets").json() == {"ok": True, "presets": [{"preset_id": "demo_glimmerdeep_pass_lvl14"}]}
    assert client.post("/api/rpg/new-game", json={"player": {"name": "Test Hero"}}).json() == {
        "ok": True,
        "session_id": "rpg_test",
        "status": "ready",
        "game": {"player": {"name": "Test Hero"}},
    }


def test_clean_rpg_session_routes_expose_save_management(monkeypatch) -> None:
    app = FastAPI(title="test")
    rpg_session_routes.register_rpg_session_routes(app)

    monkeypatch.setattr(rpg_session_routes, "list_session_summaries", lambda **_kwargs: [{"manifest": {"id": "rpg_test"}}])
    monkeypatch.setattr(rpg_session_routes, "load_session", lambda session_id: _coverage_session(session_id))
    monkeypatch.setattr(rpg_session_routes, "continue_rpg_session", lambda session_id: {"ok": True, "session_id": session_id, "status": "ready"})
    monkeypatch.setattr(rpg_session_routes, "rename_rpg_session", lambda session_id, name: {"ok": True, "session_id": session_id, "session": {"manifest": {"title": name}}})
    monkeypatch.setattr(rpg_session_routes, "delete_rpg_session", lambda session_id: {"ok": True, "session_id": session_id, "archived": True})

    client = TestClient(app)

    assert client.get("/api/rpg/sessions").json() == {"ok": True, "sessions": [{"manifest": {"id": "rpg_test"}}]}
    read_payload = client.get("/api/rpg/sessions/rpg_test").json()
    assert read_payload["game"]["session_id"] == "rpg_test"
    assert read_payload["ability_coverage"]["covered_dimensions"] == ["information"]
    assert read_payload["game"]["mechanics"]["ability_coverage_latest"]["covered_dimensions"] == ["information"]
    assert client.post("/api/rpg/sessions/rpg_test/continue", json={}).json()["status"] == "ready"
    assert client.post("/api/rpg/sessions/rpg_test/rename", json={"name": "Renamed"}).json()["session"]["manifest"]["title"] == "Renamed"
    assert client.post("/api/rpg/sessions/rpg_test/delete", json={}).json() == {"ok": True, "session_id": "rpg_test", "archived": True}


def test_clean_rpg_session_routes_expose_ability_coverage_endpoint(monkeypatch) -> None:
    app = FastAPI(title="test")
    rpg_session_routes.register_rpg_session_routes(app)
    monkeypatch.setattr(rpg_session_routes, "load_session", lambda session_id: _coverage_session(session_id))

    payload = TestClient(app).get("/api/rpg/sessions/rpg_test/ability-coverage").json()

    assert payload["ok"] is True
    assert payload["session_id"] == "rpg_test"
    assert payload["ability_coverage"]["covered_dimensions"] == ["information"]
    assert payload["ability_coverage"]["missing_dimensions"] == [
        "resources",
        "relationships",
        "access",
        "environment",
        "position",
        "narrative",
        "economy",
        "world",
    ]


def test_clean_rpg_session_routes_convert_errors_to_http_status(monkeypatch) -> None:
    app = FastAPI(title="test")
    rpg_session_routes.register_rpg_session_routes(app)
    monkeypatch.setattr(rpg_session_routes, "start_rpg_preset", lambda preset_id: {"ok": False, "error": "unknown_rpg_preset", "preset_id": preset_id})

    response = TestClient(app).post("/api/rpg/presets/missing/start", json={})

    assert response.status_code == 404
    assert response.json()["detail"] == {"ok": False, "error": "unknown_rpg_preset", "preset_id": "missing"}
