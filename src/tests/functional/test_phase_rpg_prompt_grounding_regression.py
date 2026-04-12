"""Phase: Prompt grounding regression test suite."""
from __future__ import annotations

from typing import Any, Dict, List

import pytest


class _PromptCapture:
    def __init__(self) -> None:
        self.payloads: List[Dict[str, Any]] = []

    def __call__(self, *args, **kwargs):
        self.payloads.append({"args": args, "kwargs": kwargs})
        return {
            "narrator": "You look around.",
            "action": "You observe the tavern.",
            "npc": {"speaker_id": "none", "name": "None", "text": "", "emotion": "", "portrait": ""},
            "reward": "",
        }


def _make_session():
    return {
        "session_id": "prompt_grounding_regression",
        "simulation_state": {
            "tick": 5,
            "locations": [{"location_id": "loc:tavern", "name": "The Rusty Flagon Tavern"}],
            "npc_index": {
                "npc:bran": {"name": "Bran the Innkeeper", "location_id": "loc:tavern"},
                "npc:elara": {"name": "Elara the Merchant", "location_id": "loc:tavern"},
                "npc:aldric": {"name": "Captain Aldric", "location_id": "loc:tavern"},
            },
            "player_state": {
                "location_id": "loc:tavern",
                "nearby_npc_ids": ["npc:bran", "npc:elara", "npc:aldric"],
            },
        },
        "runtime_state": {
            "opening": (
                "The story opens in The Rusty Flagon Tavern. "
                "Present: Bran the Innkeeper, Elara the Merchant, Captain Aldric."
            ),
            "current_scene": {
                "scene_id": "scene:opening",
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
            "settings": {"response_length": "short"},
            "ambient_queue": [],
            "ambient_seq": 0,
            "ambient_cooldowns": {},
            "grounded_scene_context": {},
        },
    }


def test_turn_prompt_never_reverts_to_untitled_unknown_empty(monkeypatch):
    import app.rpg.ai.world_scene_narrator as narrator_mod
    from app.rpg.session import runtime as runtime_mod

    capture = _PromptCapture()
    store = {"prompt_grounding_regression": _make_session()}

    monkeypatch.setattr(runtime_mod, "load_runtime_session", lambda session_id: store.get(session_id))
    monkeypatch.setattr(runtime_mod, "save_runtime_session", lambda session: store.__setitem__(session["session_id"], session) or session)
    monkeypatch.setattr(narrator_mod, "_generate_live_narrative", capture, raising=False)

    runtime_mod.apply_turn("prompt_grounding_regression", "i look around", action=None)

    assert capture.payloads, "Expected narration payload to be captured"
    serialized = str(capture.payloads[-1])

    assert "Untitled Scene" not in serialized
    assert "unknown location" not in serialized
    assert "Actors present:" not in serialized or "Actors present:" in serialized and "Bran the Innkeeper" in serialized
    assert "The Rusty Flagon Tavern" in serialized