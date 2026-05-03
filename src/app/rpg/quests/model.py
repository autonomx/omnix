from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Literal

QuestStatus = Literal["inactive", "active", "completed", "failed"]
ObjectiveStatus = Literal["open", "completed", "failed"]


@dataclass
class QuestObjective:
    objective_id: str
    description: str
    status: ObjectiveStatus = "open"
    completed_turn: int | None = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class QuestRecord:
    quest_id: str
    title: str
    status: QuestStatus = "inactive"
    stage: str = "inactive"
    objectives: Dict[str, QuestObjective] = field(default_factory=dict)
    flags: Dict[str, Any] = field(default_factory=dict)
    rewards: List[Dict[str, Any]] = field(default_factory=list)
    reward_claimed: bool = False
    started_turn: int | None = None
    completed_turn: int | None = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "quest_id": self.quest_id,
            "title": self.title,
            "status": self.status,
            "stage": self.stage,
            "objectives": {
                key: objective.to_dict()
                for key, objective in self.objectives.items()
            },
            "flags": dict(self.flags),
            "rewards": list(self.rewards),
            "reward_claimed": bool(self.reward_claimed),
            "started_turn": self.started_turn,
            "completed_turn": self.completed_turn,
            "metadata": dict(self.metadata),
        }