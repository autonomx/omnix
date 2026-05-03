from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Literal


SocialStance = Literal[
    "neutral",
    "cooperative",
    "cautious",
    "resistant",
    "fearful",
    "hostile",
    "impressed",
    "dismissive",
]

SocialApproach = Literal[
    "polite",
    "logical",
    "emotional",
    "bribe",
    "deceptive",
]

LeverageKind = Literal[
    "debt",
    "secret",
    "favor",
    "threat",
    "promise",
    "evidence",
]


@dataclass
class SocialRelationship:
    trust: int = 0
    fear: int = 0
    respect: int = 0
    hostility: int = 0
    reputation: int = 0
    leverage: List[Dict[str, Any]] = field(default_factory=list)
    last_stance: SocialStance = "neutral"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SocialProfile:
    npc_id: str
    bravery: int = 50
    greed: int = 30
    honor: int = 50
    stubbornness: int = 40
    social_awareness: int = 50
    authority_respect: int = 50
    risk_tolerance: int = 40

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SocialLeverage:
    leverage_id: str
    npc_id: str
    kind: LeverageKind
    summary: str
    strength: int = 0
    valid: bool = True
    source_memory_id: str = ""
    expires_after_turn: int | None = None
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)