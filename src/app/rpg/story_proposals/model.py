from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List

STORY_PROPOSAL_VERSION = "story_proposal_v1"


@dataclass
class StoryProposal:
    proposal_version: str = STORY_PROPOSAL_VERSION
    proposal_type: str = "story_pack"
    proposal_id: str = ""
    title: str = ""
    lore_entries: List[Dict[str, Any]] = field(default_factory=list)
    story_arcs: List[Dict[str, Any]] = field(default_factory=list)
    story_events: List[Dict[str, Any]] = field(default_factory=list)
    escalation_rules: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)