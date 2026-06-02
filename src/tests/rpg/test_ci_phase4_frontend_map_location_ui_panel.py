from copy import deepcopy
import inspect
from pathlib import Path


def _session_id(name: str) -> str:
    return f"ci_phase4_15_{name}"


def _base_session(session_id: str, *, items=None):
    return {
        "manifest": {"session_id": session_id, "id": session_id},
        "setup_payload": {},
        "runtime_state": {"tick": 4, "narration_mode": "deterministic"},
        "simulation_state": {
            "player_state": {
                "inventory_state": {"items": deepcopy(items if items is not None else [])},
                "survival_state": {"hunger": 10, "thirst": 10},
            },
            "travel_state": {"current_location_id": "location:rusty_flagon"},
        },
    }


def _install_save_capture(monkeypatch, runtime_part27):
    saved = {}

    def save_runtime_session(payload):
        saved.clear()
        saved.update(deepcopy(payload))
        return payload

    monkeypatch.setattr(runtime_part27, "save_runtime_session", save_runtime_session)
    return saved


def test_ci_phase4_frontend_map_location_payload_is_provider_free_and_non_mutating():
    from app.rpg.locations import OLD_MILL, RUSTY_FLAGON
    from app.rpg.session import runtime_part27

    state = {}
    before = deepcopy(state)

    panel = runtime_part27._phase4_frontend_map_location_panel_payload(state)

    assert state == before
    assert panel["source"] == "deterministic_phase4_map_location_report"
    assert panel["frontend_source"] == "deterministic_phase4_frontend_map_location_ui_panel"
    assert panel["current_location_id"] == RUSTY_FLAGON
    assert panel["current_location"]["name"] == "The Rusty Flagon"
    assert panel["visible_exits"]
    assert OLD_MILL not in {row["destination_id"] for row in panel["visible_exits"]}

    helper_source = inspect.getsource(runtime_part27._phase4_frontend_map_location_panel_payload)
    assert "provider" not in helper_source.lower()
    assert "llm" not in helper_source.lower()


def test_ci_phase4_frontend_map_location_payload_shows_visible_blocked_route_without_passable_claim():
    from app.rpg.locations import OLD_MILL, OLD_ROAD, RUSTY_FLAGON, apply_travel, discover_location, discover_route
    from app.rpg.session import runtime_part27

    state = {}
    discover_location(state, location_id=OLD_MILL, reason="scouted_old_road", turn_index=2)
    discover_route(state, edge_id="route:old_road:old_mill", reason="scouted_old_road", turn_index=2)
    travel = apply_travel(state, start_location_id=RUSTY_FLAGON, end_location_id=OLD_ROAD, turn_index=3)
    before = deepcopy(state)

    panel = runtime_part27._phase4_frontend_map_location_panel_payload(state)

    assert travel["ok"] is True
    assert state == before
    assert panel["current_location_id"] == OLD_ROAD
    assert panel["current_location"]["name"] == "Old Road"

    old_mill_exit = next(row for row in panel["visible_exits"] if row["destination_id"] == OLD_MILL)
    assert old_mill_exit["destination_name"] == "Old Mill"
    assert old_mill_exit["blocked"] is True
    assert old_mill_exit["block_reason"] == "bandit_threat_unresolved"
    assert "passable" not in repr(old_mill_exit).casefold()


def test_ci_phase4_frontend_map_location_turn_payload_surfaces_panel_for_ui(monkeypatch):
    from app.rpg.locations import OLD_ROAD
    from app.rpg.session import runtime_part27

    session_id = _session_id("turn_payload")
    session = _base_session(
        session_id,
        items=[{"item_id": "ration", "qty": 1}, {"item_id": "water_skin", "qty": 2}],
    )
    saved = _install_save_capture(monkeypatch, runtime_part27)

    result = runtime_part27._apply_phase4_session_travel_command(
        session_id,
        "go to old road",
        session=session,
        simulation_state=session["simulation_state"],
        runtime_state=session["runtime_state"],
    )

    panel = result["map_location_panel"]
    assert result["ok"] is True
    assert result["source"] == "deterministic_phase4_session_travel_command_integration"
    assert panel["frontend_source"] == "deterministic_phase4_frontend_map_location_ui_panel"
    assert panel["current_location_id"] == OLD_ROAD
    assert panel["current_location"]["name"] == "Old Road"
    assert result["resolved_result"]["map_location_panel"] == panel
    assert result["narration_context"]["map_location_panel"] == panel
    assert saved["simulation_state"]["travel_state"]["current_location_id"] == OLD_ROAD


def test_ci_phase4_frontend_map_location_browser_renderer_uses_safe_visible_payload():
    renderer = Path("src/static/rpg/rpgMapLocationPanel.js").read_text(encoding="utf-8")
    settings = Path("src/static/rpg-conversation-settings.js").read_text(encoding="utf-8")

    assert "window.RpgMapLocationPanel" in renderer
    assert "panelPayloadFromTurnPayload" in renderer
    assert "firstNonEmptyObj" in renderer
    assert "escapeHtml" in renderer
    assert "visible_exits" in renderer
    assert "block_reason" in renderer
    assert "Undiscovered destination" in renderer
    assert "passable" not in renderer.casefold()
    assert "/static/rpg/rpgMapLocationPanel.js" in settings
    assert "ensureMapLocationPanelScript" in settings


def test_ci_phase4_frontend_map_location_runtime_manifest_stays_authoritative():
    from app.rpg.session import runtime

    manifest = runtime.get_runtime_wrapper_manifest()

    assert manifest["final_apply_turn_authoritative_module"] == "app.rpg.session.runtime_part27"
    assert manifest["final_apply_attack_combat_action_module"] == "app.rpg.session.runtime_part23"
