from __future__ import annotations

from typing import Any, Dict

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.app.rpg.api.rpg_session_routes import rpg_session_bp
from src.app.rpg.session import runtime as rt


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


def _make_app() -> TestClient:
    app = FastAPI()
    app.include_router(rpg_session_bp)
    return TestClient(app)


def _extract_summaries_from_world_events_payload(payload: Dict[str, Any]) -> list[str]:
    rows = payload.get("rows") or payload.get("events") or payload.get("world_events") or []
    out = []
    for row in rows:
        if isinstance(row, dict):
            out.append(str(row.get("summary") or "").strip())
    return out


@pytest.mark.functional
def test_world_events_route_keeps_interaction_visible_until_next_unrelated_input(monkeypatch):
    """
    Route-level end-to-end regression:

    1. Start arm wrestling with Bran.
    2. Persist active interaction in session state.
    3. Idle ticks occur.
    4. /api/rpg/session/world_events still returns contest-related rows.
    5. Unrelated next player command clears the contest visibility.
    """

    # Deterministic semantic advisory so test does not depend on live LLM output.
    def fake_semantic_advisory(*args, **kwargs):
        lowered = " ".join(str(x) for x in args if isinstance(x, str)).lower()
        if "arm wrestle" in lowered or "arm wrestling" in lowered:
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
            "reason": "Unrelated follow-up input.",
        }

    monkeypatch.setattr("app.rpg.ai.semantic_action_intelligence.get_semantic_action_advisory", fake_semantic_advisory)

    # Avoid provider dependency if narration is hit by apply_turn.
    def fake_narration(*args, **kwargs):
        return {
            "ok": True,
            "used_llm": False,
            "raw_llm_narrative": "",
            "narrative": "Test narration.",
            "reply": "Test reply.",
        }

    monkeypatch.setattr("app.rpg.ai.world_scene_narrator.narrate_scene", fake_narration)

    # Create and save a real session.
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

    client = _make_app()

    # Start the contest.
    result_1 = rt.apply_turn(session_id, "I challenge Bran to arm wrestling")
    assert result_1["ok"] is True

    saved = rt.load_runtime_session(session_id)
    assert rt._safe_dict(saved.get("runtime_state")).get("last_player_action")
    assert rt._safe_list(rt._safe_dict(saved.get("simulation_state")).get("active_interactions"))

    # First idle tick.
    saved = rt._apply_idle_tick_to_session(saved, reason="heartbeat")
    rt.save_runtime_session(saved)

    response = client.post(
        "/api/rpg/session/world_events",
        json={"session_id": session_id},
    )
    assert response.status_code == 200
    payload = response.json()
    summaries_after_idle = _extract_summaries_from_world_events_payload(payload)
    joined_after_idle = " || ".join(summaries_after_idle).lower()

    assert (
        "arm wrest" in joined_after_idle
        or "contest" in joined_after_idle
        or "match" in joined_after_idle
        or "challenge" in joined_after_idle
    ), f"Expected contest-related world event after idle, got: {summaries_after_idle}"

    # Second idle tick: should still persist because mode is until_next_command.
    saved = rt._apply_idle_tick_to_session(saved, reason="heartbeat")
    rt.save_runtime_session(saved)

    response = client.post(
        "/api/rpg/session/world_events",
        json={"session_id": session_id},
    )
    assert response.status_code == 200
    payload = response.json()
    summaries_second_idle = _extract_summaries_from_world_events_payload(payload)
    joined_second_idle = " || ".join(summaries_second_idle).lower()

    assert (
        "arm wrest" in joined_second_idle
        or "contest" in joined_second_idle
        or "match" in joined_second_idle
        or "challenge" in joined_second_idle
    ), f"Expected contest to remain visible until next input, got: {summaries_second_idle}"

    # Unrelated next input should clear/resolve it.
    result_2 = rt.apply_turn(session_id, "I look around the tavern")
    assert result_2["ok"] is True

    saved = rt.load_runtime_session(session_id)
    saved = rt._apply_idle_tick_to_session(saved, reason="heartbeat")
    rt.save_runtime_session(saved)

    response = client.post(
        "/api/rpg/session/world_events",
        json={"session_id": session_id},
    )
    assert response.status_code == 200
    payload = response.json()
    summaries_after_unrelated = _extract_summaries_from_world_events_payload(payload)
    joined_after_unrelated = " || ".join(summaries_after_unrelated).lower()

    assert "arm wrest" not in joined_after_unrelated
    assert "contest" not in joined_after_unrelated
    assert "match" not in joined_after_unrelated