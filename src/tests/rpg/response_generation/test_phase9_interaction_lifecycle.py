from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.apps.rpg.session.interaction_lifecycle import (
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


def _pending(session: dict[str, Any]) -> dict[str, Any]:
    """A save from before WP-5.6: its interaction waits on a deferred narration."""
    lifecycle = session["runtime_state"]["interaction_lifecycles"]["interaction:1"]
    lifecycle.update(status="narration_pending", narration_status="queued")
    return session


def test_a_committed_interaction_is_resolved_and_queues_no_narration() -> None:
    session = _session()
    before_simulation = deepcopy(session["simulation_state"])
    result = _stateful_result()

    lifecycle = initialize_interaction_lifecycle(session, result)

    # The turn's narration is the narrative engine's: a narration request on the result queues nothing.
    assert lifecycle["status"] == "runtime_resolved"
    assert lifecycle["narration_status"] == "not_requested"
    assert session["runtime_state"]["interaction_id_by_turn"]["turn:4"] == "interaction:1"
    assert session["simulation_state"] == before_simulation
    event = session["runtime_state"]["interaction_timeline"]["events"][0]
    assert event["lifecycle"]["status"] == "runtime_resolved"


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


def test_version_10_retires_a_narration_pending_from_before_wp_5_6() -> None:
    from app.apps.rpg.session.upgrades.legacy_narration import retire_pending_narration

    session = _pending(_session_with_lifecycle())
    session["runtime_state"]["narration_jobs_by_turn"] = {"turn:4": {"narration_request": {"turn_id": "turn:4"}}}
    retired = retire_pending_narration(session)
    lifecycle = retired["runtime_state"]["interaction_lifecycles"]["interaction:1"]
    assert (lifecycle["status"], lifecycle["narration_status"]) == ("narration_retired", "retired")
    assert "narration_jobs_by_turn" not in retired["runtime_state"]


def _session_with_lifecycle() -> dict[str, Any]:
    session = _session()
    initialize_interaction_lifecycle(session, _stateful_result())
    return session
