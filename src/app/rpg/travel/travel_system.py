"""Phase 17 — Travel / map / discovery expansion.

World map, regions, routes, travel resolution, fog-of-war,
landmarks, ambient events, companion travel, map UI, analytics, determinism.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))

def _sf(v: Any, d: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return d

def _si(v: Any, d: int = 0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return d

def _ss(v: Any, d: str = "") -> str:
    return str(v) if v is not None else d

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_REGIONS = 50
MAX_ROUTES = 100
MAX_LANDMARKS = 200
MAX_TRAVEL_LOG = 100

# ---------------------------------------------------------------------------
# 17.0 — World map state foundations
# ---------------------------------------------------------------------------

@dataclass
class MapNode:
    node_id: str = ""
    name: str = ""
    region_id: str = ""
    node_type: str = "location"  # location, landmark, waypoint, dungeon
    discovered: bool = False
    x: float = 0.0
    y: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id, "name": self.name,
            "region_id": self.region_id, "node_type": self.node_type,
            "discovered": self.discovered, "x": self.x, "y": self.y,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "MapNode":
        return cls(
            node_id=_ss(d.get("node_id")), name=_ss(d.get("name")),
            region_id=_ss(d.get("region_id")),
            node_type=_ss(d.get("node_type"), "location"),
            discovered=bool(d.get("discovered", False)),
            x=_sf(d.get("x")), y=_sf(d.get("y")),
            metadata=dict(d.get("metadata") or {}),
        )


@dataclass
class MapRoute:
    route_id: str = ""
    from_node: str = ""
    to_node: str = ""
    distance: float = 1.0
    difficulty: float = 0.0
    discovered: bool = False
    blocked: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "route_id": self.route_id, "from_node": self.from_node,
            "to_node": self.to_node, "distance": self.distance,
            "difficulty": self.difficulty, "discovered": self.discovered,
            "blocked": self.blocked,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "MapRoute":
        return cls(
            route_id=_ss(d.get("route_id")),
            from_node=_ss(d.get("from_node")),
            to_node=_ss(d.get("to_node")),
            distance=max(0.0, _sf(d.get("distance"), 1.0)),
            difficulty=_clamp(_sf(d.get("difficulty"))),
            discovered=bool(d.get("discovered", False)),
            blocked=bool(d.get("blocked", False)),
        )


@dataclass
class RegionState:
    region_id: str = ""
    name: str = ""
    danger_level: float = 0.0
    explored_ratio: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "region_id": self.region_id, "name": self.name,
            "danger_level": self.danger_level,
            "explored_ratio": self.explored_ratio,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "RegionState":
        return cls(
            region_id=_ss(d.get("region_id")), name=_ss(d.get("name")),
            danger_level=_clamp(_sf(d.get("danger_level"))),
            explored_ratio=_clamp(_sf(d.get("explored_ratio"))),
            metadata=dict(d.get("metadata") or {}),
        )


@dataclass
class WorldMapState:
    tick: int = 0
    current_node: str = ""
    regions: List[RegionState] = field(default_factory=list)
    nodes: List[MapNode] = field(default_factory=list)
    routes: List[MapRoute] = field(default_factory=list)
    travel_log: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tick": self.tick, "current_node": self.current_node,
            "regions": [r.to_dict() for r in self.regions],
            "nodes": [n.to_dict() for n in self.nodes],
            "routes": [r.to_dict() for r in self.routes],
            "travel_log": list(self.travel_log),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "WorldMapState":
        return cls(
            tick=_si(d.get("tick")),
            current_node=_ss(d.get("current_node")),
            regions=[RegionState.from_dict(r) for r in (d.get("regions") or [])],
            nodes=[MapNode.from_dict(n) for n in (d.get("nodes") or [])],
            routes=[MapRoute.from_dict(r) for r in (d.get("routes") or [])],
            travel_log=list(d.get("travel_log") or []),
        )


# ---------------------------------------------------------------------------
# 17.1 — Region / node / route model
# ---------------------------------------------------------------------------

class MapManager:
    """Manage map nodes and routes."""

    @staticmethod
    def find_node(state: WorldMapState, node_id: str) -> Optional[MapNode]:
        for n in state.nodes:
            if n.node_id == node_id:
                return n
        return None

    @staticmethod
    def find_route(state: WorldMapState, from_node: str, to_node: str) -> Optional[MapRoute]:
        for r in state.routes:
            if (r.from_node == from_node and r.to_node == to_node) or \
               (r.from_node == to_node and r.to_node == from_node):
                return r
        return None

    @staticmethod
    def get_connected_nodes(state: WorldMapState, node_id: str) -> List[str]:
        connected: List[str] = []
        for r in state.routes:
            if r.blocked:
                continue
            if r.from_node == node_id:
                connected.append(r.to_node)
            elif r.to_node == node_id:
                connected.append(r.from_node)
        return sorted(connected)

    @staticmethod
    def get_region_nodes(state: WorldMapState, region_id: str) -> List[MapNode]:
        return [n for n in state.nodes if n.region_id == region_id]


# ---------------------------------------------------------------------------
# 17.2 — Travel resolution loop
# ---------------------------------------------------------------------------

class TravelResolver:
    """Resolve travel between nodes."""

    @staticmethod
    def attempt_travel(state: WorldMapState, destination: str,
                       tick: int) -> Dict[str, Any]:
        route = MapManager.find_route(state, state.current_node, destination)
        if route is None:
            return {"success": False, "reason": "no route to destination"}
        if route.blocked:
            return {"success": False, "reason": "route is blocked"}

        dest_node = MapManager.find_node(state, destination)
        if dest_node is None:
            return {"success": False, "reason": "destination not found"}

        # Travel succeeds
        previous = state.current_node
        state.current_node = destination
        route.discovered = True
        dest_node.discovered = True

        log_entry = {
            "from": previous, "to": destination,
            "tick": tick, "distance": route.distance,
        }
        state.travel_log.append(log_entry)
        if len(state.travel_log) > MAX_TRAVEL_LOG:
            state.travel_log = state.travel_log[-MAX_TRAVEL_LOG:]

        # Update region exploration
        if dest_node.region_id:
            for reg in state.regions:
                if reg.region_id == dest_node.region_id:
                    region_nodes = MapManager.get_region_nodes(state, reg.region_id)
                    if region_nodes:
                        discovered = len([n for n in region_nodes if n.discovered])
                        reg.explored_ratio = _clamp(discovered / len(region_nodes))

        return {"success": True, "from": previous, "to": destination,
                "distance": route.distance}


# ---------------------------------------------------------------------------
# 17.3 — Discovery / fog-of-war / landmarks
# ---------------------------------------------------------------------------

class DiscoverySystem:
    """Manage fog-of-war and landmark discovery."""

    @staticmethod
    def discover_node(state: WorldMapState, node_id: str) -> Dict[str, Any]:
        node = MapManager.find_node(state, node_id)
        if node is None:
            return {"success": False, "reason": "node not found"}
        if node.discovered:
            return {"success": True, "already_discovered": True}
        node.discovered = True
        return {"success": True, "node_id": node_id, "name": node.name}

    @staticmethod
    def get_discovered_nodes(state: WorldMapState) -> List[MapNode]:
        return [n for n in state.nodes if n.discovered]

    @staticmethod
    def get_undiscovered_adjacent(state: WorldMapState,
                                  node_id: str) -> List[str]:
        connected = MapManager.get_connected_nodes(state, node_id)
        return [nid for nid in connected
                if any(n.node_id == nid and not n.discovered for n in state.nodes)]


# ---------------------------------------------------------------------------
# 17.4 — Travel encounters / ambient events
# ---------------------------------------------------------------------------

class TravelEventGenerator:
    """Generate events during travel."""

    EVENT_TEMPLATES: List[Dict[str, Any]] = [
        {"type": "ambush", "danger": 0.7, "description": "Bandits block the road"},
        {"type": "discovery", "danger": 0.0, "description": "An old shrine is spotted"},
        {"type": "weather", "danger": 0.2, "description": "A storm rolls in"},
        {"type": "merchant", "danger": 0.0, "description": "A traveling merchant appears"},
        {"type": "wildlife", "danger": 0.3, "description": "Wild animals are nearby"},
    ]

    @classmethod
    def generate_travel_event(cls, route: MapRoute,
                              region_danger: float = 0.0) -> Optional[Dict[str, Any]]:
        # Deterministic: event if difficulty + danger exceeds threshold
        combined = route.difficulty + region_danger
        if combined < 0.3:
            return None
        # Select event based on combined score
        idx = int(combined * 10) % len(cls.EVENT_TEMPLATES)
        return dict(cls.EVENT_TEMPLATES[idx])


# ---------------------------------------------------------------------------
# 17.5 — Companion travel behaviour
# ---------------------------------------------------------------------------

class CompanionTravelBehavior:
    """Companion actions during travel."""

    @staticmethod
    def choose_travel_action(companion_id: str, route: MapRoute,
                             companion_role: str = "guard") -> Dict[str, Any]:
        if companion_role == "scout":
            return {"action": "scout_ahead", "companion_id": companion_id,
                    "benefit": "reveals undiscovered nodes"}
        elif companion_role == "guard":
            return {"action": "guard_rear", "companion_id": companion_id,
                    "benefit": "reduces ambush chance"}
        elif companion_role == "navigator":
            return {"action": "navigate", "companion_id": companion_id,
                    "benefit": "reduces travel time"}
        return {"action": "follow", "companion_id": companion_id, "benefit": "none"}


# ---------------------------------------------------------------------------
# 17.6 — Map UI / route presentation
# ---------------------------------------------------------------------------

class MapPresenter:
    """Format map state for UI."""

    @staticmethod
    def present_map(state: WorldMapState) -> Dict[str, Any]:
        return {
            "current_node": state.current_node,
            "discovered_nodes": [n.to_dict() for n in state.nodes if n.discovered],
            "discovered_routes": [r.to_dict() for r in state.routes if r.discovered],
            "regions": [r.to_dict() for r in state.regions],
            "available_destinations": MapManager.get_connected_nodes(state, state.current_node),
        }


# ---------------------------------------------------------------------------
# 17.7 — Travel analytics / inspector
# ---------------------------------------------------------------------------

class TravelAnalytics:
    """Analytics for travel."""

    @staticmethod
    def get_statistics(state: WorldMapState) -> Dict[str, Any]:
        total_nodes = len(state.nodes)
        discovered = len([n for n in state.nodes if n.discovered])
        return {
            "total_nodes": total_nodes,
            "discovered_nodes": discovered,
            "discovery_ratio": (discovered / total_nodes) if total_nodes > 0 else 0.0,
            "total_routes": len(state.routes),
            "discovered_routes": len([r for r in state.routes if r.discovered]),
            "travel_log_entries": len(state.travel_log),
            "regions": len(state.regions),
        }


# ---------------------------------------------------------------------------
# 17.8 — Travel determinism / bounded-state fix pass
# ---------------------------------------------------------------------------

class TravelDeterminismValidator:
    @staticmethod
    def validate_determinism(s1: WorldMapState, s2: WorldMapState) -> bool:
        return s1.to_dict() == s2.to_dict()

    @staticmethod
    def validate_bounds(state: WorldMapState) -> List[str]:
        violations: List[str] = []
        if len(state.nodes) > MAX_LANDMARKS:
            violations.append(f"nodes exceed max ({len(state.nodes)} > {MAX_LANDMARKS})")
        if len(state.routes) > MAX_ROUTES:
            violations.append(f"routes exceed max ({len(state.routes)} > {MAX_ROUTES})")
        if len(state.regions) > MAX_REGIONS:
            violations.append(f"regions exceed max ({len(state.regions)} > {MAX_REGIONS})")
        if len(state.travel_log) > MAX_TRAVEL_LOG:
            violations.append(f"travel_log exceeds max ({len(state.travel_log)} > {MAX_TRAVEL_LOG})")
        return violations

    @staticmethod
    def normalize_state(state: WorldMapState) -> WorldMapState:
        nodes = list(state.nodes)[:MAX_LANDMARKS]
        routes = list(state.routes)[:MAX_ROUTES]
        regions = list(state.regions)[:MAX_REGIONS]
        log = list(state.travel_log)
        if len(log) > MAX_TRAVEL_LOG:
            log = log[-MAX_TRAVEL_LOG:]
        for r in regions:
            r.danger_level = _clamp(r.danger_level)
            r.explored_ratio = _clamp(r.explored_ratio)
        return WorldMapState(
            tick=state.tick, current_node=state.current_node,
            regions=regions, nodes=nodes, routes=routes,
            travel_log=log,
        )
