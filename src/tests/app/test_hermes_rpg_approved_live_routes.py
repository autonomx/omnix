from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from app import create_fastapi_app
from app.assist_core.hermes_rpg_approved_config import FEATURE_FLAG
from app.assist_core import hermes_rpg_approved_routes as approved_routes
from app.assist_core.hermes_rpg_execution_ledger import hermes_rpg_execution_ledger_reset
from app.rpg.pipeline import create_new_game, delete_game, load_game, save_game


def test_hermes_rpg_approved_flow_live_config_route_defaults_off(monkeypatch: Any) -> None:
    monkeypatch.delenv(FEATURE_FLAG, raising=False)
    client = TestClient(create_fastapi_app())

    response = client.get("/api/hermes/rpg/approved-flow/config")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["feature_flag"] == FEATURE_FLAG
    assert payload["enabled"] is False
    assert payload["default_enabled"] is False
    assert payload["simulation_owned"] is True


def test_hermes_rpg_approved_flow_live_post_is_disabled_by_default(monkeypatch: Any) -> None:
    monkeypatch.delenv(FEATURE_FLAG, raising=False)
    client = TestClient(create_fastapi_app())

    response = client.post(
        "/api/hermes/rpg/approved-flow",
        json={
            "enabled": True,
            "user_step": {"ready": True, "command_text": "look around"},
            "replay_entry": {"ok": True, "command_text": "look around"},
            "context": {"session_id": "session-211", "context_hash": "ctx-211"},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is False
    assert payload["error"] == "hermes_rpg_approved_flow_disabled"
    assert payload["enabled"] is False
    assert payload["config"]["enabled"] is False
    assert payload["state_changed"] is False


def test_hermes_rpg_approved_flow_live_post_uses_canonical_submitter_when_enabled(monkeypatch: Any) -> None:
    hermes_rpg_execution_ledger_reset()
    submitted: list[dict[str, Any]] = []

    def submitter(payload: dict[str, Any]) -> dict[str, Any]:
        submitted.append(payload)
        return {
            "ok": True,
            "success": True,
            "source": "fake_live_rpg_submitter",
            "session_id": payload["session_id"],
            "command_text": payload["command_text"],
            "turn": 211,
            "narration": "You look around from the live route smoke test.",
            "events": [],
            "state_changed": True,
        }

    monkeypatch.setenv(FEATURE_FLAG, "1")
    monkeypatch.setattr(approved_routes, "hermes_rpg_canonical_submitter", submitter)
    client = TestClient(create_fastapi_app())

    response = client.post(
        "/api/hermes/rpg/approved-flow",
        json={
            "enabled": True,
            "user_step": {"ready": True, "command_text": "look around"},
            "replay_entry": {"ok": True, "command_text": "look around"},
            "context": {"session_id": "session-211", "context_hash": "ctx-211"},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert submitted == [
        {
            "ok": True,
            "source": "hermes_rpg_submit_adapter",
            "session_id": "session-211",
            "command_text": "look around",
            "input": "look around",
            "context_hash": "ctx-211",
            "canonical_path": "rpg_turn_execute",
            "state_changed": False,
        }
    ]
    assert payload["ok"] is True
    assert payload["config"]["enabled"] is True
    assert payload["readout"]["status"] == "accepted"
    assert payload["readout"]["session_id"] == "session-211"
    assert payload["readout"]["command_text"] == "look around"
    assert payload["flow"]["result"]["rpg_result"]["source"] == "fake_live_rpg_submitter"
    assert payload["ledger_entry"]["session_id"] == "session-211"
    assert payload["ledger_entry"]["command_text"] == "look around"
    assert payload["ledger_entry"]["state_changed"] is True
    assert payload["state_changed"] is True

    ledger = client.get("/api/hermes/rpg/approved-flow/ledger")
    assert ledger.status_code == 200
    ledger_payload = ledger.json()
    assert ledger_payload["count"] == 1
    assert ledger_payload["items"][0]["session_id"] == "session-211"


def test_hermes_rpg_approved_flow_live_post_advances_real_rpg_session(monkeypatch: Any) -> None:
    session_id = "session-212-real"
    delete_game(session_id)
    session = create_new_game(seed=212, player_name="Phase 212 Hero")
    starting_time = session.world.time
    save_game(session, session_id)
    monkeypatch.setenv(FEATURE_FLAG, "1")
    client = TestClient(create_fastapi_app())

    response = client.post(
        "/api/hermes/rpg/approved-flow",
        json={
            "enabled": True,
            "user_step": {"ready": True, "command_text": "look around"},
            "replay_entry": {"ok": True, "command_text": "look around"},
            "context": {"session_id": session_id, "context_hash": "ctx-212"},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    loaded = load_game(session_id)
    assert payload["ok"] is True
    assert payload["config"]["enabled"] is True
    assert payload["readout"]["status"] == "accepted"
    assert payload["readout"]["session_id"] == session_id
    assert payload["readout"]["command_text"] == "look around"
    assert payload["flow"]["result"]["rpg_result"]["source"] == "hermes_rpg_canonical_submitter"
    assert payload["flow"]["result"]["rpg_result"]["success"] is True
    assert payload["flow"]["result"]["rpg_result"]["narration"]
    assert payload["ledger_entry"]["session_id"] == session_id
    assert loaded is session
    assert loaded.world.time == starting_time + 1
    assert payload["state_changed"] is True
    delete_game(session_id)
