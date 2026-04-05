"""Phase 8.2 — Encounter Actions.

Builds available player actions based on encounter type.
Bounds: available actions max 12.
"""

from __future__ import annotations

from typing import Any, Dict, List


def build_player_actions(encounter_state: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Build a list of available player actions based on encounter type.

    Args:
        encounter_state: The current encounter state dict.

    Returns:
        List of action dicts with action_id, label, type keys. Max 12.
    """
    encounter_state = dict(encounter_state or {})
    encounter_type = str(encounter_state.get("encounter_type") or "")

    base = [
        {"action_id": "wait", "label": "Wait", "type": "wait"},
        {"action_id": "observe", "label": "Observe", "type": "observe"},
    ]

    if encounter_type == "combat":
        base.extend([
            {"action_id": "attack", "label": "Attack", "type": "attack"},
            {"action_id": "defend", "label": "Defend", "type": "defend"},
            {"action_id": "withdraw", "label": "Withdraw", "type": "withdraw"},
        ])
    elif encounter_type == "social":
        base.extend([
            {"action_id": "persuade", "label": "Persuade", "type": "persuade"},
            {"action_id": "pressure", "label": "Pressure", "type": "pressure"},
            {"action_id": "concede", "label": "Concede", "type": "concede"},
        ])
    elif encounter_type == "stealth":
        base.extend([
            {"action_id": "hide", "label": "Hide", "type": "hide"},
            {"action_id": "sneak", "label": "Sneak", "type": "sneak"},
            {"action_id": "distract", "label": "Distract", "type": "distract"},
        ])
    else:
        # Default standoff actions
        base.extend([
            {"action_id": "approach", "label": "Approach", "type": "approach"},
            {"action_id": "threaten", "label": "Threaten", "type": "threaten"},
            {"action_id": "retreat", "label": "Retreat", "type": "retreat"},
        ])

    return base[:12]