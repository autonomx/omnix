from __future__ import annotations

from fastapi.testclient import TestClient

from app import create_fastapi_app
from app.assist_core import hermes_rpg_approved_routes
from app.assist_core.hermes_sequence_state import latest_hermes_sequence_state, save_hermes_sequence_state


def reviewed_payload(*, ok: bool = True, statement: str = "look around", allowed: bool = True) -> dict:
    return {
        "ok": ok and allowed,
        "validation": {
            "ok": ok,
            "errors": [] if ok else ["missing_items"],
            "sequence": {},
        },
        "sequence": {
            "sequence_id": "seq-1",
            "objective": "Review room",
            "domain": "rpg",
            "state_owner": "rpg_sim",
            "items": [{"item_id": "look", "statement": statement, "status": "pending"}] if statement else [],
        },
        "gate": {
            "allowed": allowed,
            "blocked_count": 0 if allowed else 1,
            "decisions": [{"item_id": "look", "allowed": allowed, "reason": None if allowed else "stateful_statement"}],
        }
        if ok
        else None,
    }


def test_sequence_state_save_and_resume_latest(tmp_path) -> None:
    path = tmp_path / "sequences.json"
    state = save_hermes_sequence_state(session_id="session-1", review_payload=reviewed_payload(), path=path)

    latest = latest_hermes_sequence_state(session_id="session-1", path=path)

    assert state["sequence_id"] == "seq-1"
    assert latest["ok"] is True
    assert latest["state"]["current_item_index"] == 0
    assert latest["state"]["item_statuses"] == [
        {"item_index": 0, "item_id": "look", "status": "pending", "command_text": "look around"}
    ]
    assert latest["state"]["created_at"]
    assert latest["state"]["updated_at"]


def test_sequence_state_records_blocked_state(tmp_path) -> None:
    state = save_hermes_sequence_state(
        session_id="session-1",
        review_payload=reviewed_payload(statement="buy rope", allowed=False),
        path=tmp_path / "sequences.json",
    )

    assert state["ok"] is False
    assert state["status"] == "blocked"
    assert state["blocked_reason"] == "stateful_statement"


def test_sequence_state_records_completed_index(tmp_path) -> None:
    payload = reviewed_payload()
    payload["sequence"]["items"][0]["status"] = "done"

    state = save_hermes_sequence_state(session_id="session-1", review_payload=payload, path=tmp_path / "sequences.json")

    assert state["current_item_index"] == 1
    assert state["item_statuses"][0]["status"] == "done"


def test_sequence_state_records_invalid_state(tmp_path) -> None:
    state = save_hermes_sequence_state(
        session_id="session-1",
        review_payload=reviewed_payload(ok=False, statement=""),
        path=tmp_path / "sequences.json",
    )

    assert state["ok"] is False
    assert state["status"] == "invalid"
    assert state["blocked_reason"] == "missing_items"


def test_sequence_latest_route_fetches_session_state(monkeypatch) -> None:
    def fake_latest(*, session_id: str):
        return {"ok": True, "source": "test", "state": {"session_id": session_id, "sequence_id": "seq-1"}}

    monkeypatch.setattr(hermes_rpg_approved_routes, "latest_hermes_sequence_state", fake_latest)

    response = TestClient(create_fastapi_app()).get("/api/hermes/rpg/sequence/state?session_id=session-1")

    assert response.status_code == 200
    assert response.json()["state"] == {"session_id": "session-1", "sequence_id": "seq-1"}
