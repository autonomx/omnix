from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Literal


BarrierKind = Literal[
    "none",
    "door",
    "locked_door",
    "wall",
    "window",
    "curtain",
    "gate",
    "portcullis",
]

VisibilityMode = Literal[
    "open",
    "partial",
    "blocked",
]

AudibilityMode = Literal[
    "open",
    "muffled",
    "blocked",
]


@dataclass
class SpatialArea:
    area_id: str
    name: str
    description: str = ""
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SpatialConnection:
    connection_id: str
    from_area_id: str
    to_area_id: str
    label: str = ""
    bidirectional: bool = True

    barrier_kind: BarrierKind = "none"
    is_open: bool = True
    is_locked: bool = False
    blocks_movement: bool = False
    visibility: VisibilityMode = "open"
    audibility: AudibilityMode = "open"

    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SpatialEntityLocation:
    entity_id: str
    area_id: str
    hidden: bool = False
    silent: bool = False
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SpatialSceneGraph:
    graph_id: str
    current_area_id: str
    areas: Dict[str, SpatialArea] = field(default_factory=dict)
    connections: Dict[str, SpatialConnection] = field(default_factory=dict)
    entity_locations: Dict[str, SpatialEntityLocation] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "graph_id": self.graph_id,
            "current_area_id": self.current_area_id,
            "areas": {k: v.to_dict() for k, v in self.areas.items()},
            "connections": {k: v.to_dict() for k, v in self.connections.items()},
            "entity_locations": {
                k: v.to_dict() for k, v in self.entity_locations.items()
            },
            "metadata": dict(self.metadata),
        }