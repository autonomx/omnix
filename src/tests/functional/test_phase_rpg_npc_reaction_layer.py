from __future__ import annotations

from typing import Any, Dict

from app.rpg.analytics.world_events import build_player_world_view_rows
from app.rpg.session import runtime as rt


def _base_start_result() -> Dict[str, Any]:
    return {
        "ok": True,
        "simulation_state": {
            "tick": 20,
            "current_tick": 20,
            "scene_title": "Tavern",
            "location_name": "Tavern",
            "location_id": "loc_tavern",
            "player_state": {"name": "Player"},
            "npc_index": {
                "npc_guard_captain": {
                    "id": "npc_guard_captain",
                    "name": "Captain Aldric",
                    "location_id": "loc_tavern",
                    "role": "guard captain",
                },
                "npc_innkeeper": {
                    "id": "npc_innkeeper",
                    "name": "Bran the Innkeeper",
                    "location_id": "loc_tavern",
                    "role": "innkeeper",
                },
                "npc_merchant": {
                    "id": "npc_merchant",
                    "name": "Elara the Merchant",
                    "location_id": "loc_tavern",
                    "role": "merchant",
                },
            },
        },
    }


def _summaries(session: Dict[str, Any]) -> list[str]:
    rows = build_player_world_view_rows(
        rt._safe_dict(session.get("simulation_state")),
        rt._safe_dict(session.get("runtime_state")),
    )
    return [str(rt._safe_dict(r).get("summary") or "").strip() for r in rows]


def test_arm_wrestling_causes_observer_reaction(monkeypatch):
    def fake_semantic_advisory(*args, **kwargs):
        text = kwargs.get("player_input", "")
        return {
            "action_type": "social_competition",
            "semantic_family": "social",
            "interaction_mode": "direct",
            "activity_label": "arm_wrestling",
            "target_id": "npc_innkeeper",
            "target_name": "Bran the Innkeeper",
            "visibility": "public",
            "intensity": 2,
            "stakes": 1,
            "social_axes": [],
            "observer_hooks": ["spectacle", "crowd_attention"],
            "scene_impact": "gathers_attention",
            "reason": text,
        }

    monkeypatch.setattr(rt, "get_semantic_action_advisory", fake_semantic_advisory)
    monkeypatch.setattr(rt, "build_app_llm_gateway", lambda: None)
    monkeypatch.setattr(
        rt,
        "narrate_scene",
        lambda *args, **kwargs: {"ok": True, "used_llm": False, "narrative": "Test", "reply": "Test"},
    )

    fake_store = {}

    def _fake_save(session):
        sid = rt._safe_dict(session.get("manifest")).get("session_id")
        fake_store[sid] = session
        return session

    def _fake_load(session_id):
        return fake_store.get(session_id)

    monkeypatch.setattr(rt, "save_runtime_session", _fake_save)
    monkeypatch.setattr(rt, "load_runtime_session", _fake_load)

    session = rt.build_session_from_start_result({"title": "Test Tavern"}, _base_start_result())
    sid = rt._safe_dict(session.get("manifest")).get("session_id")
    session["runtime_state"]["runtime_settings"] = rt._normalize_runtime_settings(
        {"interaction_duration_mode": "until_next_command", "interaction_duration_ticks": 5}
    )
    rt.save_runtime_session(session)

    result = rt.apply_turn(sid, "I challenge Bran to arm wrestling")
    assert result["ok"] is True

    saved = rt.load_runtime_session(sid)
    idle = rt._apply_idle_tick_to_session(saved, reason="heartbeat")
    assert idle["ok"] is True
    saved = idle["session"]

    joined = " || ".join(_summaries(saved)).lower()
    assert "watches the scene closely" in joined or "pauses to watch" in joined


