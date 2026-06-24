from __future__ import annotations

from app.rpg.session import new_game_creation_progress as progress_module
from app.rpg.session.new_game import RpgNewGameRequest


def test_creation_progress_does_not_resave_completed_session(monkeypatch):
    session = {
        "manifest": {"session_id": "rpg_fast_create", "id": "rpg_fast_create"},
        "state": {"title": "Fast Create", "timeline": []},
        "runtime_state": {"created_from": "new_game"},
    }

    def fake_create_new_game_session(request: RpgNewGameRequest) -> dict:
        return {
            "ok": True,
            "session_id": "rpg_fast_create",
            "status": "ready",
            "session": dict(session),
            "game": session["state"],
        }

    def fail_if_resaved(*args, **kwargs):  # pragma: no cover - assertion helper
        raise AssertionError("completed creation progress should not trigger a second session save")

    monkeypatch.setattr(progress_module, "create_new_game_session", fake_create_new_game_session)
    monkeypatch.setattr(progress_module, "_persist_creation_job", fail_if_resaved)

    result = progress_module.create_new_game_session_with_progress(RpgNewGameRequest())

    assert result["ok"] is True
    assert result["creation_progress"]["progress"] == 100
    assert result["creation_progress"]["stage"] == "ready_first_turn"
    returned_session = result["session"]
    assert returned_session["runtime_state"]["creation_job"]["status"] == "completed"
    assert returned_session["manifest"]["creation_status"] == "completed"


def test_final_creation_stage_is_lightweight_first_turn_readiness():
    progress = progress_module.build_creation_progress_snapshot(session_id="rpg_fast_create", status="completed")

    assert progress["stage"] == "ready_first_turn"
    assert progress["stage_label"] == "Ready for first turn"
    assert "deferred until you act" in progress["stages"][-1]["detail"]
