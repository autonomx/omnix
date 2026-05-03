from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List


@dataclass
class EscalationRule:
    rule_id: str
    arc_id: str
    priority: int = 50
    event: Dict[str, Any] = field(default_factory=dict)
    conditions: List[Dict[str, Any]] = field(default_factory=list)
    cooldown_turns: int = 0
    max_applications: int = 1
    pressure_type: str = "story"
    reason: str = ""
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class EscalationRuleApplication:
    rule_id: str
    arc_id: str
    application_count: int = 0
    last_applied_turn: int | None = None
    applied_event_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)