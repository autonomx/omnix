from __future__ import annotations

from copy import deepcopy
import inspect
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = ROOT / ".github" / "workflows" / "rpg-pr-deterministic.yml"
RENDERER = ROOT / "src" / "static" / "rpg" / "rpgCombatActionPanel.js"
SETTINGS_BOOTSTRAP = ROOT / "src" / "static" / "rpg-conversation-settings.js"
SOURCE = "deterministic_phase8_combat_state_action_affordance_gate"
GATE_NAME = "RPG CI Phase 8 combat state action affordance gate"
GATE_COMMAND = "python -m pytest src/tests/rpg/test_ci_phase8_combat_state_action_affordance.py -q --tb=short"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_ci_phase8_combat_panel_payload_is_source_backed_and_non_mutating():
    from app.rpg.session import runtime_part27

    simulation_state = {
        "player_state": {"survival_state": {"hunger": 10, "thirst": 10}},
    }
    runtime_state = {
        "combat_state": {
            "active": True,
            "combat_id": "combat:test",
            "current_actor_id": "player",
            "participants": {
                "bandit": {"name": "<Bandit>", "side": "enemy", "hp": 6, "max_hp": 10},
                "player": {"name": "Hero", "side": "player", "hp": 12, "max_hp": 12},
            },
        },
        "last_turn_result": {"ok": True, "action_type": "attack", "summary": "hit"},
        "last_player_action": {"action_id": "player_action:8", "action_type": "attack", "target_id": "bandit"},
    }
    before_sim = deepcopy(simulation_state)
    before_runtime = deepcopy(runtime_state)

    panel = runtime_part27._phase8_combat_panel_payload(simulation_state, runtime_state)

    assert simulation_state == before_sim
    assert runtime_state == before_runtime
    assert panel["source"] == SOURCE
    assert panel["frontend_source"] == SOURCE
    assert panel["non_mutating"] is True
    assert panel["active"] is True
    assert panel["status_label"] == "In combat"
    assert panel["current_actor_id"] == "player"
    assert panel["player_actor_id"] == "player"
    assert panel["is_player_turn"] is True
    assert [row["actor_id"] for row in panel["participants"]] == ["bandit", "player"]
    assert panel["participants"][0]["name"] == "<Bandit>"
    assert panel["target_summary"][0]["actor_id"] == "bandit"
    assert panel["legal_actions"][0] == {
        "action_type": "attack",
        "target_id": "bandit",
        "label": "Attack <Bandit>",
        "enabled": True,
        "source": SOURCE,
    }
    assert panel["legal_actions"][-1]["action_type"] == "defend"
    assert panel["recent_action_state"]["action_type"] == "attack"

    helper_sources = "\n".join(
        inspect.getsource(getattr(runtime_part27, name))
        for name in (
            "_phase8_combat_panel_payload",
            "_phase8_combat_legal_actions",
            "_phase8_combat_participants",
            "_phase8_combat_panel_warnings",
        )
    )
    assert "provider" not in helper_sources.lower()
    assert "llm" not in helper_sources.lower()


def test_ci_phase8_combat_panel_blocks_affordances_when_not_player_turn():
    from app.rpg.session import runtime_part27

    panel = runtime_part27._phase8_combat_panel_payload(
        {},
        {
            "combat_state": {
                "active": True,
                "current_actor_id": "bandit",
                "participants": {
                    "bandit": {"name": "Bandit", "side": "enemy", "hp": 8, "max_hp": 8},
                    "player": {"name": "Hero", "side": "player", "hp": 9, "max_hp": 12},
                },
            },
            "last_turn_result": {"ok": False, "reason": "not_player_turn"},
        },
    )

    assert panel["is_player_turn"] is False
    assert panel["legal_actions"] == []
    assert {warning["kind"] for warning in panel["major_warnings"]} == {
        "waiting_for_npc_turn",
        "last_combat_action_rejected",
    }


