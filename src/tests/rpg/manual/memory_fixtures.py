from __future__ import annotations

from typing import Any, Dict


def build_manual_memory_event(name: str) -> Dict[str, Any]:
    if name == "same_room_greeting":
        return {
            "event_id": "evt:manual_same_room_greeting",
            "actor_id": "player",
            "target_id": "bran",
            "location_id": "tavern_common_room",
            "summary": "The player greeted Bran in the tavern common room.",
            "tags": ["social", "greeting"],
            "sound_level": "normal",
        }

    if name == "private_room_quiet_event":
        return {
            "event_id": "evt:manual_private_room_quiet_event",
            "actor_id": "guest_private",
            "target_id": "spy",
            "location_id": "private_room",
            "summary": "A quiet private exchange happened in the private room.",
            "tags": ["private", "quiet"],
            "sound_level": "quiet",
        }

    if name == "private_room_argument":
        return {
            "event_id": "evt:manual_private_room_argument",
            "actor_id": "guest_private",
            "target_id": "spy",
            "location_id": "private_room",
            "summary": "A muffled argument came from the private room.",
            "tags": ["argument", "muffled"],
            "sound_level": "normal",
        }

    if name == "player_affects_bran":
        return {
            "event_id": "evt:manual_player_affects_bran",
            "actor_id": "player",
            "target_id": "bran",
            "location_id": "tavern_common_room",
            "summary": "The player directly insulted Bran.",
            "tags": ["insult", "social"],
            "sound_level": "normal",
        }

    if name == "street_bandit_seen":
        return {
            "event_id": "evt:manual_street_bandit_seen",
            "actor_id": "bandit",
            "target_id": "player",
            "location_id": "street",
            "summary": "A bandit confronted the player in the street.",
            "tags": ["bandit", "threat"],
            "sound_level": "normal",
        }

    raise KeyError(f"unknown_manual_memory_event:{name}")