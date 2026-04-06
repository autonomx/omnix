"""Phase 13 — Social simulation 2.0.

Reputation graph deepening, relationship trust, alliance formation,
betrayal propagation, group decisions, rumor spread/mutation/decay,
social pressure, inspector, and determinism validation.
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

MAX_REPUTATION_EDGES = 200
MAX_RELATIONSHIPS = 100
MAX_ALLIANCES = 32
MAX_RUMORS = 64
MAX_GROUP_MEMBERS = 20
TRUST_RANGE = (-1.0, 1.0)

# ---------------------------------------------------------------------------
# 13.0 — Reputation graph foundations
# ---------------------------------------------------------------------------

@dataclass
class ReputationEdge:
    source_id: str = ""
    target_id: str = ""
    trust: float = 0.0
    fear: float = 0.0
    respect: float = 0.0
    hostility: float = 0.0
    last_tick: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_id": self.source_id, "target_id": self.target_id,
            "trust": self.trust, "fear": self.fear,
            "respect": self.respect, "hostility": self.hostility,
            "last_tick": self.last_tick,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ReputationEdge":
        return cls(
            source_id=_ss(d.get("source_id")),
            target_id=_ss(d.get("target_id")),
            trust=_clamp(_sf(d.get("trust")), *TRUST_RANGE),
            fear=_clamp(_sf(d.get("fear")), *TRUST_RANGE),
            respect=_clamp(_sf(d.get("respect")), *TRUST_RANGE),
            hostility=_clamp(_sf(d.get("hostility")), *TRUST_RANGE),
            last_tick=_si(d.get("last_tick")),
        )


@dataclass
class AllianceRecord:
    alliance_id: str = ""
    faction_a: str = ""
    faction_b: str = ""
    strength: float = 0.5
    status: str = "neutral"
    formed_tick: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "alliance_id": self.alliance_id, "faction_a": self.faction_a,
            "faction_b": self.faction_b, "strength": self.strength,
            "status": self.status, "formed_tick": self.formed_tick,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "AllianceRecord":
        return cls(
            alliance_id=_ss(d.get("alliance_id")),
            faction_a=_ss(d.get("faction_a")),
            faction_b=_ss(d.get("faction_b")),
            strength=_clamp(_sf(d.get("strength"), 0.5)),
            status=_ss(d.get("status"), "neutral"),
            formed_tick=_si(d.get("formed_tick")),
        )


@dataclass
class RumorRecord:
    rumor_id: str = ""
    content: str = ""
    source_id: str = ""
    credibility: float = 0.5
    spread_count: int = 0
    mutation_count: int = 0
    created_tick: int = 0
    last_spread_tick: int = 0
    active: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rumor_id": self.rumor_id, "content": self.content,
            "source_id": self.source_id, "credibility": self.credibility,
            "spread_count": self.spread_count, "mutation_count": self.mutation_count,
            "created_tick": self.created_tick, "last_spread_tick": self.last_spread_tick,
            "active": self.active,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "RumorRecord":
        return cls(
            rumor_id=_ss(d.get("rumor_id")),
            content=_ss(d.get("content")),
            source_id=_ss(d.get("source_id")),
            credibility=_clamp(_sf(d.get("credibility"), 0.5)),
            spread_count=_si(d.get("spread_count")),
            mutation_count=_si(d.get("mutation_count")),
            created_tick=_si(d.get("created_tick")),
            last_spread_tick=_si(d.get("last_spread_tick")),
            active=bool(d.get("active", True)),
        )


@dataclass
class SocialSimState:
    tick: int = 0
    reputation_edges: List[ReputationEdge] = field(default_factory=list)
    alliances: List[AllianceRecord] = field(default_factory=list)
    rumors: List[RumorRecord] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tick": self.tick,
            "reputation_edges": [e.to_dict() for e in self.reputation_edges],
            "alliances": [a.to_dict() for a in self.alliances],
            "rumors": [r.to_dict() for r in self.rumors],
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SocialSimState":
        return cls(
            tick=_si(d.get("tick")),
            reputation_edges=[ReputationEdge.from_dict(e) for e in (d.get("reputation_edges") or [])],
            alliances=[AllianceRecord.from_dict(a) for a in (d.get("alliances") or [])],
            rumors=[RumorRecord.from_dict(r) for r in (d.get("rumors") or [])],
        )


# ---------------------------------------------------------------------------
# 13.1 — Relationship / trust deepening
# ---------------------------------------------------------------------------

class RelationshipDeepener:
    """Deepen trust/fear/respect based on events."""

    EVENT_DELTAS: Dict[str, Dict[str, float]] = {
        "help": {"trust": 0.15, "respect": 0.05, "hostility": -0.05},
        "attack": {"trust": -0.2, "hostility": 0.25, "fear": 0.1},
        "betray": {"trust": -0.4, "hostility": 0.3, "fear": 0.15, "respect": -0.1},
        "gift": {"trust": 0.1, "respect": 0.05},
        "dialogue": {"trust": 0.03, "respect": 0.02},
        "trade": {"trust": 0.08, "respect": 0.03},
        "threaten": {"fear": 0.2, "hostility": 0.1, "trust": -0.1},
        "protect": {"trust": 0.2, "respect": 0.1, "fear": -0.05},
    }

    @classmethod
    def apply_event(cls, edge: ReputationEdge, event_type: str, tick: int) -> ReputationEdge:
        deltas = cls.EVENT_DELTAS.get(event_type, {})
        edge.trust = _clamp(edge.trust + _sf(deltas.get("trust")), *TRUST_RANGE)
        edge.fear = _clamp(edge.fear + _sf(deltas.get("fear")), *TRUST_RANGE)
        edge.respect = _clamp(edge.respect + _sf(deltas.get("respect")), *TRUST_RANGE)
        edge.hostility = _clamp(edge.hostility + _sf(deltas.get("hostility")), *TRUST_RANGE)
        edge.last_tick = tick
        return edge

    @staticmethod
    def decay_relationships(edges: List[ReputationEdge], current_tick: int,
                            decay_rate: float = 0.98) -> List[ReputationEdge]:
        for e in edges:
            age = current_tick - e.last_tick
            if age > 0:
                factor = decay_rate ** age
                e.trust *= factor
                e.fear *= factor
                e.respect *= factor
                e.hostility *= factor
                e.trust = _clamp(e.trust, *TRUST_RANGE)
                e.fear = _clamp(e.fear, *TRUST_RANGE)
                e.respect = _clamp(e.respect, *TRUST_RANGE)
                e.hostility = _clamp(e.hostility, *TRUST_RANGE)
        return edges


# ---------------------------------------------------------------------------
# 13.2 — Alliance formation / maintenance
# ---------------------------------------------------------------------------

class AllianceManager:
    """Form, strengthen, and dissolve alliances."""

    _counter = 0

    @classmethod
    def _next_id(cls) -> str:
        cls._counter += 1
        return f"alliance_{cls._counter}"

    @classmethod
    def form_alliance(cls, faction_a: str, faction_b: str, tick: int,
                      strength: float = 0.5) -> AllianceRecord:
        return AllianceRecord(
            alliance_id=cls._next_id(),
            faction_a=faction_a, faction_b=faction_b,
            strength=_clamp(strength), status="allied",
            formed_tick=tick,
        )

    @staticmethod
    def strengthen(alliance: AllianceRecord, amount: float = 0.1) -> AllianceRecord:
        alliance.strength = _clamp(alliance.strength + amount)
        if alliance.strength >= 0.7:
            alliance.status = "allied"
        return alliance

    @staticmethod
    def weaken(alliance: AllianceRecord, amount: float = 0.1) -> AllianceRecord:
        alliance.strength = _clamp(alliance.strength - amount)
        if alliance.strength <= 0.2:
            alliance.status = "dissolved"
        elif alliance.strength <= 0.4:
            alliance.status = "tense"
        return alliance

    @staticmethod
    def dissolve(alliance: AllianceRecord) -> AllianceRecord:
        alliance.strength = 0.0
        alliance.status = "dissolved"
        return alliance


# ---------------------------------------------------------------------------
# 13.3 — Betrayal / loyalty propagation
# ---------------------------------------------------------------------------

class BetrayalPropagator:
    """Propagate betrayal effects through social networks."""

    @staticmethod
    def propagate_betrayal(
        betrayer_id: str,
        victim_id: str,
        edges: List[ReputationEdge],
        tick: int,
    ) -> List[Dict[str, Any]]:
        events: List[Dict[str, Any]] = []
        # Direct effect
        events.append({
            "type": "trust_collapse",
            "source": victim_id,
            "target": betrayer_id,
            "tick": tick,
        })
        # Propagate to victim's allies
        for e in edges:
            if e.source_id == victim_id and e.trust > 0.3:
                events.append({
                    "type": "social_shock",
                    "source": e.target_id,
                    "target": betrayer_id,
                    "severity": _clamp(e.trust * 0.5),
                    "tick": tick,
                })
            if e.target_id == victim_id and e.trust > 0.3:
                events.append({
                    "type": "social_shock",
                    "source": e.source_id,
                    "target": betrayer_id,
                    "severity": _clamp(e.trust * 0.5),
                    "tick": tick,
                })
        return events


# ---------------------------------------------------------------------------
# 13.4 — Group decision making
# ---------------------------------------------------------------------------

class GroupDecisionEngine:
    """Aggregate individual beliefs into group stance."""

    @staticmethod
    def compute_group_stance(
        member_edges: List[ReputationEdge],
        target_id: str,
    ) -> Dict[str, Any]:
        relevant = [e for e in member_edges if e.target_id == target_id]
        if not relevant:
            return {"stance": "neutral", "confidence": 0.0, "voter_count": 0}

        avg_trust = sum(e.trust for e in relevant) / len(relevant)
        avg_hostility = sum(e.hostility for e in relevant) / len(relevant)
        avg_fear = sum(e.fear for e in relevant) / len(relevant)

        if avg_hostility > 0.3:
            stance = "oppose"
        elif avg_fear > 0.3:
            stance = "fear"
        elif avg_trust > 0.3:
            stance = "support"
        else:
            stance = "watch"

        confidence = _clamp(abs(avg_trust) + abs(avg_hostility))
        return {
            "stance": stance,
            "confidence": confidence,
            "voter_count": len(relevant),
            "avg_trust": round(avg_trust, 3),
            "avg_hostility": round(avg_hostility, 3),
        }


# ---------------------------------------------------------------------------
# 13.5 — Rumor spread / mutation / decay
# ---------------------------------------------------------------------------

class RumorEngine:
    """Spread, mutate, and decay rumors."""

    _counter = 0

    @classmethod
    def _next_id(cls) -> str:
        cls._counter += 1
        return f"rumor_{cls._counter}"

    @classmethod
    def create_rumor(cls, content: str, source_id: str, tick: int,
                     credibility: float = 0.5) -> RumorRecord:
        return RumorRecord(
            rumor_id=cls._next_id(), content=content,
            source_id=source_id, credibility=_clamp(credibility),
            created_tick=tick, last_spread_tick=tick, active=True,
        )

    @staticmethod
    def spread_rumor(rumor: RumorRecord, tick: int) -> RumorRecord:
        rumor.spread_count += 1
        rumor.last_spread_tick = tick
        # Credibility drops slightly per spread
        rumor.credibility = _clamp(rumor.credibility * 0.95)
        return rumor

    @staticmethod
    def mutate_rumor(rumor: RumorRecord, mutation: str) -> RumorRecord:
        rumor.content = mutation
        rumor.mutation_count += 1
        rumor.credibility = _clamp(rumor.credibility * 0.85)
        return rumor

    @staticmethod
    def decay_rumors(rumors: List[RumorRecord], current_tick: int,
                     decay_rate: float = 0.95) -> List[RumorRecord]:
        for r in rumors:
            age = current_tick - r.last_spread_tick
            if age > 0:
                r.credibility = _clamp(r.credibility * (decay_rate ** age))
            if r.credibility < 0.05:
                r.active = False
        return rumors

    @staticmethod
    def get_active_rumors(rumors: List[RumorRecord]) -> List[RumorRecord]:
        return [r for r in rumors if r.active and r.credibility > 0.05]


# ---------------------------------------------------------------------------
# 13.6 — Social pressure on encounters / dialogue
# ---------------------------------------------------------------------------

class SocialPressureEngine:
    """Compute social pressure that affects encounters and dialogue."""

    @staticmethod
    def compute_encounter_pressure(
        actor_id: str,
        opponent_id: str,
        edges: List[ReputationEdge],
        alliances: List[AllianceRecord],
    ) -> Dict[str, Any]:
        result = {
            "aggression_modifier": 0.0,
            "retreat_modifier": 0.0,
            "negotiate_modifier": 0.0,
            "social_tags": [],
        }
        for e in edges:
            if e.source_id == actor_id and e.target_id == opponent_id:
                result["aggression_modifier"] += e.hostility * 0.3
                result["retreat_modifier"] += e.fear * 0.3
                result["negotiate_modifier"] += e.trust * 0.2
                if e.hostility > 0.5:
                    result["social_tags"].append("grudge")
                if e.trust > 0.5:
                    result["social_tags"].append("former_ally")

        result["aggression_modifier"] = _clamp(result["aggression_modifier"], -1.0, 1.0)
        result["retreat_modifier"] = _clamp(result["retreat_modifier"], -1.0, 1.0)
        result["negotiate_modifier"] = _clamp(result["negotiate_modifier"], -1.0, 1.0)
        result["social_tags"] = sorted(set(result["social_tags"]))
        return result

    @staticmethod
    def compute_dialogue_pressure(
        speaker_id: str,
        listener_id: str,
        edges: List[ReputationEdge],
    ) -> Dict[str, Any]:
        result = {"tone_modifier": "neutral", "openness": 0.5, "tags": []}
        for e in edges:
            if e.source_id == speaker_id and e.target_id == listener_id:
                if e.trust > 0.3:
                    result["tone_modifier"] = "friendly"
                    result["openness"] = _clamp(0.5 + e.trust * 0.3)
                    result["tags"].append("trusted")
                elif e.hostility > 0.3:
                    result["tone_modifier"] = "hostile"
                    result["openness"] = _clamp(0.5 - e.hostility * 0.3)
                    result["tags"].append("hostile")
                elif e.fear > 0.3:
                    result["tone_modifier"] = "cautious"
                    result["openness"] = _clamp(0.5 - e.fear * 0.2)
                    result["tags"].append("fearful")
        result["tags"] = sorted(set(result["tags"]))
        return result


# ---------------------------------------------------------------------------
# 13.7 — Social inspector / graph views
# ---------------------------------------------------------------------------

class SocialInspector:
    """Debug inspection for social state."""

    @staticmethod
    def inspect_state(state: SocialSimState) -> Dict[str, Any]:
        return {
            "tick": state.tick,
            "edge_count": len(state.reputation_edges),
            "alliance_count": len(state.alliances),
            "rumor_count": len(state.rumors),
            "active_rumor_count": len([r for r in state.rumors if r.active]),
        }

    @staticmethod
    def inspect_entity_relationships(
        state: SocialSimState, entity_id: str,
    ) -> Dict[str, Any]:
        outgoing = [e for e in state.reputation_edges if e.source_id == entity_id]
        incoming = [e for e in state.reputation_edges if e.target_id == entity_id]
        return {
            "entity_id": entity_id,
            "outgoing_count": len(outgoing),
            "incoming_count": len(incoming),
            "allies": [e.target_id for e in outgoing if e.trust > 0.3],
            "enemies": [e.target_id for e in outgoing if e.hostility > 0.3],
        }

    @staticmethod
    def get_social_graph(state: SocialSimState) -> Dict[str, Any]:
        nodes = set()
        for e in state.reputation_edges:
            nodes.add(e.source_id)
            nodes.add(e.target_id)
        return {
            "node_count": len(nodes),
            "edge_count": len(state.reputation_edges),
            "nodes": sorted(nodes),
        }


# ---------------------------------------------------------------------------
# 13.8 — Social determinism / bounded-state fix pass
# ---------------------------------------------------------------------------

class SocialDeterminismValidator:
    @staticmethod
    def validate_determinism(s1: SocialSimState, s2: SocialSimState) -> bool:
        return s1.to_dict() == s2.to_dict()

    @staticmethod
    def validate_bounds(state: SocialSimState) -> List[str]:
        violations: List[str] = []
        if len(state.reputation_edges) > MAX_REPUTATION_EDGES:
            violations.append(f"edges exceed max ({len(state.reputation_edges)} > {MAX_REPUTATION_EDGES})")
        if len(state.alliances) > MAX_ALLIANCES:
            violations.append(f"alliances exceed max ({len(state.alliances)} > {MAX_ALLIANCES})")
        if len(state.rumors) > MAX_RUMORS:
            violations.append(f"rumors exceed max ({len(state.rumors)} > {MAX_RUMORS})")
        for e in state.reputation_edges:
            for attr in ("trust", "fear", "respect", "hostility"):
                v = getattr(e, attr)
                if v < -1.0 or v > 1.0:
                    violations.append(f"edge {e.source_id}->{e.target_id} {attr} out of range: {v}")
                    break
        return violations

    @staticmethod
    def normalize_state(state: SocialSimState) -> SocialSimState:
        edges = list(state.reputation_edges)
        if len(edges) > MAX_REPUTATION_EDGES:
            edges.sort(key=lambda e: abs(e.trust) + abs(e.hostility), reverse=True)
            edges = edges[:MAX_REPUTATION_EDGES]
        for e in edges:
            e.trust = _clamp(e.trust, *TRUST_RANGE)
            e.fear = _clamp(e.fear, *TRUST_RANGE)
            e.respect = _clamp(e.respect, *TRUST_RANGE)
            e.hostility = _clamp(e.hostility, *TRUST_RANGE)

        alliances = list(state.alliances)
        if len(alliances) > MAX_ALLIANCES:
            alliances = alliances[:MAX_ALLIANCES]

        rumors = list(state.rumors)
        if len(rumors) > MAX_RUMORS:
            rumors.sort(key=lambda r: r.credibility, reverse=True)
            rumors = rumors[:MAX_RUMORS]

        return SocialSimState(
            tick=state.tick, reputation_edges=edges,
            alliances=alliances, rumors=rumors,
        )
