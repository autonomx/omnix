"""Phase 14 — Story director system integration.

Director state, tension/pacing, arc/beat tracking, scene biasing,
director influence on dialogue and quests, inspector, determinism.
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

MAX_ARCS = 10
MAX_BEATS_PER_ARC = 20
MAX_SCENE_BIASES = 10
ARC_PHASES = ("setup", "rising", "climax", "falling", "resolution")

# ---------------------------------------------------------------------------
# 14.0 — Director state foundations
# ---------------------------------------------------------------------------

@dataclass
class StoryBeat:
    beat_id: str = ""
    arc_id: str = ""
    description: str = ""
    beat_type: str = "event"  # event, revelation, confrontation, resolution
    status: str = "pending"   # pending, active, completed, skipped
    tick_triggered: int = 0
    tension_delta: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "beat_id": self.beat_id, "arc_id": self.arc_id,
            "description": self.description, "beat_type": self.beat_type,
            "status": self.status, "tick_triggered": self.tick_triggered,
            "tension_delta": self.tension_delta,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "StoryBeat":
        return cls(
            beat_id=_ss(d.get("beat_id")), arc_id=_ss(d.get("arc_id")),
            description=_ss(d.get("description")),
            beat_type=_ss(d.get("beat_type"), "event"),
            status=_ss(d.get("status"), "pending"),
            tick_triggered=_si(d.get("tick_triggered")),
            tension_delta=_sf(d.get("tension_delta")),
        )


@dataclass
class StoryArcState:
    arc_id: str = ""
    title: str = ""
    phase: str = "setup"
    tension: float = 0.0
    priority: float = 0.5
    beats: List[StoryBeat] = field(default_factory=list)
    focus_entities: List[str] = field(default_factory=list)
    status: str = "active"  # active, resolved, abandoned

    def to_dict(self) -> Dict[str, Any]:
        return {
            "arc_id": self.arc_id, "title": self.title,
            "phase": self.phase, "tension": self.tension,
            "priority": self.priority,
            "beats": [b.to_dict() for b in self.beats],
            "focus_entities": list(self.focus_entities),
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "StoryArcState":
        return cls(
            arc_id=_ss(d.get("arc_id")), title=_ss(d.get("title")),
            phase=_ss(d.get("phase"), "setup"),
            tension=_clamp(_sf(d.get("tension"))),
            priority=_clamp(_sf(d.get("priority"), 0.5)),
            beats=[StoryBeat.from_dict(b) for b in (d.get("beats") or [])],
            focus_entities=list(d.get("focus_entities") or []),
            status=_ss(d.get("status"), "active"),
        )


@dataclass
class DirectorState:
    tick: int = 0
    global_tension: float = 0.3
    pacing_target: float = 0.5  # desired tension level
    arcs: List[StoryArcState] = field(default_factory=list)
    scene_biases: List[Dict[str, Any]] = field(default_factory=list)
    last_beat_tick: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tick": self.tick, "global_tension": self.global_tension,
            "pacing_target": self.pacing_target,
            "arcs": [a.to_dict() for a in self.arcs],
            "scene_biases": list(self.scene_biases),
            "last_beat_tick": self.last_beat_tick,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "DirectorState":
        return cls(
            tick=_si(d.get("tick")),
            global_tension=_clamp(_sf(d.get("global_tension"), 0.3)),
            pacing_target=_clamp(_sf(d.get("pacing_target"), 0.5)),
            arcs=[StoryArcState.from_dict(a) for a in (d.get("arcs") or [])],
            scene_biases=list(d.get("scene_biases") or []),
            last_beat_tick=_si(d.get("last_beat_tick")),
        )


# ---------------------------------------------------------------------------
# 14.1 — Tension / pacing controls
# ---------------------------------------------------------------------------

class TensionPacingController:
    """Manage global tension and pacing."""

    @staticmethod
    def update_tension(state: DirectorState, events: List[Dict[str, Any]],
                       tick: int) -> DirectorState:
        delta = 0.0
        for evt in events:
            etype = _ss(evt.get("type"))
            if etype in ("attack", "betrayal", "ambush", "confrontation"):
                delta += 0.1
            elif etype in ("resolution", "peace", "gift", "rest"):
                delta -= 0.1
            elif etype in ("revelation", "twist"):
                delta += 0.15
        # Drift toward pacing target
        drift = (state.pacing_target - state.global_tension) * 0.05
        state.global_tension = _clamp(state.global_tension + delta + drift)
        state.tick = tick
        return state

    @staticmethod
    def set_pacing_target(state: DirectorState, target: float) -> DirectorState:
        state.pacing_target = _clamp(target)
        return state

    @staticmethod
    def get_tension_band(tension: float) -> str:
        if tension < 0.2:
            return "calm"
        elif tension < 0.4:
            return "low"
        elif tension < 0.6:
            return "medium"
        elif tension < 0.8:
            return "high"
        else:
            return "critical"


# ---------------------------------------------------------------------------
# 14.2 — Arc / beat tracking
# ---------------------------------------------------------------------------

class ArcBeatTracker:
    """Track story arc progression and beats."""

    @staticmethod
    def advance_arc_phase(arc: StoryArcState) -> StoryArcState:
        phases = list(ARC_PHASES)
        idx = phases.index(arc.phase) if arc.phase in phases else 0
        if idx < len(phases) - 1:
            arc.phase = phases[idx + 1]
        else:
            arc.status = "resolved"
        return arc

    @staticmethod
    def trigger_beat(arc: StoryArcState, beat_id: str, tick: int) -> StoryArcState:
        for b in arc.beats:
            if b.beat_id == beat_id and b.status == "pending":
                b.status = "completed"
                b.tick_triggered = tick
                arc.tension = _clamp(arc.tension + b.tension_delta)
                break
        return arc

    @staticmethod
    def get_pending_beats(arc: StoryArcState) -> List[StoryBeat]:
        return [b for b in arc.beats if b.status == "pending"]

    @staticmethod
    def get_next_beat(arc: StoryArcState) -> Optional[StoryBeat]:
        pending = [b for b in arc.beats if b.status == "pending"]
        return pending[0] if pending else None


# ---------------------------------------------------------------------------
# 14.3 — Scene biasing without simulation override
# ---------------------------------------------------------------------------

class SceneBiasEngine:
    """Bias scene selection without overriding simulation truth."""

    @staticmethod
    def compute_scene_bias(state: DirectorState) -> Dict[str, Any]:
        bias: Dict[str, Any] = {
            "preferred_mood": "neutral",
            "entity_focus": [],
            "tension_band": TensionPacingController.get_tension_band(state.global_tension),
            "arc_themes": [],
        }
        active_arcs = [a for a in state.arcs if a.status == "active"]
        if active_arcs:
            top = max(active_arcs, key=lambda a: a.priority)
            bias["entity_focus"] = list(top.focus_entities[:5])
            bias["arc_themes"].append(top.title)

        if state.global_tension > 0.6:
            bias["preferred_mood"] = "tense"
        elif state.global_tension < 0.3:
            bias["preferred_mood"] = "relaxed"

        return bias

    @staticmethod
    def add_scene_bias(state: DirectorState, bias: Dict[str, Any]) -> DirectorState:
        state.scene_biases.append(bias)
        if len(state.scene_biases) > MAX_SCENE_BIASES:
            state.scene_biases = state.scene_biases[-MAX_SCENE_BIASES:]
        return state


# ---------------------------------------------------------------------------
# 14.4 — Director influence on runtime dialogue
# ---------------------------------------------------------------------------

class DirectorDialogueInfluence:
    """Influence dialogue based on director state."""

    @staticmethod
    def get_dialogue_directives(
        state: DirectorState,
        speaker_id: str,
        listener_id: str,
    ) -> Dict[str, Any]:
        directives: Dict[str, Any] = {
            "tone_suggestion": "neutral",
            "reveal_hints": [],
            "tension_level": state.global_tension,
            "arc_context": [],
        }
        for arc in state.arcs:
            if arc.status != "active":
                continue
            if speaker_id in arc.focus_entities or listener_id in arc.focus_entities:
                directives["arc_context"].append(arc.title)
                pending = ArcBeatTracker.get_next_beat(arc)
                if pending and pending.beat_type == "revelation":
                    directives["reveal_hints"].append(pending.description)

        if state.global_tension > 0.6:
            directives["tone_suggestion"] = "urgent"
        elif state.global_tension < 0.3:
            directives["tone_suggestion"] = "relaxed"

        return directives


# ---------------------------------------------------------------------------
# 14.5 — Director influence on quest / objective flow
# ---------------------------------------------------------------------------

class DirectorQuestInfluence:
    """Influence quest progression based on director state."""

    @staticmethod
    def get_quest_directives(
        state: DirectorState,
        active_quests: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        directives: Dict[str, Any] = {
            "urgency_modifier": 0.0,
            "suggested_priority_quest": None,
            "delay_quests": [],
        }
        if state.global_tension > 0.7:
            directives["urgency_modifier"] = 0.3
        elif state.global_tension < 0.3:
            directives["urgency_modifier"] = -0.2

        # Suggest quest tied to highest-priority arc
        active_arcs = [a for a in state.arcs if a.status == "active"]
        if active_arcs:
            top_arc = max(active_arcs, key=lambda a: a.priority)
            for q in active_quests:
                entities = q.get("entities") or []
                if any(e in top_arc.focus_entities for e in entities):
                    directives["suggested_priority_quest"] = q.get("quest_id")
                    break

        return directives


# ---------------------------------------------------------------------------
# 14.6 — Director inspector / tuning tools
# ---------------------------------------------------------------------------

class DirectorInspector:
    """Debug inspection for director state."""

    @staticmethod
    def inspect_state(state: DirectorState) -> Dict[str, Any]:
        return {
            "tick": state.tick,
            "global_tension": state.global_tension,
            "pacing_target": state.pacing_target,
            "tension_band": TensionPacingController.get_tension_band(state.global_tension),
            "arc_count": len(state.arcs),
            "active_arc_count": len([a for a in state.arcs if a.status == "active"]),
            "scene_bias_count": len(state.scene_biases),
        }

    @staticmethod
    def inspect_arc(arc: StoryArcState) -> Dict[str, Any]:
        return {
            "arc_id": arc.arc_id, "title": arc.title,
            "phase": arc.phase, "tension": arc.tension,
            "status": arc.status,
            "beat_count": len(arc.beats),
            "pending_beats": len([b for b in arc.beats if b.status == "pending"]),
            "completed_beats": len([b for b in arc.beats if b.status == "completed"]),
        }

    @staticmethod
    def get_director_statistics(state: DirectorState) -> Dict[str, Any]:
        total_beats = sum(len(a.beats) for a in state.arcs)
        completed_beats = sum(
            len([b for b in a.beats if b.status == "completed"]) for a in state.arcs
        )
        return {
            "arc_count": len(state.arcs),
            "total_beats": total_beats,
            "completed_beats": completed_beats,
            "completion_ratio": (completed_beats / total_beats) if total_beats > 0 else 0.0,
        }


# ---------------------------------------------------------------------------
# 14.7 — Director determinism / bounded-state fix pass
# ---------------------------------------------------------------------------

class DirectorDeterminismValidator:
    @staticmethod
    def validate_determinism(s1: DirectorState, s2: DirectorState) -> bool:
        return s1.to_dict() == s2.to_dict()

    @staticmethod
    def validate_bounds(state: DirectorState) -> List[str]:
        violations: List[str] = []
        if len(state.arcs) > MAX_ARCS:
            violations.append(f"arcs exceed max ({len(state.arcs)} > {MAX_ARCS})")
        if state.global_tension < 0.0 or state.global_tension > 1.0:
            violations.append(f"global_tension out of range: {state.global_tension}")
        for arc in state.arcs:
            if len(arc.beats) > MAX_BEATS_PER_ARC:
                violations.append(f"arc {arc.arc_id} beats exceed max ({len(arc.beats)} > {MAX_BEATS_PER_ARC})")
            if arc.tension < 0.0 or arc.tension > 1.0:
                violations.append(f"arc {arc.arc_id} tension out of range: {arc.tension}")
        if len(state.scene_biases) > MAX_SCENE_BIASES:
            violations.append(f"scene_biases exceed max ({len(state.scene_biases)} > {MAX_SCENE_BIASES})")
        return violations

    @staticmethod
    def normalize_state(state: DirectorState) -> DirectorState:
        arcs = list(state.arcs)
        if len(arcs) > MAX_ARCS:
            arcs.sort(key=lambda a: a.priority, reverse=True)
            arcs = arcs[:MAX_ARCS]
        for a in arcs:
            a.tension = _clamp(a.tension)
            a.priority = _clamp(a.priority)
            if len(a.beats) > MAX_BEATS_PER_ARC:
                a.beats = a.beats[:MAX_BEATS_PER_ARC]

        biases = list(state.scene_biases)
        if len(biases) > MAX_SCENE_BIASES:
            biases = biases[-MAX_SCENE_BIASES:]

        return DirectorState(
            tick=state.tick,
            global_tension=_clamp(state.global_tension),
            pacing_target=_clamp(state.pacing_target),
            arcs=arcs, scene_biases=biases,
            last_beat_tick=state.last_beat_tick,
        )
