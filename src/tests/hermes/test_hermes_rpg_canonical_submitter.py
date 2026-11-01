from __future__ import annotations

from app.apps.rpg.edge.hermes import canonical_submitter as submitter
from app.apps.rpg.session import service


def test_default_submitter_submits_the_turn_as_the_play_screen_does_and_reports_its_outcome(monkeypatch) -> None:
    """RQ-1.6: an approved Hermes command is a turn like the play screen's, keyed by its submission id and
    committed; Hermes reads its TurnOutcome."""
    from app.apps.rpg.edge.api import turn_pipeline

    before = {"manifest": {"session_id": "session-1"}, "simulation_state": {"player_state": {"id": "player-1"}}}
    after = {"manifest": {"session_id": "session-1"}, "simulation_state": {"player_state": {"id": "player-1", "hp": 9}}}
    loads = [before, after]
    monkeypatch.setattr(service, "load_session", lambda session_id: loads.pop(0) if session_id == "session-1" else None)
    calls: list[dict] = []

    def submit(**kwargs):
        calls.append(kwargs)
        return {
            "ok": True,
            "turn_id": "turn-2",
            "submission_id": kwargs["submission_id"],
            "visible_response": {"plain_text": "The door opens."},
            "state": {"changed": True},
            "outcome": {"turn_id": "turn-2", "applied_changes": [{"type": "turn_counted", "turn_count": 2}]},
        }

    monkeypatch.setattr(turn_pipeline, "submit_rpg_turn", submit)

    result = submitter.hermes_rpg_canonical_submitter(
        {"session_id": "session-1", "command_text": "open the door", "submission_id": "hermes-sub-1"}
    )

    assert calls == [{"session_id": "session-1", "command": "open the door", "submission_id": "hermes-sub-1",
                      "source": "hermes"}]
    assert result["ok"] is True and result["state_changed"] is True
    assert result["turn"] == "turn-2" and result["narration"] == "The door opens."
    assert result["state_changes"] == {"applied_changes": [{"type": "turn_counted", "turn_count": 2}]}
    assert result["outcome"]["turn_id"] == "turn-2" and result["submission_id"] == "hermes-sub-1"
    assert result["player"] == {"id": "player-1", "hp": 9}  # as the turn left the hero


def test_submitter_treats_an_explicit_failed_turn_as_failure() -> None:
    result = submitter.hermes_rpg_canonical_submitter(
        {"session_id": "session-1", "command_text": "wait"},
        loader=lambda _session_id: {"manifest": {"session_id": "session-1"}},
        executor=lambda _session, _command: {"ok": False},
    )

    assert result["ok"] is False
    assert result["error"] == "turn_failed"
    assert result["state_changed"] is False
