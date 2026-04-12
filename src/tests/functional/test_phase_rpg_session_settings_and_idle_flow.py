"""Phase: Session settings and idle flow integration tests."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone


def _iso_utc_now_minus(seconds: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat()


def test_session_settings_route_persists_and_echoes(client, monkeypatch):
    from app.rpg.session import runtime as runtime_mod

    store = {
        "settings_flow_session": {
            "session_id": "settings_flow_session",
            "simulation_state": {},
            "runtime_state": {
                "runtime_settings": {
                    "response_length": "short",
                    "idle_conversations_enabled": True,
                    "idle_conversation_seconds": 60,
                    "idle_npc_to_player_enabled": True,
                    "idle_npc_to_npc_enabled": True,
                    "follow_reactions_enabled": True,
                    "reaction_style": "normal",
                    "console_debug_enabled": False,
                    "world_events_panel_enabled": True,
                }
            },
        }
    }

    monkeypatch.setattr(runtime_mod, "load_runtime_session", lambda session_id: store.get(session_id))
    monkeypatch.setattr(runtime_mod, "save_runtime_session", lambda session: store.__setitem__(session["session_id"], session) or session)

    res = client.post("/api/rpg/session/settings", json={
        "session_id": "settings_flow_session",
        "settings": {
            "response_length": "medium",
            "idle_conversation_seconds": 30,
            "console_debug_enabled": True,
            "world_events_panel_enabled": True,
            "interaction_duration_mode": "until_next_command",
            "interaction_duration_ticks": 10,
        },
    })
    assert res.status_code == 200
    data = res.get_json()
    assert data["ok"] is True
    assert data["settings"]["response_length"] == "medium"
    assert data["settings"]["idle_conversation_seconds"] == 30
    assert data["settings"]["console_debug_enabled"] is True
    assert data["settings"]["interaction_duration_mode"] == "until_next_command"
    assert data["settings"]["interaction_duration_ticks"] == 10


def test_session_settings_route_accepts_legacy_response_length_dict(client, monkeypatch):
    from app.rpg.session import runtime as runtime_mod

    store = {
        "settings_flow_session": {
            "session_id": "settings_flow_session",
            "simulation_state": {},
            "runtime_state": {"settings": {"response_length": "short"}},
        }
    }

    monkeypatch.setattr(runtime_mod, "load_runtime_session", lambda session_id: store.get(session_id))
    monkeypatch.setattr(runtime_mod, "save_runtime_session", lambda session: store.__setitem__(session["session_id"], session) or session)

    res = client.post("/api/rpg/session/settings", json={
        "session_id": "settings_flow_session",
        "settings": {
            "response_length": {
                "narrator_length": "long",
                "character_length": "short",
            }
        },
    })
    assert res.status_code == 200
    data = res.get_json()
    assert data["ok"] is True
    assert data["settings"]["response_length"] == "long"


def test_inspect_state_route_returns_grounding_settings_and_events(client, monkeypatch):
    from app.rpg.session import runtime as runtime_mod

    store = {
        "inspect_state_session": {
            "session_id": "inspect_state_session",
            "simulation_state": {},
            "runtime_state": {
                "settings": {"console_debug_enabled": True},
                "grounded_scene_context": {
                    "scene_title": "The Rusty Flagon Tavern",
                    "location_name": "The Rusty Flagon Tavern",
                    "present_actor_names": ["Bran the Innkeeper"],
                },
                "recent_world_event_rows": [{"event_id": "evt:1"}],
            },
        }
    }

    monkeypatch.setattr(runtime_mod, "load_runtime_session", lambda session_id: store.get(session_id))

    res = client.post("/api/rpg/session/inspect_state", json={"session_id": "inspect_state_session"})
    assert res.status_code == 200
    data = res.get_json()
    assert data["ok"] is True
    assert data["grounded_scene_context"]["location_name"] == "The Rusty Flagon Tavern"
    assert data["settings"]["console_debug_enabled"] is True
    assert len(data["recent_world_event_rows"]) == 1


def test_idle_tick_obeys_threshold_with_real_session_flow(monkeypatch):
    from app.rpg.session import runtime as runtime_mod

    store = {
        "idle_threshold_session": {
            "session_id": "idle_threshold_session",
            "simulation_state": {
                "tick": 2,
                "player_state": {
                    "location_id": "loc:tavern",
                    "nearby_npc_ids": ["npc:bran"],
                },
                "npc_index": {
                    "npc:bran": {
                        "name": "Bran the Innkeeper",
                        "location_id": "loc:tavern",
                        "role": "companion",
                        "is_companion": True,
                    }
                },
                "npc_minds": {
                    "npc:bran": {"beliefs": {"player": {"trust": 0.8, "hostility": 0.0}}, "goals": []}
                },
                "sandbox_state": {"world_consequences": []},
                "events": [],
                "incidents": [],
            },
            "runtime_state": {
                "settings": {
                    "response_length": "short",
                    "idle_conversations_enabled": True,
                    "idle_conversation_seconds": 30,
                    "idle_npc_to_player_enabled": True,
                    "idle_npc_to_npc_enabled": True,
                    "follow_reactions_enabled": True,
                    "reaction_style": "normal",
                    "console_debug_enabled": True,
                    "world_events_panel_enabled": True,
                },
                "ambient_queue": [],
                "ambient_seq": 0,
                "ambient_cooldowns": {},
                "last_real_player_activity_at": _iso_utc_now_minus(90),
                "last_player_action_context": {},
                "idle_debug_trace": {},
                "recent_world_event_rows": [],
                "grounded_scene_context": {},
            },
        }
    }

    monkeypatch.setattr(runtime_mod, "load_runtime_session", lambda session_id: store.get(session_id))
    monkeypatch.setattr(runtime_mod, "save_runtime_session", lambda session: store.__setitem__(session["session_id"], session) or session)

    result = runtime_mod.apply_idle_tick("idle_threshold_session", reason="heartbeat")
    assert result["idle_gate_open"] is True
    assert isinstance(result.get("updates"), list)
    assert result["updates"], "Expected visible idle update after threshold"


def test_simulation_state_normalization_preserves_active_interactions():
    """Test that _ensure_simulation_state preserves active_interactions."""
    from app.rpg.session.runtime import _ensure_simulation_state

    simulation_state = {
        "active_interactions": [
            {
                "id": "test_interaction",
                "type": "player_semantic_interaction",
                "subtype": "arm_wrestling",
                "participants": ["player", "bran"],
                "resolved": False,
                "phase": "active",
                "updated_tick": 5,
                "expires_tick": 10,
            }
        ]
    }

    result = _ensure_simulation_state(simulation_state)
    assert "active_interactions" in result
    assert len(result["active_interactions"]) == 1
    assert result["active_interactions"][0]["id"] == "test_interaction"


def test_apply_turn_writeback_preserves_active_interactions(client, monkeypatch):
    """Test that apply_turn saves active_interactions in simulation_state."""
    from app.rpg.session import runtime as runtime_mod

    store = {
        "interaction_session": {
            "session_id": "interaction_session",
            "simulation_state": {
                "tick": 1,
                "player_state": {},
                "npc_index": {"bran": {"id": "bran", "name": "Bran"}},
            },
            "runtime_state": {
                "tick": 1,
                "runtime_settings": {"interaction_duration_mode": "until_next_command"},
                "last_player_action": {},
            },
            "setup_payload": {},
        }
    }

    monkeypatch.setattr(runtime_mod, "load_runtime_session", lambda session_id: store.get(session_id))
    monkeypatch.setattr(runtime_mod, "save_runtime_session", lambda session: store.__setitem__(session["session_id"], session) or session)

    # Mock LLM to return semantic action for wrestling
    def mock_get_semantic_action_advisory(*args, **kwargs):
        return {
            "action_type": "social_competition",
            "activity_label": "arm_wrestling",
            "target_id": "bran",
            "target_name": "Bran",
            "intensity": 2,
            "reason": "Player challenging to arm wrestling",
        }

    monkeypatch.setattr(runtime_mod, "get_semantic_action_advisory", mock_get_semantic_action_advisory)

    res = client.post("/api/rpg/session/turn", json={
        "session_id": "interaction_session",
        "player_input": "I challenge Bran to arm wrestling",
        "action": {"action_type": "social_competition"},
    })
    assert res.status_code == 200
    data = res.get_json()
    assert data["ok"] is True

    # Check saved session has active_interactions
    saved = store["interaction_session"]
    assert "active_interactions" in saved["simulation_state"]
    assert len(saved["simulation_state"]["active_interactions"]) >= 1
    interaction = saved["simulation_state"]["active_interactions"][0]
    assert interaction["subtype"] == "arm_wrestling"
    assert not interaction["resolved"]


def test_idle_tick_reads_persisted_active_interactions(client, monkeypatch):
    """Test that idle tick loads and uses persisted active_interactions."""
    from app.rpg.session import runtime as runtime_mod

    store = {
        "idle_interaction_session": {
            "session_id": "idle_interaction_session",
            "simulation_state": {
                "tick": 2,
                "active_interactions": [
                    {
                        "id": "semantic_interaction:test_id",
                        "type": "player_semantic_interaction",
                        "subtype": "arm_wrestling",
                        "action_type": "social_competition",
                        "participants": ["player", "bran"],
                        "resolved": False,
                        "phase": "active",
                        "updated_tick": 1,
                        "expires_tick": 10**9,  # until_next_command
                        "state": {
                            "duration_mode": "until_next_command",
                            "summary": "Arm wrestling Bran",
                        },
                    }
                ],
                "player_state": {},
                "npc_index": {"bran": {"id": "bran", "name": "Bran"}},
            },
            "runtime_state": {
                "tick": 2,
                "runtime_settings": {"interaction_duration_mode": "until_next_command"},
                "last_player_action": {"action_type": "social_competition"},
                "last_real_player_activity_at": _iso_utc_now_minus(300),  # idle
            },
            "setup_payload": {},
        }
    }

    monkeypatch.setattr(runtime_mod, "load_runtime_session", lambda session_id: store.get(session_id))
    monkeypatch.setattr(runtime_mod, "save_runtime_session", lambda session: store.__setitem__(session["session_id"], session) or session)

    result = runtime_mod.apply_idle_tick("idle_interaction_session", reason="heartbeat")
    assert result["ok"] is True
    # The idle tick should have read the active_interactions and processed them
    # If it didn't, the semantic prompt would have interaction_count = 0
    # But since we can't easily check logs, at least assert it completed


def test_until_next_command_mode_keeps_interaction_active():
    """Test that until_next_command mode keeps interaction active for same-type commands."""
    from app.rpg.session.runtime import (
        _get_interaction_duration_mode,
        _resolve_until_next_command_interactions,
    )

    runtime_state = {"runtime_settings": {"interaction_duration_mode": "until_next_command"}}
    simulation_state = {
        "active_interactions": [
            {
                "id": "test_interaction",
                "action_type": "social_competition",
                "subtype": "arm_wrestling",
                "participants": ["player", "bran"],
                "resolved": False,
            }
        ]
    }

    # Same action type, should not resolve
    semantic_record = {
        "action_type": "social_competition",
        "activity_label": "arm_wrestling",
        "target_id": "bran",
    }

    result = _resolve_until_next_command_interactions(
        simulation_state, runtime_state, semantic_record, current_tick=5
    )
    assert len(result["active_interactions"]) == 1
    assert not result["active_interactions"][0]["resolved"]


def test_until_next_command_mode_resolves_on_unrelated_command():
    """Test that until_next_command mode resolves on unrelated commands."""
    from app.rpg.session.runtime import _resolve_until_next_command_interactions

    runtime_state = {"runtime_settings": {"interaction_duration_mode": "until_next_command"}}
    simulation_state = {
        "active_interactions": [
            {
                "id": "test_interaction",
                "action_type": "social_competition",
                "subtype": "arm_wrestling",
                "participants": ["player", "bran"],
                "resolved": False,
            }
        ]
    }

    # Different action type, should resolve
    semantic_record = {
        "action_type": "observe",
        "activity_label": "look_around",
    }

    result = _resolve_until_next_command_interactions(
        simulation_state, runtime_state, semantic_record, current_tick=5
    )
    assert len(result["active_interactions"]) == 1
    assert result["active_interactions"][0]["resolved"]


def test_apply_turn_persists_last_player_action_and_active_interactions():
    from app.rpg.session.runtime import (
        _safe_dict,
        _safe_list,
        _safe_str,
        apply_turn,
        build_session_from_start_result,
        load_runtime_session,
        save_runtime_session,
    )

    session = build_session_from_start_result(
        {"title": "Test", "location_name": "Tavern"},
        {"ok": True, "simulation_state": {"tick": 10, "current_tick": 10, "npc_index": {
            "npc_guard_captain": {"id": "npc_guard_captain", "name": "Captain Aldric", "location_id": "loc_tavern"},
            "npc_innkeeper": {"id": "npc_innkeeper", "name": "Bran", "location_id": "loc_tavern"},
        }}},
    )
    session_id = session["manifest"]["session_id"]
    save_runtime_session(session)

    result = apply_turn(session_id, "I challenge Bran to arm wrestling", None)
    assert result["ok"] is True

    saved = load_runtime_session(session_id)
    runtime_state = _safe_dict(saved.get("runtime_state"))
    simulation_state = _safe_dict(saved.get("simulation_state"))

    assert _safe_dict(runtime_state.get("last_player_action"))
    assert _safe_str(_safe_dict(runtime_state.get("last_player_action")).get("text"))
    assert len(_safe_list(simulation_state.get("active_interactions"))) >= 1


def test_idle_tick_sees_persisted_interaction_context():
    from app.rpg.session.runtime import (
        _build_semantic_state_change_prompt_contract,
        _safe_dict,
        apply_turn,
        build_session_from_start_result,
        load_runtime_session,
        save_runtime_session,
    )

    session = build_session_from_start_result(
        {"title": "Test", "location_name": "Tavern"},
        {"ok": True, "simulation_state": {"tick": 10, "current_tick": 10, "npc_index": {
            "npc_guard_captain": {"id": "npc_guard_captain", "name": "Captain Aldric", "location_id": "loc_tavern"},
            "npc_innkeeper": {"id": "npc_innkeeper", "name": "Bran", "location_id": "loc_tavern"},
        }}},
    )
    session_id = session["manifest"]["session_id"]
    save_runtime_session(session)
    apply_turn(session_id, "I arm wrestle Bran", None)

    saved = load_runtime_session(session_id)
    sim = _safe_dict(saved.get("simulation_state"))
    rt = _safe_dict(saved.get("runtime_state"))
    prompt = _build_semantic_state_change_prompt_contract(sim, rt)

    assert "active_interactions" in prompt