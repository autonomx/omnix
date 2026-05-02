from __future__ import annotations

from typing import Any, Dict

SCENE_ACTIVITY_SCENARIOS: Dict[str, Dict[str, Any]] = {
    "scene_activity_respects_cooldown": {
        "currency": {
            "gold": 0,
            "silver": 0,
            "copper": 0
        },
        "conversation_settings": {
            "enabled": True,
            "autonomous_ticks_enabled": True,
            "frequency": "off",
            "conversation_chance_percent": 0,
            "allow_scene_activities": True,
            "scene_activity_interval_ticks": 1,
            "scene_activity_cooldown_ticks": 10
        },
        "turns": [
            "__scene_activity_tick__",
            "__scene_activity_tick__"
        ]
    },
    "scene_activity_schedules_idle_action": {
        "currency": {
            "gold": 0,
            "silver": 0,
            "copper": 0
        },
        "conversation_settings": {
            "enabled": True,
            "autonomous_ticks_enabled": True,
            "frequency": "off",
            "conversation_chance_percent": 0,
            "allow_scene_activities": True,
            "scene_activity_interval_ticks": 1,
            "scene_activity_cooldown_ticks": 0,
            "allow_scene_activity_world_events": True,
            "allow_scene_activity_world_signals": True
        },
        "turns": [
            "__scene_activity_tick__",
            "__scene_activity_tick__"
        ]
    },
}