from __future__ import annotations

from copy import deepcopy
import inspect
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = ROOT / ".github" / "workflows" / "rpg-pr-deterministic.yml"
RENDERER = ROOT / "src" / "static" / "rpg" / "rpgObjectiveJournalPanel.js"
SETTINGS_BOOTSTRAP = ROOT / "src" / "static" / "rpg-conversation-settings.js"
SOURCE = "deterministic_phase8_objective_journal_detail_panel_gate"
GATE_NAME = "RPG CI Phase 8 objective journal detail panel gate"
GATE_COMMAND = "python -m pytest src/tests/rpg/test_ci_phase8_objective_journal_detail_panel.py -q --tb=short"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_ci_phase8_objective_journal_panel_payload_is_source_backed_and_non_mutating():
    from app.rpg.session import runtime_part27

    simulation_state = {
        "player_state": {"survival_state": {"hunger": 12, "thirst": 82}},
        "journal_state": {
            "objectives": [
                {"id": "obj:ask_bran", "title": "Ask Bran about the bandits", "status": "active"},
                {"id": "obj:visit_road", "title": "Visit the Old Road", "status": "available"},
                {"id": "obj:find_badge", "title": "Find the torn badge", "status": "blocked", "reason": "Need a clue"},
                {"id": "obj:rent_room", "title": "Rent a room", "status": "completed"},
            ],
            "entries": [
                {"id": "entry:1", "title": "Rusty Flagon", "body": "Bran mentioned fresh tracks.", "turn_index": 2}
            ],
        },
    }
    runtime_state = {
        "last_turn_result": {"ok": False, "reason": "route_blocked", "action_type": "travel"},
        "last_player_action": {"action_id": "player_action:7", "action_type": "travel", "target_id": "location:old_road"},
    }
    before_sim = deepcopy(simulation_state)
    before_runtime = deepcopy(runtime_state)

    panel = runtime_part27._phase8_objective_journal_panel_payload(simulation_state, runtime_state)

    assert simulation_state == before_sim
    assert runtime_state == before_runtime
    assert panel["source"] == SOURCE
    assert panel["frontend_source"] == SOURCE
    assert panel["non_mutating"] is True
    assert panel["active_objective"]["title"] == "Ask Bran about the bandits"
    assert panel["active_objective"]["status_label"] == "Active"
    assert [item["title"] for item in panel["objectives"]["available"]] == ["Visit the Old Road"]
    assert [item["title"] for item in panel["objectives"]["completed"]] == ["Rent a room"]
    assert panel["objectives"]["blocked"][0]["blocking_reason"] == "Need a clue"
    assert panel["journal_entries"][0]["body"] == "Bran mentioned fresh tracks."
    assert panel["recent_action_state"] == {
        "ok": False,
        "action_id": "player_action:7",
        "action_type": "travel",
        "target_id": "location:old_road",
        "reason": "route_blocked",
        "summary": "",
        "source": SOURCE,
    }
    assert {warning["kind"] for warning in panel["major_warnings"]} == {"high_thirst", "last_action_failed"}

    helper_sources = "\n".join(
        inspect.getsource(getattr(runtime_part27, name))
        for name in (
            "_phase8_objective_journal_panel_payload",
            "_phase8_grouped_objectives",
            "_phase8_journal_entries",
            "_phase8_recent_action_state",
        )
    )
    assert "provider" not in helper_sources.lower()
    assert "llm" not in helper_sources.lower()


def test_ci_phase8_objective_journal_panel_attaches_to_travel_payload(monkeypatch):
    from app.rpg.locations import OLD_ROAD
    from app.rpg.session import runtime_part27

    saved = {}

    def save_runtime_session(payload):
        saved.clear()
        saved.update(deepcopy(payload))
        return payload

    monkeypatch.setattr(runtime_part27, "save_runtime_session", save_runtime_session)
    session_id = "ci_phase8_objective_journal_panel_travel"
    session = {
        "manifest": {"session_id": session_id, "id": session_id},
        "setup_payload": {},
        "runtime_state": {"tick": 4, "narration_mode": "deterministic"},
        "simulation_state": {
            "player_state": {
                "inventory_state": {
                    "items": [
                        {"item_id": "ration", "qty": 1},
                        {"item_id": "water_skin", "qty": 1},
                    ]
                }
            },
            "travel_state": {"current_location_id": "location:rusty_flagon"},
            "journal_state": {
                "objectives": [{"title": "Reach the old road", "status": "active"}],
                "entries": [{"title": "Road rumor", "body": "The road is dangerous."}],
            },
        },
    }

    result = runtime_part27._apply_phase4_session_travel_command(
        session_id,
        "go to old road",
        session=session,
        simulation_state=session["simulation_state"],
        runtime_state=session["runtime_state"],
    )

    panel = result["objective_journal_panel"]
    assert result["ok"] is True
    assert result["player_hud"]["current_location_id"] == OLD_ROAD
    assert panel["source"] == SOURCE
    assert panel["active_objective"]["title"] == "Reach the old road"
    assert result["resolved_result"]["objective_journal_panel"] == panel
    assert result["narration_context"]["objective_journal_panel"] == panel
    assert saved["runtime_state"]["tick"] == 5


