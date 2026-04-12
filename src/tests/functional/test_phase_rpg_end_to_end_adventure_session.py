"""Phase: End-to-end RPG session lifecycle regression tests."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import pytest

# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

def _iso_utc_now_minus(seconds: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat()


def _make_start_payload() -> Dict[str, Any]:
    return {
        "session_id": "test_session_rusty_flagon",
        "opening": (
            "An ancient evil stirs, and unlikely heroes must answer the call. "
            "The story opens in The Rusty Flagon Tavern. "
            "You find yourself in The Rusty Flagon Tavern. "
            "Present: Bran the Innkeeper, Elara the Merchant, Captain Aldric."
        ),
        "world": {
            "title": "Rusty Flagon Test World",
        },
        "player": {
            "name": "Player",
        },
        "locations": [
            {
                "location_id": "loc:tavern",
                "name": "The Rusty Flagon Tavern",
            }
        ],
        "npcs": [
            {"npc_id": "npc:bran", "name": "Bran the Innkeeper", "location_id": "loc:tavern", "role": "innkeeper"},
            {"npc_id": "npc:elara", "name": "Elara the Merchant", "location_id": "loc:tavern", "role": "merchant"},
            {"npc_id": "npc:aldric", "name": "Captain Aldric", "location_id": "loc:tavern", "role": "guard"},
        ],
    }


def _make_runtime_session() -> Dict[str, Any]:
    return {
        "session_id": "test_session_rusty_flagon",
        "simulation_state": {
            "tick": 1,
            "locations": [
                {
                    "location_id": "loc:tavern",
                    "name": "The Rusty Flagon Tavern",
                }
            ],
            "npc_index": {
                "npc:bran": {
                    "name": "Bran the Innkeeper",
                    "location_id": "loc:tavern",
                    "role": "innkeeper",
                },
                "npc:elara": {
                    "name": "Elara the Merchant",
                    "location_id": "loc:tavern",
                    "role": "merchant",
                },
                "npc:aldric": {
                    "name": "Captain Aldric",
                    "location_id": "loc:tavern",
                    "role": "guard",
                },
            },
            "npc_minds": {
                "npc:bran": {
                    "beliefs": {"player": {"trust": 0.7, "hostility": 0.0}},
                    "goals": [],
                },
                "npc:elara": {
                    "beliefs": {"player": {"trust": 0.4, "hostility": 0.0}},
                    "goals": [{"id": "goal:trade", "text": "Protect my wares"}],
                },
                "npc:aldric": {
                    "beliefs": {"player": {"trust": 0.5, "hostility": 0.0}},
                    "goals": [{"id": "goal:order", "text": "Maintain order"}],
                },
            },
            "player_state": {
                "location_id": "loc:tavern",
                "nearby_npc_ids": ["npc:bran", "npc:elara", "npc:aldric"],
                "party_npc_ids": ["npc:bran"],
            },
            "events": [],
            "incidents": [],
            "sandbox_state": {
                "world_consequences": [],
            },
        },
        "runtime_state": {
            "opening": (
                "An ancient evil stirs, and unlikely heroes must answer the call. "
                "The story opens in The Rusty Flagon Tavern. "
                "You find yourself in The Rusty Flagon Tavern. "
                "Present: Bran the Innkeeper, Elara the Merchant, Captain Aldric."
            ),
            "current_scene": {
                "scene_id": "scene:tavern:opening",
                "title": "",
                "location_id": "",
                "location_name": "",
                "summary": "",
                "present_npc_ids": [],
                "actors": [],
                "items": [],
                "available_checks": [],
            },
            "turn_result": {},
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
            "idle_streak": 0,
            "last_real_player_activity_at": "",
            "last_player_action_context": {},
            "idle_debug_trace": {},
            "recent_world_event_rows": [],
            "grounded_scene_context": {},
        },
    }


class _CapturedNarrationCall:
    def __init__(self) -> None:
        self.calls: List[Dict[str, Any]] = []

    def __call__(self, *args, **kwargs) -> Dict[str, Any]:
        self.calls.append({
            "args": args,
            "kwargs": kwargs,
        })
        return {
            "narrator": "You take in the tavern around you.",
            "action": "You scan the room carefully.",
            "npc": {"speaker_id": "none", "name": "None", "text": "", "emotion": "", "portrait": ""},
            "reward": "",
        }


# ---------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------

@pytest.fixture
def captured_narration():
    return _CapturedNarrationCall()


@pytest.fixture
def fake_session_store(monkeypatch):
    store: Dict[str, Dict[str, Any]] = {}

    from app.rpg.session import runtime as runtime_mod

    def _load_runtime_session(session_id: str):
        return store.get(session_id)

    def _save_runtime_session(session: Dict[str, Any]):
        store[session["session_id"]] = session
        return session

    monkeypatch.setattr(runtime_mod, "load_runtime_session", _load_runtime_session)
    monkeypatch.setattr(runtime_mod, "save_runtime_session", _save_runtime_session)
    return store


@pytest.fixture
def patch_narrator(monkeypatch, captured_narration):
    import app.rpg.ai.world_scene_narrator as narrator_mod

    def _fake_narrate(*args, **kwargs):
        return captured_narration(*args, **kwargs)

    monkeypatch.setattr(narrator_mod, "narrate_player_action", _fake_narrate, raising=False)
    monkeypatch.setattr(narrator_mod, "narrate_scene", _fake_narrate, raising=False)
    return captured_narration


# ---------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------

def test_start_bootstrap_grounded_scene_context(fake_session_store):
    from app.rpg.session.runtime import build_frontend_bootstrap_payload

    session = _make_runtime_session()
    fake_session_store[session["session_id"]] = session

    payload = build_frontend_bootstrap_payload(session)

    assert "grounded_scene_context" in payload
    grounded = payload["grounded_scene_context"]
    assert grounded["scene_title"]
    assert grounded["location_name"] == "The Rusty Flagon Tavern"
    assert "Bran the Innkeeper" in grounded["present_actor_names"]
    assert "Elara the Merchant" in grounded["present_actor_names"]
    assert "Captain Aldric" in grounded["present_actor_names"]


def test_first_turn_prompt_is_grounded(fake_session_store, patch_narrator, captured_narration):
    from app.rpg.session.runtime import apply_turn

    session = _make_runtime_session()
    fake_session_store[session["session_id"]] = session

    result = apply_turn(session["session_id"], "i look around", action=None)
    assert result

    assert captured_narration.calls, "Narrator was never called"

    serialized = str(captured_narration.calls[-1])

    assert "Untitled Scene" not in serialized
    assert "unknown location" not in serialized
    assert "The Rusty Flagon Tavern" in serialized
    assert "Bran the Innkeeper" in serialized


def test_movement_turn_records_reaction_context(fake_session_store, patch_narrator):
    from app.rpg.session.runtime import apply_turn, load_runtime_session

    session = _make_runtime_session()
    fake_session_store[session["session_id"]] = session

    apply_turn(session["session_id"], "i run toward the door", action=None)
    saved = load_runtime_session(session["session_id"])
    ctx = saved["runtime_state"]["last_player_action_context"]

    assert ctx["movement_intent"] in ("rush", "approach", "advance")
    assert ctx["location_id"] == "loc:tavern"


def test_idle_threshold_eventually_surfaces_visible_update(fake_session_store, patch_narrator):
    from app.rpg.session.runtime import apply_idle_tick, load_runtime_session

    session = _make_runtime_session()
    session["runtime_state"]["last_real_player_activity_at"] = _iso_utc_now_minus(120)
    fake_session_store[session["session_id"]] = session

    result = apply_idle_tick(session["session_id"], reason="heartbeat")
    assert result["idle_gate_open"] is True
    assert "idle_debug_trace" in result

    updates = result.get("updates") or []
    assert isinstance(updates, list)
    assert updates, "Expected at least one visible idle update after threshold"

    kinds = {u.get("kind") for u in updates}
    assert kinds & {"idle_check_in", "npc_to_npc", "gossip", "follow_reaction", "caution_reaction"}


def test_world_events_session_flow(fake_session_store):
    from app.rpg.analytics.world_events import build_world_events_view

    session = _make_runtime_session()
    session["runtime_state"]["recent_world_event_rows"] = [
        {
            "event_id": "evt:1",
            "scope": "local",
            "kind": "idle_check_in",
            "title": "Idle Check-in",
            "summary": "Bran checks in with you.",
            "tick": 2,
            "actors": ["npc:bran"],
            "location_id": "loc:tavern",
            "priority": 0.4,
            "status": "active",
            "source": "ambient_runtime",
        }
    ]
    fake_session_store[session["session_id"]] = session

    view = build_world_events_view(session["simulation_state"], session["runtime_state"])
    assert "local_events" in view
    assert "global_events" in view
    assert "director_pressure" in view
    assert isinstance(view["local_events"], list)


def test_settings_mutation_changes_idle_threshold(fake_session_store):
    from app.rpg.session.runtime import (
        apply_idle_tick,
        load_runtime_session,
        save_runtime_session,
    )

    session = _make_runtime_session()
    session["runtime_state"]["settings"]["idle_conversation_seconds"] = 300
    session["runtime_state"]["last_real_player_activity_at"] = _iso_utc_now_minus(60)
    fake_session_store[session["session_id"]] = session

    result = apply_idle_tick(session["session_id"], reason="heartbeat")
    assert result["idle_gate_open"] is False

    saved = load_runtime_session(session["session_id"])
    saved["runtime_state"]["settings"]["idle_conversation_seconds"] = 30
    saved["runtime_state"]["last_real_player_activity_at"] = _iso_utc_now_minus(60)
    save_runtime_session(saved)

    result2 = apply_idle_tick(session["session_id"], reason="heartbeat")
    assert result2["idle_gate_open"] is True