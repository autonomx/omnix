from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Literal

PuzzleStatus = Literal["inactive", "active", "solved", "failed"]


@dataclass
class PuzzleRecord:
    puzzle_id: str
    title: str
    status: PuzzleStatus = "inactive"
    state: str = "initial"
    flags: Dict[str, Any] = field(default_factory=dict)
    attempts: int = 0
    solved_turn: int | None = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)