from __future__ import annotations

from typing import Any

import pytest

from app.platform import rpg_session_compat
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


@pytest.mark.parametrize(
    ("identity_request", "expected_identity"),
    [
        (
            {
                "genre": "classic_fantasy",
                "tone": "scholarly high fantasy",
                "player": new_game.RpgPlayerOptions(name="Ilyra", background="academy exile", build="balanced_adventurer"),
                "primary_capability": "knowledge",
                "secondary_capabilities": ["recon", "support"],
                "power_source": "magic",
            },
            {
                "genre": "classic_fantasy",
                "tone": "scholarly high fantasy",
                "background": "academy exile",
                "primary_capability": "knowledge",
                "secondary_capabilities": ["recon", "support"],
                "power_source": "magic",
                "generated_class_name": "Runebinder",
            },
        ),
        (
            {
                "genre": "cyberpunk",
                "tone": "street-level neon noir",
                "player": new_game.RpgPlayerOptions(name="Nyx", background="corporate defector", build="balanced_adventurer"),
                "primary_capability": "technical",
                "secondary_capabilities": ["knowledge", "recon"],
                "power_source": "technology",
            },
            {
                "genre": "cyberpunk",
                "tone": "street-level neon noir",
                "background": "corporate defector",
                "primary_capability": "technical",
                "secondary_capabilities": ["knowledge", "recon"],
                "power_source": "technology",
                "generated_class_name": "Netrunner",
            },
        ),
        (
            {
                "genre": "detective_noir",
                "tone": "rain-soaked procedural",
                "player": new_game.RpgPlayerOptions(name="Mara Voss", background="former detective", build="silver_tongue"),
                "primary_capability": "recon",
                "secondary_capabilities": ["knowledge", "influence"],
                "power_source": "mundane",
            },
            {
                "genre": "detective_noir",
                "tone": "rain-soaked procedural",
                "background": "former detective",
                "primary_capability": "recon",
                "secondary_capabilities": ["knowledge", "influence"],
                "power_source": "mundane",
                "generated_class_name": "Private Eye",
            },
        ),
        (
            {
                "genre": "political_intrigue",
                "tone": "courtroom pressure",
                "player": new_game.RpgPlayerOptions(name="Sera", background="disgraced envoy", build="silver_tongue"),
                "primary_capability": "influence",
                "secondary_capabilities": ["knowledge", "recon"],
                "power_source": "social_power",
            },
            {
                "genre": "political_intrigue",
                "tone": "courtroom pressure",
                "background": "disgraced envoy",
                "primary_capability": "influence",
                "secondary_capabilities": ["knowledge", "recon"],
                "power_source": "social_power",
                "generated_class_name": "Court Schemer",
            },
        ),
    ],
)
def test_create_new_game_session_persists_capability_identity(monkeypatch, identity_request, expected_identity) -> None:
    captured = _capture_saved_session(monkeypatch)

    result = new_game.create_new_game_session(new_game.RpgNewGameRequest(seed=24680, **identity_request))

    assert result["ok"] is True
    session = captured["session"]
    state = session["state"]
    setup_payload = session["setup_payload"]
    identity = state["character_identity"]
    for key, value in expected_identity.items():
        assert identity[key] == value
        assert setup_payload[key] == value
    assert setup_payload["player"]["background"] == expected_identity["background"]
    assert state["metadata"]["primary_capability"] == expected_identity["primary_capability"]
    assert state["metadata"]["power_source"] == expected_identity["power_source"]
    assert state["player"]["class"] == expected_identity["generated_class_name"]
    assert state["ability_tree"]["genre"] == expected_identity["genre"]
    assert state["ability_tree"]["primary_capability"] == expected_identity["primary_capability"]


def test_continue_rpg_session_returns_saved_identity_without_regeneration(monkeypatch) -> None:
    identity = {
        "genre": "cyberpunk",
        "tone": "street-level neon noir",
        "background": "corporate defector",
        "primary_capability": "technical",
        "secondary_capabilities": ["knowledge", "recon"],
        "power_source": "technology",
        "generated_class_name": "Ghostwalker",
        "generated_class_summary": "A saved covert systems intruder.",
    }
    saved_session = {
        "manifest": {"id": "rpg_saved", "session_id": "rpg_saved"},
        "state": {"character_identity": dict(identity)},
        "setup_payload": dict(identity),
    }
    monkeypatch.setattr(new_game, "load_session", lambda session_id: saved_session)

    result = new_game.continue_rpg_session("rpg_saved")

    assert result["ok"] is True
    assert result["game"]["character_identity"] == identity
    assert result["session"]["setup_payload"] == identity


def test_create_new_game_session_uses_selected_starting_location(monkeypatch) -> None:
    captured = _capture_saved_session(monkeypatch)

    result = new_game.create_new_game_session(
        new_game.RpgNewGameRequest(seed=67890, starting_location="old_quarry")
    )

    assert result["ok"] is True
    state = captured["session"]["state"]
    assert state["current_location"] == "Old Quarry"
    assert state["world"]["time"] == "Day 1 • 16:20"
    assert "Inspect the fissure" in state["quick_actions"]
    assert state["timeline"][1]["kind"] == "mystery"


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


def test_rename_rpg_session_updates_manifest_title(monkeypatch) -> None:
    saved_sessions: list[dict[str, Any]] = []

    monkeypatch.setattr(
        new_game,
        "load_session",
        lambda session_id: {"manifest": {"id": session_id, "session_id": session_id, "title": "Old Name"}, "state": {}},
    )

    def fake_save_session(session: dict[str, Any], *, compact: bool = False) -> dict[str, Any]:
        saved_sessions.append(session)
        return session

    monkeypatch.setattr(new_game, "save_session", fake_save_session)

    result = new_game.rename_rpg_session("rpg_test", "New Name")

    assert result["ok"] is True
    assert result["session_id"] == "rpg_test"
    assert saved_sessions[0]["manifest"]["title"] == "New Name"
    assert "updated_at" in saved_sessions[0]["manifest"]


def test_delete_rpg_session_archives_session(monkeypatch) -> None:
    monkeypatch.setattr(new_game, "archive_session", lambda session_id: {"ok": True, "session_id": session_id, "archived": True})

    assert new_game.delete_rpg_session("rpg_test") == {"ok": True, "session_id": "rpg_test", "archived": True}


def test_session_compat_supports_rename_and_delete(monkeypatch) -> None:
    monkeypatch.setattr(new_game, "rename_rpg_session", lambda session_id, name: {"ok": True, "session_id": session_id, "name": name})
    monkeypatch.setattr(new_game, "delete_rpg_session", lambda session_id: {"ok": True, "session_id": session_id, "archived": True})

    assert rpg_session_compat.get_rpg_session_payload({"action": "rename", "session_id": "rpg_test", "name": "Renamed"}) == {
        "ok": True,
        "session_id": "rpg_test",
        "name": "Renamed",
    }
    assert rpg_session_compat.get_rpg_session_payload({"action": "delete", "session_id": "rpg_test"}) == {
        "ok": True,
        "session_id": "rpg_test",
        "archived": True,
    }