def test_ci_phase8_objective_journal_panel_attaches_to_base_turn_payload(monkeypatch):
    from app.rpg.session import runtime_part27

    session_id = "ci_phase8_objective_journal_panel_base"

    monkeypatch.setattr(
        runtime_part27,
        "load_runtime_session",
        lambda _session_id: {
            "manifest": {"session_id": session_id, "id": session_id},
            "runtime_state": {"tick": 1},
            "simulation_state": {
                "journal_state": {"objectives": [{"title": "Ask around town", "status": "available"}]},
            },
        },
    )

    def base_turn(_session_id, _player_input, _action=None, *, performance_override=None):
        return {"ok": True, "result": {"summary": "base turn"}, "source": "base"}

    monkeypatch.setattr(runtime_part27, "_base_apply_turn_authoritative", base_turn)

    payload = runtime_part27._apply_turn_authoritative(session_id, "ask Bran about work")

    assert payload["player_hud"]["source"] == "deterministic_phase8_player_visible_state_objective_hud_gate"
    assert payload["objective_journal_panel"]["source"] == SOURCE
    assert payload["objective_journal_panel"]["active_objective"]["title"] == "Ask around town"


def test_ci_phase8_objective_journal_browser_renderer_uses_safe_visible_payload():
    renderer = _read(RENDERER)
    settings = _read(SETTINGS_BOOTSTRAP)

    for expected in (
        "window.RpgObjectiveJournalPanel",
        "objectiveJournalPayloadFromTurnPayload",
        "firstNonEmptyObj",
        "escapeHtml",
        "rpgObjectiveJournalPanel",
        "active_objective",
        "objectives.active",
        "objectives.available",
        "objectives.completed",
        "objectives.blocked",
        "journal_entries",
        "recent_action_state",
        "major_warnings",
        "data-source",
    ):
        assert expected in renderer

    assert "Math.random" not in renderer
    assert "provider" not in renderer.lower()
    assert "llm" not in renderer.lower()
    assert "innerHTML" in renderer
    assert "escapeHtml" in renderer
    assert "/static/rpg/rpgObjectiveJournalPanel.js" in settings
    assert "ensureObjectiveJournalPanelScript" in settings


def test_ci_phase8_objective_journal_renderer_escapes_state_values():
    renderer = _read(RENDERER)

    assert ".replace(/&/g, \"&amp;\")" in renderer
    assert ".replace(/</g, \"&lt;\")" in renderer
    assert ".replace(/>/g, \"&gt;\")" in renderer
    assert "${escapeHtml(activeObjective.title || \"No active objective recorded\")}" in renderer
    assert "${escapeHtml(source)}" in renderer
    assert "${escapeHtml(title)}" in renderer


def test_ci_phase8_objective_journal_workflow_gate_is_ordered_before_manifest():
    workflow = _read(WORKFLOW)

    assert GATE_NAME in workflow
    assert GATE_COMMAND in workflow
    previous_gate = "RPG CI Phase 8 player visible state objective HUD gate"
    next_gate = "RPG CI runtime facade manifest gate"
    assert workflow.index(previous_gate) < workflow.index(GATE_NAME) < workflow.index(next_gate)


def test_ci_phase8_objective_journal_runtime_manifest_stays_authoritative():
    from app.rpg.session import runtime

    manifest = runtime.get_runtime_wrapper_manifest()

    assert "runtime_part27" in manifest["part_modules"]
    assert runtime._apply_turn_authoritative.__module__ == manifest[
        "final_apply_turn_authoritative_module"
    ]
    assert manifest["final_apply_attack_combat_action_module"] == "app.rpg.session.runtime_part23"
