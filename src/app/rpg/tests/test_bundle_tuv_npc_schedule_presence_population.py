from __future__ import annotations

from app.rpg.world.conversation_director import select_conversation_intent
from app.rpg.world.npc_presence_runtime import (
    present_npcs_at_location,
    update_present_npcs_for_location,
)
from app.rpg.world.scene_population_runtime import build_scene_population_state


def test_schedule_populates_tavern_presence():
    state = {"location_state": {"current_location_id": "loc_tavern"}}
    result = update_present_npcs_for_location(state, location_id="loc_tavern", tick=1)

    assert result["updated"] is True
    present = present_npcs_at_location(state, location_id="loc_tavern")
    assert "npc:Bran" in present
    assert "npc:Mira" in present
    assert "npc:GuardCaptain" not in present


def test_scene_population_uses_presence_and_biographies():
    state = {"location_state": {"current_location_id": "loc_tavern"}}
    population = build_scene_population_state(state, location_id="loc_tavern", tick=1)

    names = {npc["name"] for npc in population["present_npcs"]}
    roles = {npc["role"] for npc in population["present_npcs"]}

    assert "Bran" in names
    assert "Mira" in names
    assert "Tavern keeper" in roles
    assert "Curious local informant" in roles


def test_director_uses_presence_runtime_without_guard_fallback():
    state = {
        "location_state": {"current_location_id": "loc_tavern"},
        "quest_state": {
            "quests": [
                {
                    "quest_id": "quest:old_mill_bandits",
                    "title": "Trouble near the Old Mill",
                    "summary": "There is talk of armed figures near the old mill road.",
                    "status": "active",
                    "location_id": "loc_tavern",
                }
            ]
        },
    }

    intent = select_conversation_intent(
        state,
        settings={
            "npc_presence_enabled": True,
            "conversation_director_cooldown_ticks": 4,
        },
        tick=10,
    )

    assert intent["selected"] is True
    assert intent["speaker_id"] in {"npc:Bran", "npc:Mira"}
    assert intent["listener_id"] in {"npc:Bran", "npc:Mira"}
    assert "npc:GuardCaptain" not in {intent["speaker_id"], intent["listener_id"]}
    assert intent["topic_type"] == "quest"
