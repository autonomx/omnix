from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Literal

StoryArcStatus = Literal["inactive", "active", "resolved", "failed"]


@dataclass
class StoryArcRecord:
    arc_id: str
    title: str
    status: StoryArcStatus = "inactive"
    stage: str = "inactive"
    pressure: int = 0
    escalation_level: int = 0
    linked_lore: List[str] = field(default_factory=list)
    linked_quests: List[str] = field(default_factory=list)
    linked_puzzles: List[str] = field(default_factory=list)
    linked_locations: List[str] = field(default_factory=list)
    linked_entities: List[str] = field(default_factory=list)
    flags: Dict[str, Any] = field(default_factory=dict)
    started_turn: int | None = None
    resolved_turn: int | None = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)