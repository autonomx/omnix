from __future__ import annotations

from copy import deepcopy
import inspect
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = ROOT / ".github" / "workflows" / "rpg-pr-deterministic.yml"
HUD_RENDERER = ROOT / "src" / "static" / "rpg" / "rpgPlayerHud.js"
SETTINGS_BOOTSTRAP = ROOT / "src" / "static" / "rpg-conversation-settings.js"
SOURCE = "deterministic_phase8_player_visible_state_objective_hud_gate"
GATE_NAME = "RPG CI Phase 8 player visible state objective HUD gate"
GATE_COMMAND = "python -m pytest src/tests/rpg/test_ci_phase8_player_visible_state_objective_hud.py -q --tb=short"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_ci_phase8_player_hud_payload_is_provider_free_source_backed_and_non_mutating():
    from app.rpg.session import runtime_part27

    simulation_state = {
        "player_state": {
            "inventory_state": {
                "items": [
                    {"item_id": "ration", "name": "Ration", "qty": 2},
                    {"item_id": "water_skin", "name": "Water Skin", "qty": 1},
                ],
                "currency": {"gold": 1, "silver": 5, "copper": 7},
            },
            "survival_state": {"hunger": 81, "thirst": 12},
        },
        "travel_state": {"current_location_id": "location:rusty_flagon"},
        "journal_state": {"objectives": [{"id": "obj:bandits", "title": "Ask Bran about the bandits", "status": "active"}]},
        "party_state": {"members": [{"id": "npc:bran", "name": "Bran", "role": "companion"}]},
        "time_state": {"day_count": 1},
    }
    runtime_state = {"tick": 3, "last_turn_result": {"ok": False, "reason": "route_blocked"}}
    before_sim = deepcopy(simulation_state)
    before_runtime = deepcopy(runtime_state)

    hud = runtime_part27._phase8_player_visible_hud_payload(simulation_state, runtime_state)

    assert simulation_state == before_sim
    assert runtime_state == before_runtime
    assert hud["source"] == SOURCE
    assert hud["frontend_source"] == SOURCE
    assert hud["non_mutating"] is True
    assert hud["current_location_id"] == "location:rusty_flagon"
    assert hud["current_location"]["name"] == "The Rusty Flagon"
    assert hud["active_objective"]["title"] == "Ask Bran about the bandits"
    assert hud["player_resources"]["currency"] == {"gold": 1, "silver": 5, "copper": 7, "source": SOURCE}
    assert [item["item_id"] for item in hud["player_resources"]["items"]] == ["ration", "water_skin"]
    assert hud["party_summary"]["members"] == [
        {"id": "npc:bran", "name": "Bran", "role": "companion", "source": SOURCE}
    ]
    assert {warning["kind"] for warning in hud["major_warnings"]} == {"high_hunger", "last_action_failed"}
    assert hud["map_location_panel"]["frontend_source"] == "deterministic_phase4_frontend_map_location_ui_panel"

    helper_source = inspect.getsource(runtime_part27._phase8_player_visible_hud_payload)
    assert "provider" not in helper_source.lower()
    assert "llm" not in helper_source.lower()


def test_ci_phase8_player_hud_attaches_to_travel_turn_payload(monkeypatch):
    from app.rpg.locations import OLD_ROAD
    from app.rpg.session import runtime_part27

    saved = {}

    def save_runtime_session(payload):
        saved.clear()
        saved.update(deepcopy(payload))
        return payload

    monkeypatch.setattr(runtime_part27, "save_runtime_session", save_runtime_session)
    session_id = "ci_phase8_player_hud_travel"
    session = {
        "manifest": {"session_id": session_id, "id": session_id},
        "setup_payload": {},
        "runtime_state": {"tick": 4, "narration_mode": "deterministic"},
        "simulation_state": {
            "player_state": {
                "inventory_state": {
                    "items": [{"item_id": "ration", "qty": 1}, {"item_id": "water_skin", "qty": 2}],
                    "currency": {"silver": 3},
                },
                "survival_state": {"hunger": 10, "thirst": 10},
            },
            "travel_state": {"current_location_id": "location:rusty_flagon"},
            "journal_state": {"objectives": [{"title": "Reach the old road", "status": "active"}]},
        },
    }

    result = runtime_part27._apply_phase4_session_travel_command(
        session_id,
        "go to old road",
        session=session,
        simulation_state=session["simulation_state"],
        runtime_state=session["runtime_state"],
    )

    hud = result["player_hud"]
    assert result["ok"] is True
    assert hud["source"] == SOURCE
    assert hud["current_location_id"] == OLD_ROAD
    assert hud["active_objective"]["title"] == "Reach the old road"
    assert result["resolved_result"]["player_hud"] == hud
    assert result["narration_context"]["player_hud"] == hud
    assert saved["runtime_state"]["tick"] == 5


def test_ci_phase8_player_hud_browser_renderer_uses_safe_visible_payload():
    renderer = _read(HUD_RENDERER)
    settings = _read(SETTINGS_BOOTSTRAP)

    for expected in (
        "window.RpgPlayerHud",
        "hudPayloadFromTurnPayload",
        "firstNonEmptyObj",
        "escapeHtml",
        "rpgPlayerHudPanel",
        "current_location",
        "active_objective",
        "player_resources",
        "party_summary",
        "major_warnings",
        "rpg-player-hud-source",
    ):
        assert expected in renderer

    assert "Math.random" not in renderer
    assert "innerHTML" in renderer
    assert "escapeHtml" in renderer
    assert "/static/rpg/rpgPlayerHud.js" in settings
    assert "ensurePlayerHudScript" in settings


def test_ci_phase8_player_hud_renderer_escapes_state_values():
    renderer = _read(HUD_RENDERER)

    assert ".replace(/&/g, \"&amp;\")" in renderer
    assert ".replace(/</g, \"&lt;\")" in renderer
    assert ".replace(/>/g, \"&gt;\")" in renderer
    assert "${escapeHtml(locationName)}" in renderer
    assert "${escapeHtml(objectiveTitle)}" in renderer
    assert "${escapeHtml(source)}" in renderer


def test_ci_phase8_player_hud_workflow_gate_is_ordered_before_manifest():
    workflow = _read(WORKFLOW)

    assert GATE_NAME in workflow
    assert GATE_COMMAND in workflow
    previous_gate = "RPG CI Phase 7 closeout planning gate"
    next_gate = "RPG CI runtime facade manifest gate"
    assert workflow.index(previous_gate) < workflow.index(GATE_NAME) < workflow.index(next_gate)


def test_ci_phase8_player_hud_runtime_manifest_stays_authoritative():
    from app.rpg.session import runtime

    manifest = runtime.get_runtime_wrapper_manifest()

    assert manifest["final_apply_turn_authoritative_module"] == "app.rpg.session.runtime_part27"
    assert manifest["final_apply_attack_combat_action_module"] == "app.rpg.session.runtime_part23"
