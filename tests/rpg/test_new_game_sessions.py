from __future__ import annotations

from typing import Any

from app.rpg.session import new_game


def _capture_saved_session(monkeypatch) -> dict[str, Any]:
    captured: dict[str, Any] = {}

    def fake_save_session(session: dict[str, Any], *, compact: bool = False) -> dict[str, Any]:
        captured["session"] = session
        captured["compact"] = compact
        return session

    monkeypatch.setattr(new_game, "save_session", fake_save_session)
    return captured


def test_create_new_game_session_builds_level_one_campaign(monkeypatch) -> None:
    captured = _capture_saved_session(monkeypatch)

    result = new_game.create_new_game_session(
        new_game.RpgNewGameRequest(
            seed=12345,
            player=new_game.RpgPlayerOptions(name="Test Hero", build="balanced_adventurer"),
        )
    )

    assert result["ok"] is True
    assert result["status"] == "ready"
    assert result["session_id"].startswith("rpg_")
    assert captured["compact"] is False

    session = captured["session"]
    state = session["state"]
    assert session["manifest"]["kind"] == "new_game"
    assert session["runtime_state"] == {"active_job_id": None, "last_error": None, "created_from": "new_game"}
    assert state["metadata"]["seed"] == 12345
    assert state["player"]["name"] == "Test Hero"
    assert state["player"]["level"] == 1
    assert state["player"]["currency"] == {"gold": 10, "silver": 25, "copper": 50}
    assert {item["id"] for item in state["player"]["inventory"]} >= {"ration", "torch", "iron_dagger", "simple_bow", "journal"}
    assert state["current_location"] == "Rusty Flagon Tavern"
    assert state["turn_count"] == 0


def test_list_rpg_presets_exposes_glimmerdeep_demo() -> None:
    presets = new_game.list_rpg_presets()

    assert presets["ok"] is True
    assert presets["presets"] == [
        {
            "preset_id": new_game.DEMO_PRESET_ID,
            "name": "Demo: Glimmerdeep Pass",
            "description": "Level 14 ranger party at Glimmerdeep Pass with quests, equipment, journal, relationships, and world state preloaded.",
            "kind": "in_progress_demo",
            "level": 14,
            "location": "Glimmerdeep Pass",
            "clone_on_start": True,
        }
    ]


def test_start_rpg_preset_clones_playable_demo_session(monkeypatch) -> None:
    captured = _capture_saved_session(monkeypatch)

    result = new_game.start_rpg_preset(new_game.DEMO_PRESET_ID)

    assert result["ok"] is True
    assert result["status"] == "ready"
    assert result["session_id"].startswith("rpg_demo_")

    session = captured["session"]
    state = session["state"]
    assert session["manifest"]["kind"] == "playable_demo_clone"
    assert session["manifest"]["created_from_preset"] == new_game.DEMO_PRESET_ID
    assert session["runtime_state"] == {"active_job_id": None, "last_error": None, "created_from": new_game.DEMO_PRESET_ID}
    assert state["metadata"]["created_from_preset"] == new_game.DEMO_PRESET_ID
    assert state["player"]["name"] == "Alyndra"
    assert state["player"]["level"] == 14
    assert state["current_location"] == "Glimmerdeep Pass"
    assert len(state["party"]) == 3
    assert {quest["id"] for quest in state["quests"]} == {"frostbound_relic", "secrets_in_snow", "icefang_alpha"}


def test_start_rpg_preset_rejects_unknown_id(monkeypatch) -> None:
    captured = _capture_saved_session(monkeypatch)

    result = new_game.start_rpg_preset("missing")

    assert result == {"ok": False, "error": "unknown_rpg_preset", "preset_id": "missing"}
    assert "session" not in captured
