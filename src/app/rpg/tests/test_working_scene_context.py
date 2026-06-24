from __future__ import annotations

from app.rpg.session.working_scene_context import (
    WORKING_SCENE_CONTEXT_VERSION,
    build_working_scene_context,
    estimate_context_tokens,
)


def _session() -> dict:
    return {
        "manifest": {"session_id": "session-1"},
        "state": {
            "location": "Rusty Flagon Tavern",
            "player": {
                "name": "Aria",
                "level": 2,
                "currency": {"silver": 12},
                "inventory": [{"name": "Short sword"}, {"name": "Ration"}],
            },
            "quests": [{"title": "Bandit trail", "status": "active", "objective": "Ask Bran about the witness"}],
        },
        "runtime_state": {
            "time": "evening",
            "visible_npcs": [{"id": "npc:bran", "name": "Bran", "role": "innkeeper"}],
            "recent_turns": [{"summary": "You entered the tavern."}, {"summary": "Bran cleaned a mug."}],
        },
    }


def test_build_working_scene_context_compacts_scene_blocks() -> None:
    context = build_working_scene_context(_session(), player_input="Ask Bran about monsters nearby")

    assert context["format_version"] == WORKING_SCENE_CONTEXT_VERSION
    assert context["blocks"]["scene"]["location"] == "Rusty Flagon Tavern"
    assert context["blocks"]["player"]["name"] == "Aria"
    assert context["blocks"]["visible_npcs"][0]["name"] == "Bran"
    assert "Ask Bran" in context["compact_text"]
    assert context["estimated_tokens"] == estimate_context_tokens(context["compact_text"])


def test_working_scene_context_honors_token_budget_by_trimming_recent_turns() -> None:
    session = _session()
    session["runtime_state"]["recent_turns"] = [{"summary": f"recent event {index} " * 20} for index in range(20)]

    context = build_working_scene_context(session, max_tokens=80)

    assert context["estimated_tokens"] <= 80
    assert len(context["blocks"]["recent"]) < 6


def test_working_scene_context_deduplicates_visible_npcs() -> None:
    session = _session()
    session["state"]["visible_npcs"] = [{"name": "Bran"}, {"name": "Elara"}]

    context = build_working_scene_context(session)
    names = [npc["name"] for npc in context["blocks"]["visible_npcs"]]

    assert names == ["Bran", "Elara"]
