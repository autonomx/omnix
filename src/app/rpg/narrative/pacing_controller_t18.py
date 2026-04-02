"""Pacing Controller - World Pacing from Narrative State.

TIER 18: Narrative Intelligence - Meta-AI Story Director
"""


class PacingController:
    """Adjusts world pacing from narrative phase."""

    def adjust(self, story_state, world):
        phase = story_state.phase
        if phase == "climax":
            world["npc_activity_multiplier"] = 1.5
            world["event_frequency"] = world.get("event_frequency", 1.0) * 1.3
        elif phase == "falling":
            world["npc_activity_multiplier"] = 0.7
            world["event_frequency"] = world.get("event_frequency", 1.0) * 0.8
        else:
            world["npc_activity_multiplier"] = 1.0
            world["event_frequency"] = world.get("event_frequency", 1.0) * 1.0
        return world
