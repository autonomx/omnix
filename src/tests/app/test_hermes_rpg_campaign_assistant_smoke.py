from __future__ import annotations

from fastapi.testclient import TestClient

from app import create_fastapi_app
from app.assist_core import hermes_rpg_approved_routes
from app.assist_core.hermes_rpg_approved_config import FEATURE_FLAG
from app.assist_core.hermes_rpg_execution_ledger import hermes_rpg_execution_ledger_reset
from app.assist_core.hermes_sequence_approved_executor import hermes_rpg_sequence_execute_step_payload as execute_step_payload
from app.assist_core.hermes_sequence_state import build_hermes_sequence_state


def _campaign_session() -> dict:
    return {
        "id": "campaign-242",
        "state": {
            "location": {"name": "Rusty Flagon Tavern"},
            "player": {"stats": {"charisma": 12, "strength": 10}},
            "inventory": [{"id": "coin-pouch", "name": "Coin pouch"}],
            "party": [{"id": "bran", "name": "Bran"}],
            "active_quests": [{"id": "trail", "title": "Follow the bandit trail"}],
            "recent_events": [{"kind": "rumor", "text": "A guard mentioned quarry tracks."}],
            "known_npcs": [{"id": "elara", "name": "Elara"}],
        },
    }


def _sequence() -> dict:
    return {
        "sequence_id": "seq-campaign-242",
        "objective": "Review safe tavern clues before acting",
        "domain": "rpg",
        "state_owner": "rpg_sim",
        "risk": "low",
        "items": [
            {"item_id": "look", "statement": "inspect tavern clues", "user_gate": False},
            {"item_id": "listen", "statement": "observe guard rumors", "user_gate": False},
        ],
    }


def test_hermes_rpg_campaign_assistant_smoke_routes(monkeypatch) -> None:
    hermes_rpg_execution_ledger_reset()
    client = TestClient(create_fastapi_app())
    states: dict[str, dict] = {}

    def fake_save(*, session_id: str, review_payload: dict) -> dict:
        state = build_hermes_sequence_state(session_id=session_id, review_payload=review_payload)
        states[session_id] = state
        return state

    def fake_latest(*, session_id: str) -> dict:
        state = states.get(session_id)
        return {"ok": bool(state), "source": "test", "state": state, "error": None if state else "sequence_state_not_found"}

    def fake_execute(payload: dict | None) -> dict:
        def submitter(command_payload: dict) -> dict:
            return {
                "ok": True,
                "turn": 42,
                "narration": f"Campaign advanced with {command_payload['command_text']}",
                "state_changed": True,
            }

        def write_state(updated: dict) -> dict:
            states[updated["session_id"]] = updated
            return updated

        return execute_step_payload(
            payload,
            submitter=submitter,
            environ={FEATURE_FLAG: "1"},
            state_loader=fake_latest,
            state_writer=write_state,
        )

    monkeypatch.setattr(hermes_rpg_approved_routes, "save_hermes_sequence_state", fake_save)
    monkeypatch.setattr(hermes_rpg_approved_routes, "latest_hermes_sequence_state", fake_latest)
    monkeypatch.setattr(hermes_rpg_approved_routes, "hermes_rpg_sequence_execute_step_payload", fake_execute)

    context_response = client.post("/api/hermes/rpg/context-pack", json={"session": _campaign_session()})
    assert context_response.status_code == 200
    context_pack = context_response.json()
    assert context_pack["ok"] is True
    assert context_pack["session_id"] == "campaign-242"
    assert context_pack["current_location"] == "Rusty Flagon Tavern"

    plan_response = client.post(
        "/api/hermes/rpg/sequence/plan",
        json={"sequence": _sequence(), "context_pack": context_pack},
    )
    assert plan_response.status_code == 200
    planned = plan_response.json()
    assert planned["ok"] is True
    assert planned["critique_summary"]["blocked"] is False

    review_response = client.post(
        "/api/hermes/rpg/sequence/review",
        json={**planned["sequence"], "session_id": "campaign-242", "assist_mode": "auto_low_risk"},
    )
    assert review_response.status_code == 200
    review = review_response.json()
    assert review["ok"] is True
    assert review["sequence_state"]["session_id"] == "campaign-242"
    assert review["sequence_state"]["current_item_index"] == 0

    state_response = client.get("/api/hermes/rpg/sequence/state?session_id=campaign-242")
    assert state_response.status_code == 200
    assert state_response.json()["state"]["sequence_id"] == "seq-campaign-242"

    execute_response = client.post(
        "/api/hermes/rpg/sequence/execute-step",
        json={"session_id": "campaign-242", "assist_mode": "auto_low_risk"},
    )
    assert execute_response.status_code == 200
    executed = execute_response.json()
    assert executed["ok"] is True
    assert executed["status"] == "accepted"
    assert executed["rpg_turn_result"]["turn"] == 42
    assert executed["sequence_state"]["current_item_index"] == 1
    assert executed["next_item_preview"]["item_id"] == "listen"

    ledger_response = client.get(
        "/api/hermes/rpg/approved-flow/ledger?session_id=campaign-242&sequence_id=seq-campaign-242"
    )
    assert ledger_response.status_code == 200
    ledger = ledger_response.json()
    assert ledger["count"] == 1
    assert ledger["items"][0]["command_text"] == "inspect tavern clues"
    assert ledger["items"][0]["state_changed"] is True