def test_punching_bran_causes_guard_intervention(monkeypatch):
    def fake_semantic_advisory(*args, **kwargs):
        text = kwargs.get("player_input", "")
        return {
            "action_type": "violence",
            "semantic_family": "combat",
            "interaction_mode": "direct",
            "activity_label": "punching_in_the_face",
            "target_id": "npc_innkeeper",
            "target_name": "Bran the Innkeeper",
            "visibility": "public",
            "intensity": 3,
            "stakes": 2,
            "social_axes": [],
            "observer_hooks": ["authority_attention", "crowd_attention"],
            "scene_impact": "violence",
            "reason": text,
        }

    monkeypatch.setattr(rt, "get_semantic_action_advisory", fake_semantic_advisory)
    monkeypatch.setattr(rt, "build_app_llm_gateway", lambda: None)
    monkeypatch.setattr(
        rt,
        "narrate_scene",
        lambda *args, **kwargs: {"ok": True, "used_llm": False, "narrative": "Test", "reply": "Test"},
    )

    fake_store = {}

    def _fake_save(session):
        sid = rt._safe_dict(session.get("manifest")).get("session_id")
        fake_store[sid] = session
        return session

    def _fake_load(session_id):
        return fake_store.get(session_id)

    monkeypatch.setattr(rt, "save_runtime_session", _fake_save)
    monkeypatch.setattr(rt, "load_runtime_session", _fake_load)

    session = rt.build_session_from_start_result({"title": "Test Tavern"}, _base_start_result())
    sid = rt._safe_dict(session.get("manifest")).get("session_id")
    session["runtime_state"]["runtime_settings"] = rt._normalize_runtime_settings(
        {"interaction_duration_mode": "until_next_command", "interaction_duration_ticks": 5}
    )
    rt.save_runtime_session(session)

    result = rt.apply_turn(sid, "I punch Bran in the face")
    assert result["ok"] is True

    saved = rt.load_runtime_session(sid)
    idle = rt._apply_idle_tick_to_session(saved, reason="heartbeat")
    assert idle["ok"] is True
    saved = idle["session"]

    joined = " || ".join(_summaries(saved)).lower()
    assert "steps in to stop the violence" in joined or "moves closer, ready to intervene" in joined

    pressure = rt._safe_list(rt._safe_dict(saved.get("runtime_state")).get("world_pressure"))
    pressure_joined = " || ".join([str(rt._safe_dict(p).get("summary") or "").lower() for p in pressure])
    assert "violence" in pressure_joined or "intervene" in pressure_joined or "watch" in pressure_joined


def test_reactions_do_not_duplicate_across_idle_ticks(monkeypatch):
    def fake_semantic_advisory(*args, **kwargs):
        text = kwargs.get("player_input", "")
        return {
            "action_type": "violence",
            "semantic_family": "combat",
            "interaction_mode": "direct",
            "activity_label": "punching_in_the_face",
            "target_id": "npc_innkeeper",
            "target_name": "Bran the Innkeeper",
            "visibility": "public",
            "intensity": 3,
            "stakes": 2,
            "social_axes": [],
            "observer_hooks": ["authority_attention", "crowd_attention"],
            "scene_impact": "violence",
            "reason": text,
        }

    monkeypatch.setattr(rt, "get_semantic_action_advisory", fake_semantic_advisory)
    monkeypatch.setattr(rt, "build_app_llm_gateway", lambda: None)
    monkeypatch.setattr(
        rt,
        "narrate_scene",
        lambda *args, **kwargs: {"ok": True, "used_llm": False, "narrative": "Test", "reply": "Test"},
    )

    fake_store = {}

    def _fake_save(session):
        sid = rt._safe_dict(session.get("manifest")).get("session_id")
        fake_store[sid] = session
        return session

    def _fake_load(session_id):
        return fake_store.get(session_id)

    monkeypatch.setattr(rt, "save_runtime_session", _fake_save)
    monkeypatch.setattr(rt, "load_runtime_session", _fake_load)

    session = rt.build_session_from_start_result({"title": "Test Tavern"}, _base_start_result())
    sid = rt._safe_dict(session.get("manifest")).get("session_id")
    session["runtime_state"]["runtime_settings"] = rt._normalize_runtime_settings(
        {"interaction_duration_mode": "until_next_command", "interaction_duration_ticks": 5}
    )
    rt.save_runtime_session(session)

    result = rt.apply_turn(sid, "I punch Bran in the face")
    assert result["ok"] is True

    saved = rt.load_runtime_session(sid)
    idle_1 = rt._apply_idle_tick_to_session(saved, reason="heartbeat")
    assert idle_1["ok"] is True
    saved = idle_1["session"]

    rows_1 = rt._safe_list(rt._safe_dict(saved.get("runtime_state")).get("recent_world_event_rows"))
    reaction_rows_1 = [r for r in rows_1 if rt._safe_str(rt._safe_dict(r).get("source")) == "npc_reaction_layer"]
    reaction_ids_1 = sorted(rt._safe_str(rt._safe_dict(r).get("event_id")) for r in reaction_rows_1)

    idle_2 = rt._apply_idle_tick_to_session(saved, reason="heartbeat")
    assert idle_2["ok"] is True
    saved = idle_2["session"]

    rows_2 = rt._safe_list(rt._safe_dict(saved.get("runtime_state")).get("recent_world_event_rows"))
    reaction_rows_2 = [r for r in rows_2 if rt._safe_str(rt._safe_dict(r).get("source")) == "npc_reaction_layer"]
    reaction_ids_2 = sorted(rt._safe_str(rt._safe_dict(r).get("event_id")) for r in reaction_rows_2)

    assert reaction_ids_1 == reaction_ids_2