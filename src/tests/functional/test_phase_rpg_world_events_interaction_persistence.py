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
            "player_state": {
                "name": "Player",
            },
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


def _world_summaries(session: Dict[str, Any]) -> list[str]:
    rows = build_player_world_view_rows(
        rt._safe_dict(session.get("simulation_state")),
        rt._safe_dict(session.get("runtime_state")),
    )
    return [str(rt._safe_dict(row).get("summary") or "").strip() for row in rows]


def test_arm_wrestling_event_stays_visible_in_world_events_until_next_unrelated_input(monkeypatch):
    """
    End-to-end guard for the exact behavior we want:

    1. Player starts arm wrestling with Bran.
    2. The interaction is persisted into session state.
    3. Idle ticks keep the interaction active.
    4. World events include contest-related rows while active.
    5. A later unrelated command clears/resolves the interaction.
    """

    # --- Create deterministic semantic interpretation so the test does not depend on live LLM output.
    def fake_semantic_advisory(*args, **kwargs):
        text = kwargs.get("player_input", "")
        if not text:
            text = " ".join(str(x) for x in args if isinstance(x, str))
        text = text.lower()
        if "arm wrestle" in text or "arm wrestling" in text:
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
                "social_axes": [{"axis": "respect", "delta": 1}],
                "observer_hooks": ["spectacle", "crowd_attention", "authority_notice"],
                "scene_impact": "gathers_attention",
                "reason": "Public tavern contest between player and Bran.",
            }
        return {
            "action_type": "observe",
            "semantic_family": "utility",
            "interaction_mode": "solo",
            "activity_label": "look_around",
            "target_id": "",
            "target_name": "",
            "visibility": "local",
            "intensity": 0,
            "stakes": 0,
            "social_axes": [],
            "observer_hooks": [],
            "scene_impact": "none",
            "reason": "Non-interaction follow-up.",
        }

    monkeypatch.setattr(rt, "get_semantic_action_advisory", fake_semantic_advisory)

    def fake_action_advisory(*args, **kwargs):
        return {
            "action_type": "social_competition",
            "target_id": "npc_innkeeper",
            "target_name": "Bran the Innkeeper",
        }

    monkeypatch.setattr(rt, "get_action_advisory", fake_action_advisory)

    # Optional but useful: avoid any live narration/provider dependency if apply_turn touches it.
    def fake_narration(*args, **kwargs):
        return {
            "ok": True,
            "used_llm": False,
            "raw_llm_narrative": "",
            "narrative": "Test narration.",
            "reply": "Test reply.",
        }

    monkeypatch.setattr(rt, "narrate_scene", fake_narration)

    # Also prevent live LLM gateway usage.
    monkeypatch.setattr(rt, "build_app_llm_gateway", lambda: None)

    # Mock session store for test isolation
    fake_session_store = {}

    def _fake_save(session):
        sid = rt._safe_dict(session.get("manifest")).get("session_id") or session.get("session_id", "")
        if sid:
            fake_session_store[sid] = session
        return session

    def _fake_load(session_id):
        return fake_session_store.get(session_id)

    monkeypatch.setattr(rt, "load_runtime_session", _fake_load)
    monkeypatch.setattr(rt, "save_runtime_session", _fake_save)

    # --- Build and save a real session.
    session = rt.build_session_from_start_result(
        {"title": "Test Tavern", "location_name": "Tavern"},
        _base_start_result(),
    )
    session_id = rt._safe_dict(session.get("manifest")).get("session_id")
    assert session_id

    session["runtime_state"] = rt._safe_dict(session.get("runtime_state"))
    session["runtime_state"]["runtime_settings"] = rt._normalize_runtime_settings(
        {
            "interaction_duration_mode": "until_next_command",
            "interaction_duration_ticks": 5,
            "response_length": "short",
        }
    )
    rt.save_runtime_session(session)

    # --- Start the contest.
    result_1 = rt.apply_turn(session_id, "I challenge Bran to arm wrestling")
    assert result_1["ok"] is True

    saved = rt.load_runtime_session(session_id)
    saved_rt = rt._safe_dict(saved.get("runtime_state"))
    saved_sim = rt._safe_dict(saved.get("simulation_state"))

    # The turn must persist both the player action and active interaction.
    assert rt._safe_dict(saved_rt.get("last_player_action")), "last_player_action was not persisted"
    assert rt._safe_list(saved_sim.get("active_interactions")), "active_interactions were not persisted"

    # --- Run an idle tick. The interaction should still be active before next unrelated command.
    idle_result = rt._apply_idle_tick_to_session(saved, reason="heartbeat")
    assert idle_result.get("ok") is True, f"idle tick failed: {idle_result.get('error')}"
    saved = idle_result["session"]
    rt.save_runtime_session(saved)

    summaries_after_idle = _world_summaries(saved)
    joined_after_idle = " || ".join(summaries_after_idle).lower()

    assert (
        "arm wrest" in joined_after_idle
        or "contest" in joined_after_idle
        or "match" in joined_after_idle
        or "challenge" in joined_after_idle
    ), f"Expected wrestling/contest-related world event, got: {summaries_after_idle}"

    # --- A second idle tick should STILL keep it visible in until_next_command mode.
    idle_result_2 = rt._apply_idle_tick_to_session(saved, reason="heartbeat")
    assert idle_result_2.get("ok") is True, f"idle tick 2 failed: {idle_result_2.get('error')}"
    saved = idle_result_2["session"]
    rt.save_runtime_session(saved)

    summaries_second_idle = _world_summaries(saved)
    joined_second_idle = " || ".join(summaries_second_idle).lower()

    assert (
        "arm wrest" in joined_second_idle
        or "contest" in joined_second_idle
        or "match" in joined_second_idle
        or "challenge" in joined_second_idle
    ), f"Expected event to persist until next player input, got: {summaries_second_idle}"

    # --- Now send an unrelated command. This should resolve/clear the interaction.
    result_2 = rt.apply_turn(session_id, "I look around the tavern")
    assert result_2["ok"] is True

    saved = rt.load_runtime_session(session_id)
    idle_result_3 = rt._apply_idle_tick_to_session(saved, reason="heartbeat")
    assert idle_result_3.get("ok") is True, f"idle tick 3 failed: {idle_result_3.get('error')}"
    saved = idle_result_3["session"]
    rt.save_runtime_session(saved)

    summaries_after_unrelated = _world_summaries(saved)
    joined_after_unrelated = " || ".join(summaries_after_unrelated).lower()

    assert "arm wrest" not in joined_after_unrelated
    assert "contest" not in joined_after_unrelated
    assert "match" not in joined_after_unrelated