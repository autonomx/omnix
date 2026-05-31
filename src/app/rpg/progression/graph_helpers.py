from __future__ import annotations

from typing import Any, Dict, List

from app.rpg.progression.models import ProgressionAction


def _a(
    action_id: str,
    command: str,
    semantic: str,
    *,
    target_type: str = "",
    target_id: str = "",
    priority: int = 50,
    mechanic: str = "",
    required_mechanic: str = "",
    completes_mechanic: str = "",
    completion_flags: List[str] = None,
    changed_parts: List[str] = None,
    effects: Dict[str, Any] = None,
    display: Dict[str, Any] = None,
    action_terms: List[str] = None,
) -> ProgressionAction:
    return ProgressionAction(
        action_id=action_id,
        command=command,
        semantic=semantic,
        target_type=target_type,
        target_id=target_id,
        priority=priority,
        mechanic=mechanic,
        required_mechanic=required_mechanic,
        completes_mechanic=completes_mechanic,
        completion_flags=completion_flags or [],
        changed_parts=changed_parts or [],
        effects=effects or {},
        display=display or {},
        action_terms=action_terms or [],
    )