def test_ci_phase8_combat_panel_attaches_to_travel_payload(monkeypatch):
    from app.rpg.locations import OLD_ROAD
    from app.rpg.session import runtime_part27

    saved = {}

    def save_runtime_session(payload):
        saved.clear()
        saved.update(deepcopy(payload))
        return payload

    monkeypatch.setattr(runtime_part27, "save_runtime_session", save_runtime_session)
    session_id = "ci_phase8_combat_action_panel_travel"
    session = {
        "manifest": {"session_id": session_id, "id": session_id},
        "setup_payload": {},
        "runtime_state": {
            "tick": 4,
            "narration_mode": "deterministic",
            "combat_state": {
                "active": True,
                "current_actor_id": "player",
                "participants": {
                    "player": {"side": "player", "hp": 10, "max_hp": 10},
                    "wolf": {"name": "Wolf", "side": "enemy", "hp": 4, "max_hp": 6},
                },
            },
        },
        "simulation_state": {
            "player_state": {
                "inventory_state": {"items": [{"item_id": "ration", "qty": 1}]},
            },
            "travel_state": {"current_location_id": "location:rusty_flagon"},
        },
    }

    result = runtime_part27._apply_phase4_session_travel_command(
        session_id,
        "go to old road",
        session=session,
        simulation_state=session["simulation_state"],
        runtime_state=session["runtime_state"],
    )

    panel = result["combat_action_panel"]
    assert result["ok"] is True
    assert result["player_hud"]["current_location_id"] == OLD_ROAD
    assert panel["source"] == SOURCE
    assert panel["legal_actions"][0]["target_id"] == "wolf"
    assert result["resolved_result"]["combat_action_panel"] == panel
    assert result["narration_context"]["combat_action_panel"] == panel
    assert saved["runtime_state"]["tick"] == 5


def test_ci_phase8_combat_panel_attaches_to_base_turn_payload(monkeypatch):
    from app.rpg.session import runtime_part27

    session_id = "ci_phase8_combat_action_panel_base"

    monkeypatch.setattr(
        runtime_part27,
        "load_runtime_session",
        lambda _session_id: {
            "manifest": {"session_id": session_id, "id": session_id},
            "runtime_state": {
                "tick": 1,
                "combat_state": {
                    "active": True,
                    "current_actor_id": "player",
                    "participants": {
                        "player": {"side": "player", "hp": 9, "max_hp": 9},
                        "bandit": {"side": "enemy", "hp": 7, "max_hp": 7},
                    },
                },
            },
            "simulation_state": {},
        },
    )

    def base_turn(_session_id, _player_input, _action=None, *, performance_override=None):
        return {"ok": True, "result": {"summary": "base turn"}, "source": "base"}

    monkeypatch.setattr(runtime_part27, "_base_apply_turn_authoritative", base_turn)

    payload = runtime_part27._apply_turn_authoritative(session_id, "attack bandit")

    assert payload["player_hud"]["source"] == "deterministic_phase8_player_visible_state_objective_hud_gate"
    assert payload["objective_journal_panel"]["source"] == "deterministic_phase8_objective_journal_detail_panel_gate"
    assert payload["combat_action_panel"]["source"] == SOURCE
    assert payload["combat_action_panel"]["legal_actions"][0]["target_id"] == "bandit"


def test_ci_phase8_combat_browser_renderer_uses_safe_visible_payload():
    renderer = _read(RENDERER)
    settings = _read(SETTINGS_BOOTSTRAP)

    for expected in (
        "window.RpgCombatActionPanel",
        "combatActionPayloadFromTurnPayload",
        "firstNonEmptyObj",
        "escapeHtml",
        "rpgCombatActionPanel",
        "combat_action_panel",
        "participants",
        "legal_actions",
        "major_warnings",
        "current_actor_id",
        "is_player_turn",
        "data-source",
    ):
        assert expected in renderer

    assert "Math.random" not in renderer
    assert "provider" not in renderer.lower()
    assert "llm" not in renderer.lower()
    assert "innerHTML" in renderer
    assert "escapeHtml" in renderer
    assert "/static/rpg/rpgCombatActionPanel.js" in settings
    assert "ensureCombatActionPanelScript" in settings


def test_ci_phase8_combat_renderer_escapes_state_values():
    renderer = _read(RENDERER)

    assert ".replace(/&/g, \"&amp;\")" in renderer
    assert ".replace(/</g, \"&lt;\")" in renderer
    assert ".replace(/>/g, \"&gt;\")" in renderer
    assert "${escapeHtml(source)}" in renderer
    assert "${escapeHtml(name)}" in renderer
    assert "${escapeHtml(label)}" in renderer


def test_ci_phase8_combat_workflow_gate_is_ordered_before_manifest():
    workflow = _read(WORKFLOW)

    assert GATE_NAME in workflow
    assert GATE_COMMAND in workflow
    previous_gate = "RPG CI Phase 8 objective journal detail panel gate"
    next_gate = "RPG CI runtime facade manifest gate"
    assert workflow.index(previous_gate) < workflow.index(GATE_NAME) < workflow.index(next_gate)


def test_ci_phase8_combat_runtime_manifest_stays_authoritative():
    from app.rpg.session import runtime

    manifest = runtime.get_runtime_wrapper_manifest()

    assert manifest["final_apply_turn_authoritative_module"] == "app.rpg.session.runtime_part27"
    assert manifest["final_apply_attack_combat_action_module"] == "app.rpg.session.runtime_part23"
