from __future__ import annotations

from app.rpg.session import interactive_first_call_runtime as interactive_runtime


def _session_override():
    return {
        "session_id": "ce212_app_fast_direct",
        "simulation_state": {
            "player_state": {"location_id": "loc:tavern"},
            "npc_index": {},
        },
        "runtime_state": {
            "tick": 1,
            "combat_state": {
                "active": True,
                "participants": {
                    "player": {"side": "player", "hp": 10, "name": "Player"},
                    "enemy:road_bandit": {"side": "enemy", "hp": 8, "name": "road bandit"},
                },
            },
        },
    }


def _install_runtime_capture(monkeypatch):
    observed = {}

    def fail_gateway():  # pragma: no cover - failure path asserted by raising
        raise AssertionError("first-call provider should be bypassed for fast-direct turns")

    def fake_runtime_apply_turn(**kwargs):
        observed["kwargs"] = kwargs
        action = dict(kwargs.get("action") or {})
        return {
            "ok": True,
            "result": {
                "action_type": action.get("action_type"),
                "visible_interaction_reason": "fast_direct_runtime_test",
            },
            "runtime_state": {
                "tick": 2,
                "combat_state": {"active": True},
            },
            "simulation_state": {},
            "narration": "Result: fast_direct_runtime_test",
            "final_narration": "Result: fast_direct_runtime_test",
        }

    monkeypatch.setattr(interactive_runtime, "build_app_llm_gateway", fail_gateway)
    monkeypatch.setattr(interactive_runtime.canonical_runtime, "apply_turn", fake_runtime_apply_turn)
    monkeypatch.setattr(interactive_runtime.canonical_runtime, "save_runtime_session", lambda session: session)
    monkeypatch.setattr(interactive_runtime.canonical_runtime, "load_runtime_session", lambda session_id: _session_override())
    return observed


def test_ce212_fast_direct_combat_bypasses_first_call_provider(monkeypatch):
    observed = _install_runtime_capture(monkeypatch)

    result = interactive_runtime.apply_turn(
        session_id="ce212_app_fast_direct",
        player_input="I attack the road bandit",
        performance_override={"fast_turn_mode": True, "narration_mode": "deferred"},
        session_override=_session_override(),
    )

    assert observed["kwargs"]["action"]["action_type"] == "combat"
    assert observed["kwargs"]["action"]["metadata"]["fast_direct_runtime"] is True
    assert observed["kwargs"]["action"]["metadata"]["skip_sync_combat_narration"] is True
    assert observed["kwargs"]["performance_override"]["skip_sync_combat_narration"] is True
    assert result["fast_direct_runtime"] is True
    assert result["llm_called"] is False
    assert result["first_call_grounding_diagnostics"]["source"] == "ce212_fast_direct_runtime_budget_v1"


def test_ce212_fast_direct_survival_bypasses_first_call_provider(monkeypatch):
    observed = _install_runtime_capture(monkeypatch)

    result = interactive_runtime.apply_turn(
        session_id="ce212_app_fast_direct",
        player_input="I drink from my waterskin",
        performance_override={"fast_turn_mode": True, "narration_mode": "deferred"},
        session_override=_session_override(),
    )

    assert observed["kwargs"]["action"]["action_type"] == "observe"
    assert observed["kwargs"]["action"]["target_id"] == "player:survival"
    assert result["fast_direct_runtime"] is True
    assert result["llm_called"] is False


def test_ce212_fast_direct_travel_bypasses_first_call_provider(monkeypatch):
    observed = _install_runtime_capture(monkeypatch)

    result = interactive_runtime.apply_turn(
        session_id="ce212_app_fast_direct",
        player_input="I continue north on the road to the old mill",
        performance_override={"fast_turn_mode": True, "narration_mode": "deferred"},
        session_override=_session_override(),
    )

    assert observed["kwargs"]["action"]["action_type"] == "travel"
    assert observed["kwargs"]["action"]["target_id"] == "loc:old_mill"
    assert result["fast_direct_runtime"] is True
    assert result["llm_called"] is False
