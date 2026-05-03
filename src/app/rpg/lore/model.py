from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Literal

LoreTruthStatus = Literal["true", "rumor", "false", "myth", "unknown", "secret"]


@dataclass
class LoreEntry:
    lore_id: str
    title: str
    kind: str = "fact"
    truth_status: LoreTruthStatus = "unknown"
    revealed_to_player: bool = False
    known_by: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    summary: str = ""
    source: str = "manual"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)