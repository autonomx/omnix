from __future__ import annotations

from app.rpg.session import new_game_creation_progress as progress
from app.rpg.session.new_game import RpgNewGameRequest


EXPECTED_STAGE_IDS = [
    "validate_setup",
    "resolve_seed",
    "create_player",
    "apply_stats",
    "assign_gear",
    "prepare_location",
    "seed_npcs_services",
    "create_opening_hook",
    "save_session",
    "prepare_first_turn",
]


def test_creation_progress_stages_match_wizard_modal_contract() -> None:
    snapshot = progress.build_creation_progress_snapshot(session_id="rpg_test", status="completed")

    assert snapshot["contract_version"] == progress.NEW_GAME_CREATION_JOB_CONTRACT
    assert snapshot["job_id"] == "rpg-create:rpg_test"
    assert snapshot["status"] == "completed"
    assert snapshot["progress"] == 100
    assert snapshot["stage"] == "prepare_first_turn"
    assert [stage["id"] for stage in snapshot["stages"]] == EXPECTED_STAGE_IDS
    assert [stage["status"] for stage in snapshot["stages"]] == ["done"] * len(EXPECTED_STAGE_IDS)


def test_creation_progress_failure_state_is_deterministic() -> None:
    first = progress.build_creation_progress_snapshot(session_id="rpg_test", status="failed", error="boom")
    second = progress.build_creation_progress_snapshot(session_id="rpg_test", status="failed", error="boom")

    assert first == second
    assert first["status"] == "failed"
    assert first["progress"] == 68
    assert first["error"] == "boom"
    assert first["stages"][first["current_stage_index"]]["status"] == "failed"
    assert first["stages"][-1]["status"] == "pending"


def test_create_new_game_session_with_progress_wraps_success(monkeypatch) -> None:
    def fake_create_new_game_session(request: RpgNewGameRequest) -> dict:
        assert request.seed == 42
        return {
            "ok": True,
            "session_id": "rpg_test",
            "status": "ready",
            "session": {"runtime_state": {}, "state": {"session_id": "rpg_test"}},
            "game": {"session_id": "rpg_test"},
        }

    monkeypatch.setattr(progress, "create_new_game_session", fake_create_new_game_session)
    monkeypatch.setattr(progress, "_persist_creation_job", lambda session_id, job, progress_snapshot: None)

    result = progress.create_new_game_session_with_progress(RpgNewGameRequest(seed=42))

    assert result["ok"] is True
    assert result["session_id"] == "rpg_test"
    assert result["creation_job"]["job_id"] == "rpg-create:rpg_test"
    assert result["creation_job"]["status"] == "completed"
    assert result["creation_progress"]["progress"] == 100
    assert result["creation_progress"]["stage"] == "prepare_first_turn"


def test_create_new_game_session_with_progress_wraps_failure(monkeypatch) -> None:
    def fake_create_new_game_session(request: RpgNewGameRequest) -> dict:
        assert request.seed == 13
        return {"ok": False, "error": "bad_setup"}

    monkeypatch.setattr(progress, "create_new_game_session", fake_create_new_game_session)

    result = progress.create_new_game_session_with_progress(RpgNewGameRequest(seed=13))

    assert result["ok"] is False
    assert result["error"] == "bad_setup"
    assert result["creation_job"]["status"] == "failed"
    assert result["creation_progress"]["status"] == "failed"
    assert result["creation_progress"]["progress"] == 68
