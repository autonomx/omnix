from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List


@dataclass
class NPCEvolutionRecord:
    npc_id: str
    active_arcs: List[str] = field(default_factory=list)
    completed_arcs: List[str] = field(default_factory=list)
    profession: str = ""
    role: str = ""
    motivation: str = ""
    companion_eligible: bool = False
    companion_offered: bool = False
    personality: Dict[str, int] = field(default_factory=dict)
    flags: Dict[str, Any] = field(default_factory=dict)
    history: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)