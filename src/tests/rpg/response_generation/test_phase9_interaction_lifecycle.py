from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.rpg.session.interaction_lifecycle import (
    apply_narration_result_to_interaction,
    initialize_interaction_lifecycle,
)


def _session() -> dict[str, Any]:
    return {
        "manifest": {"session_id": "session:bran"},
        "simulation_state": {"tick": 4, "gold": 10},
        "runtime_state": {
            "interaction_seq": 1,
            "state_revision": 1,
            "interaction_timeline": {
                "events": [
                    {
                        "interaction_id": "interaction:1",
                        "sequence": 1,
                        "turn_id": "turn:4",
                        "player_input": "I buy two rations.",
                    }
                ]
            },
        },
    }


def _stateful_result() -> dict[str, Any]:
    return {
        "ok": True,
        "interaction_id": "interaction:1",
        "submission_id": "submit:one",
        "turn_id": "turn:4",
        "tick": 4,
        "stateful": True,
        "action_type": "trade",
        "outcome": "purchase_completed",
        "narration": "You pay for two rations.",
        "narration_request": {
            "turn_id": "turn:4",
            "tick": 4,
            "narration_context": {"resolved_result": {"outcome": "purchase_completed"}},
        },
    }


def test_stateful_turn_enters_narration_pending_without_changing_simulation_state() -> None:
    session = _session()
    before_simulation = deepcopy(session["simulation_state"])
    result = _stateful_result()

    lifecycle = initialize_interaction_lifecycle(session, result)

    assert lifecycle["status"] == "narration_pending"
    assert lifecycle["narration_status"] == "queued"
    assert result["narration_request"]["interaction_id"] == "interaction:1"
    assert session["runtime_state"]["interaction_id_by_turn"]["turn:4"] == "interaction:1"
    assert session["simulation_state"] == before_simulation
    event = session["runtime_state"]["interaction_timeline"]["events"][0]
    assert event["lifecycle"]["status"] == "narration_pending"


def test_nonstateful_turn_stops_at_runtime_resolved() -> None:
    session = _session()
    result = {
        "ok": True,
        "interaction_id": "interaction:1",
        "turn_id": "turn:4",
        "tick": 4,
        "stateful": False,
        "action_type": "npc_interpretive_dialogue",
        "narration": "Bran answers plainly.",
    }

    lifecycle = initialize_interaction_lifecycle(session, result)

    assert lifecycle["status"] == "runtime_resolved"
    assert lifecycle["narration_status"] == "not_requested"
    assert result["narration_status"] == "not_requested"


def test_completed_narration_enriches_same_interaction_only(monkeypatch: Any) -> None:
    session = _session()
    result = _stateful_result()
    initialize_interaction_lifecycle(session, result)
    before_simulation = deepcopy(session["simulation_state"])
    saved: list[dict[str, Any]] = []

    monkeypatch.setattr(
        "app.rpg.session.runtime.load_runtime_session",
        lambda session_id: session,
    )
    monkeypatch.setattr(
        "app.rpg.session.runtime.save_runtime_session",
        lambda value: saved.append(deepcopy(value)) or value,
    )

    worker_result = apply_narration_result_to_interaction(
        "session:bran",
        {
            "ok": True,
            "status": "completed",
            "turn_id": "turn:4",
            "artifact": {
                "artifact_type": "rpg_turn_narration",
                "turn_id": "turn:4",
                "tick": 4,
                "narration": "Bran wraps the rations and slides them across the counter.",
                "used_llm": False,
            },
        },
    )

    assert worker_result["interaction_id"] == "interaction:1"
    assert worker_result["interaction_lifecycle"]["status"] == "narration_complete"
    assert session["simulation_state"] == before_simulation
    assert len(session["runtime_state"]["interaction_timeline"]["events"]) == 1
    event = session["runtime_state"]["interaction_timeline"]["events"][0]
    assert event["interaction_id"] == "interaction:1"
    assert "slides them across" in event["narration_enrichment"]["narration"]
    assert saved


def test_failed_narration_keeps_authoritative_response_and_marks_same_interaction(monkeypatch: Any) -> None:
    session = _session()
    result = _stateful_result()
    lifecycle = initialize_interaction_lifecycle(session, result)
    authoritative = deepcopy(lifecycle["authoritative_response"])

    monkeypatch.setattr("app.rpg.session.runtime.load_runtime_session", lambda session_id: session)
    monkeypatch.setattr("app.rpg.session.runtime.save_runtime_session", lambda value: value)

    failed = apply_narration_result_to_interaction(
        "session:bran",
        {
            "ok": False,
            "status": "failed",
            "turn_id": "turn:4",
            "error": "provider_unavailable",
        },
    )

    assert failed["interaction_id"] == "interaction:1"
    updated = failed["interaction_lifecycle"]
    assert updated["status"] == "narration_failed"
    assert updated["authoritative_response"] == authoritative
    assert updated["narration_error"] == "provider_unavailable"


def test_late_narration_for_superseded_turn_is_ignored(monkeypatch: Any) -> None:
    session = _session()
    result = _stateful_result()
    initialize_interaction_lifecycle(session, result)
    session["runtime_state"]["interaction_id_by_turn"]["turn:old"] = "interaction:1"

    monkeypatch.setattr("app.rpg.session.runtime.load_runtime_session", lambda session_id: session)
    monkeypatch.setattr("app.rpg.session.runtime.save_runtime_session", lambda value: value)

    late = apply_narration_result_to_interaction(
        "session:bran",
        {"ok": True, "status": "completed", "turn_id": "turn:old", "artifact": {"narration": "Late."}},
    )

    assert "interaction_lifecycle" not in late
    assert session["runtime_state"]["interaction_lifecycles"]["interaction:1"]["status"] == "narration_pending"
