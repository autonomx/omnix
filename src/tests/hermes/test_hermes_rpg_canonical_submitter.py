from __future__ import annotations

from app.apps.rpg.edge.hermes import canonical_submitter as submitter
from app.apps.rpg.session import interactive_first_call_runtime, service


def test_default_submitter_loads_and_runs_the_durable_turn_pipeline(monkeypatch) -> None:
    session = {
        "manifest": {"session_id": "session-1"},
        "simulation_state": {"player_state": {"id": "player-1"}},
    }
    calls: list[tuple[str, str, dict]] = []

    monkeypatch.setattr(service, "load_session", lambda session_id: session if session_id == "session-1" else None)

    def apply_turn(session_id, command, **kwargs):
        calls.append((session_id, command, kwargs))
        return {
            "ok": True,
            "turn_id": "turn-2",
            "narration": "The door opens.",
            "events": [{"kind": "door_opened"}],
            "state_changed": True,
        }

    monkeypatch.setattr(interactive_first_call_runtime, "apply_turn", apply_turn)

    result = submitter.hermes_rpg_canonical_submitter(
        {"session_id": "session-1", "command_text": "open the door"}
    )

    assert result["ok"] is True
    assert result["state_changed"] is True
    assert result["turn"] == "turn-2"
    assert result["narration"] == "The door opens."
    assert result["player"] == {"id": "player-1"}
    assert calls[0][0:2] == ("session-1", "open the door")
    assert calls[0][2]["session_override"] == session
    assert calls[0][2]["performance_override"]["narration_mode"] == "blocking"


def test_submitter_treats_an_explicit_failed_turn_as_failure() -> None:
    result = submitter.hermes_rpg_canonical_submitter(
        {"session_id": "session-1", "command_text": "wait"},
        loader=lambda _session_id: {"manifest": {"session_id": "session-1"}},
        executor=lambda _session, _command: {"ok": False},
    )

    assert result["ok"] is False
    assert result["error"] == "turn_failed"
    assert result["state_changed"] is False
