from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

ALLOWED_SUGGESTION_KEYS = {
    "npc_intent",
    "dialogue_direction",
    "scene_pressure",
    "quest_pacing",
    "ambient_event",
    "companion_behavior",
    "rumor_idea",
}

FORBIDDEN_TRUTH_KEYS = {
    "inventory",
    "currency",
    "xp",
    "combat_state",
    "location",
    "quest_completion",
    "save_state",
    "player_state",
    "party_state",
}


@dataclass
class RpgDirectionReview:
    accepted: bool
    accepted_keys: list[str] = field(default_factory=list)
    rejected_keys: list[str] = field(default_factory=list)
    reason: str = ""


def review_rpg_direction(payload: dict[str, Any]) -> RpgDirectionReview:
    keys = set(payload.keys())
    forbidden = sorted(keys & FORBIDDEN_TRUTH_KEYS)
    if forbidden:
        return RpgDirectionReview(
            accepted=False,
            accepted_keys=sorted(keys & ALLOWED_SUGGESTION_KEYS),
            rejected_keys=forbidden,
            reason="rpg_truth_mutation_not_allowed",
        )

    accepted = sorted(keys & ALLOWED_SUGGESTION_KEYS)
    unknown = sorted(keys - ALLOWED_SUGGESTION_KEYS)
    if not accepted:
        return RpgDirectionReview(
            accepted=False,
            rejected_keys=unknown,
            reason="no_supported_direction_keys",
        )

    return RpgDirectionReview(
        accepted=True,
        accepted_keys=accepted,
        rejected_keys=unknown,
        reason="suggestion_only",
    )


def build_direction_prompt_context(payload: dict[str, Any]) -> dict[str, Any]:
    review = review_rpg_direction(payload)
    return {
        "accepted": review.accepted,
        "accepted_keys": review.accepted_keys,
        "rejected_keys": review.rejected_keys,
        "reason": review.reason,
        "truth_boundary": "RPG simulation owns inventory, currency, XP, combat, location, quests, party, and save/load state.",
    }
