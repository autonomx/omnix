"""Phase 23 — Emergent narrative endgame.

Narrative coherence, theme/motif tracking, callback/payoff system,
arc synthesis, relationship-driven emergence, director convergence,
endgame orchestration, narrative analytics, final coherence.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

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

# Constants
MAX_THEMES = 10
MAX_CALLBACKS = 30
MAX_MOTIFS = 20
MAX_ARC_SYNTHESIS = 5

# ---------------------------------------------------------------------------
# 23.0 — Narrative coherence foundations
# ---------------------------------------------------------------------------

@dataclass
class NarrativeCoherenceState:
    tick: int = 0
    themes: List[Dict[str, Any]] = field(default_factory=list)
    motifs: List[Dict[str, Any]] = field(default_factory=list)
    callbacks: List[Dict[str, Any]] = field(default_factory=list)
    payoffs: List[Dict[str, Any]] = field(default_factory=list)
    arc_syntheses: List[Dict[str, Any]] = field(default_factory=list)
    coherence_score: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tick": self.tick,
            "themes": list(self.themes),
            "motifs": list(self.motifs),
            "callbacks": list(self.callbacks),
            "payoffs": list(self.payoffs),
            "arc_syntheses": list(self.arc_syntheses),
            "coherence_score": self.coherence_score,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "NarrativeCoherenceState":
        return cls(
            tick=_si(d.get("tick")),
            themes=list(d.get("themes") or []),
            motifs=list(d.get("motifs") or []),
            callbacks=list(d.get("callbacks") or []),
            payoffs=list(d.get("payoffs") or []),
            arc_syntheses=list(d.get("arc_syntheses") or []),
            coherence_score=_clamp(_sf(d.get("coherence_score"), 1.0)),
        )


# ---------------------------------------------------------------------------
# 23.1 — Theme / motif tracking
# ---------------------------------------------------------------------------

class ThemeTracker:
    """Track recurring themes and motifs."""

    @staticmethod
    def register_theme(state: NarrativeCoherenceState,
                       theme: str, tick: int) -> Dict[str, Any]:
        entry = {"theme": theme, "first_tick": tick,
                 "occurrences": 1, "active": True}
        for t in state.themes:
            if t.get("theme") == theme:
                t["occurrences"] = t.get("occurrences", 0) + 1
                return {"success": True, "new": False, "occurrences": t["occurrences"]}
        state.themes.append(entry)
        if len(state.themes) > MAX_THEMES:
            state.themes.sort(key=lambda t: t.get("occurrences", 0))
            state.themes = state.themes[-MAX_THEMES:]
        return {"success": True, "new": True, "occurrences": 1}

    @staticmethod
    def register_motif(state: NarrativeCoherenceState,
                       motif: str, entity_id: str, tick: int) -> Dict[str, Any]:
        entry = {"motif": motif, "entity_id": entity_id,
                 "first_tick": tick, "count": 1}
        for m in state.motifs:
            if m.get("motif") == motif and m.get("entity_id") == entity_id:
                m["count"] = m.get("count", 0) + 1
                return {"success": True, "new": False}
        state.motifs.append(entry)
        if len(state.motifs) > MAX_MOTIFS:
            state.motifs.sort(key=lambda m: m.get("count", 0))
            state.motifs = state.motifs[-MAX_MOTIFS:]
        return {"success": True, "new": True}

    @staticmethod
    def get_dominant_themes(state: NarrativeCoherenceState,
                            top_k: int = 3) -> List[Dict[str, Any]]:
        themes = sorted(state.themes, key=lambda t: t.get("occurrences", 0),
                        reverse=True)
        return themes[:top_k]


# ---------------------------------------------------------------------------
# 23.2 — Callback / payoff system
# ---------------------------------------------------------------------------

class CallbackPayoffSystem:
    """Track narrative setups (callbacks) and their payoffs."""

    _counter = 0

    @classmethod
    def _next_id(cls) -> str:
        cls._counter += 1
        return f"callback_{cls._counter}"

    @classmethod
    def register_callback(cls, state: NarrativeCoherenceState,
                          description: str, entity_ids: List[str],
                          tick: int) -> Dict[str, Any]:
        cb_id = cls._next_id()
        entry = {
            "callback_id": cb_id, "description": description,
            "entity_ids": list(entity_ids), "tick": tick,
            "paid_off": False, "payoff_tick": 0,
        }
        state.callbacks.append(entry)
        if len(state.callbacks) > MAX_CALLBACKS:
            # Remove oldest paid-off callbacks first
            paid = [c for c in state.callbacks if c.get("paid_off")]
            unpaid = [c for c in state.callbacks if not c.get("paid_off")]
            state.callbacks = unpaid + paid[-(MAX_CALLBACKS - len(unpaid)):]
        return {"success": True, "callback_id": cb_id}

    @staticmethod
    def trigger_payoff(state: NarrativeCoherenceState,
                       callback_id: str, tick: int,
                       payoff_description: str = "") -> Dict[str, Any]:
        for cb in state.callbacks:
            if cb.get("callback_id") == callback_id and not cb.get("paid_off"):
                cb["paid_off"] = True
                cb["payoff_tick"] = tick
                state.payoffs.append({
                    "callback_id": callback_id,
                    "payoff_description": payoff_description,
                    "tick": tick,
                })
                return {"success": True, "callback_id": callback_id}
        return {"success": False, "reason": "callback not found or already paid off"}

    @staticmethod
    def get_pending_callbacks(state: NarrativeCoherenceState) -> List[Dict[str, Any]]:
        return [c for c in state.callbacks if not c.get("paid_off")]


# ---------------------------------------------------------------------------
# 23.3 — Arc synthesis across long play
# ---------------------------------------------------------------------------

class ArcSynthesizer:
    """Synthesize story arcs across long play sessions."""

    @staticmethod
    def synthesize_arcs(state: NarrativeCoherenceState,
                        completed_arcs: List[Dict[str, Any]],
                        tick: int) -> Dict[str, Any]:
        if len(completed_arcs) < 2:
            return {"success": False, "reason": "need at least 2 completed arcs"}

        common_entities = set()
        for arc in completed_arcs:
            entities = set(arc.get("focus_entities", []))
            if not common_entities:
                common_entities = entities
            else:
                common_entities &= entities

        themes = [t.get("theme") for t in state.themes if t.get("occurrences", 0) >= 2]

        synthesis = {
            "synthesis_id": f"synthesis_{tick}",
            "arc_count": len(completed_arcs),
            "common_entities": sorted(common_entities),
            "recurring_themes": themes[:3],
            "tick": tick,
            "narrative_summary": f"Synthesis of {len(completed_arcs)} arcs with {len(common_entities)} shared entities",
        }
        state.arc_syntheses.append(synthesis)
        if len(state.arc_syntheses) > MAX_ARC_SYNTHESIS:
            state.arc_syntheses = state.arc_syntheses[-MAX_ARC_SYNTHESIS:]
        return {"success": True, "synthesis": synthesis}


# ---------------------------------------------------------------------------
# 23.4 — Relationship-driven story emergence
# ---------------------------------------------------------------------------

class RelationshipEmergenceEngine:
    """Detect emergent stories from relationship dynamics."""

    @staticmethod
    def detect_emergence(relationships: List[Dict[str, Any]],
                         threshold: float = 0.7) -> List[Dict[str, Any]]:
        emergent: List[Dict[str, Any]] = []
        for rel in relationships:
            trust = _sf(rel.get("trust"))
            hostility = _sf(rel.get("hostility"))
            if trust > threshold:
                emergent.append({
                    "type": "deep_bond",
                    "entities": [rel.get("source_id"), rel.get("target_id")],
                    "strength": trust,
                    "narrative_potential": "loyalty arc",
                })
            elif hostility > threshold:
                emergent.append({
                    "type": "rivalry",
                    "entities": [rel.get("source_id"), rel.get("target_id")],
                    "strength": hostility,
                    "narrative_potential": "confrontation arc",
                })
            elif trust > 0.5 and hostility > 0.3:
                emergent.append({
                    "type": "complex_relationship",
                    "entities": [rel.get("source_id"), rel.get("target_id")],
                    "strength": (trust + hostility) / 2,
                    "narrative_potential": "betrayal or redemption arc",
                })
        return emergent


# ---------------------------------------------------------------------------
# 23.5 — Director + memory + planning convergence
# ---------------------------------------------------------------------------

class ConvergenceEngine:
    """Converge director, memory, and planning for coherent narrative."""

    @staticmethod
    def compute_convergence(
        director_context: Dict[str, Any],
        memory_context: Dict[str, Any],
        planning_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        d_tension = _sf(director_context.get("global_tension"), 0.5)
        m_fear = _sf(memory_context.get("avg_fear"), 0.0)
        p_urgency = _sf(planning_context.get("avg_priority"), 0.5)

        alignment = 1.0 - abs(d_tension - (m_fear + p_urgency) / 2)
        alignment = _clamp(alignment)

        suggestion = "maintain"
        if alignment < 0.3:
            suggestion = "recalibrate"
        elif alignment > 0.8:
            suggestion = "escalate"

        return {
            "alignment_score": round(alignment, 3),
            "suggestion": suggestion,
            "director_tension": d_tension,
            "memory_fear": m_fear,
            "planning_urgency": p_urgency,
        }


# ---------------------------------------------------------------------------
# 23.6 — Endgame / climax orchestration
# ---------------------------------------------------------------------------

class CliMaxOrchestrator:
    """Orchestrate endgame/climax sequences."""

    @staticmethod
    def evaluate_climax_readiness(
        state: NarrativeCoherenceState,
        active_arcs: List[Dict[str, Any]],
        completed_arcs: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        pending_callbacks = len([c for c in state.callbacks if not c.get("paid_off")])
        total_callbacks = len(state.callbacks)
        payoff_ratio = (
            (total_callbacks - pending_callbacks) / total_callbacks
            if total_callbacks > 0 else 0.0
        )
        active_count = len(active_arcs)
        completed_count = len(completed_arcs)

        readiness = 0.0
        if payoff_ratio > 0.7:
            readiness += 0.3
        if active_count <= 2:
            readiness += 0.2
        if completed_count >= 3:
            readiness += 0.2
        if state.coherence_score > 0.7:
            readiness += 0.3

        return {
            "readiness": _clamp(readiness),
            "payoff_ratio": round(payoff_ratio, 3),
            "pending_callbacks": pending_callbacks,
            "active_arcs": active_count,
            "completed_arcs": completed_count,
            "recommendation": "ready" if readiness > 0.7 else "not_ready",
        }


# ---------------------------------------------------------------------------
# 23.7 — Narrative analytics / author insight tools
# ---------------------------------------------------------------------------

class NarrativeAnalytics:
    @staticmethod
    def get_coherence_report(state: NarrativeCoherenceState) -> Dict[str, Any]:
        return {
            "theme_count": len(state.themes),
            "motif_count": len(state.motifs),
            "callback_count": len(state.callbacks),
            "payoff_count": len(state.payoffs),
            "pending_callbacks": len([c for c in state.callbacks if not c.get("paid_off")]),
            "synthesis_count": len(state.arc_syntheses),
            "coherence_score": state.coherence_score,
        }

    @staticmethod
    def get_theme_distribution(state: NarrativeCoherenceState) -> Dict[str, int]:
        return {
            t.get("theme", "unknown"): t.get("occurrences", 0)
            for t in state.themes
        }


# ---------------------------------------------------------------------------
# 23.8 — Final coherence / determinism fix pass
# ---------------------------------------------------------------------------

class NarrativeDeterminismValidator:
    @staticmethod
    def validate_determinism(s1: NarrativeCoherenceState,
                             s2: NarrativeCoherenceState) -> bool:
        return s1.to_dict() == s2.to_dict()

    @staticmethod
    def validate_bounds(state: NarrativeCoherenceState) -> List[str]:
        violations: List[str] = []
        if len(state.themes) > MAX_THEMES:
            violations.append(f"themes exceed max ({len(state.themes)} > {MAX_THEMES})")
        if len(state.motifs) > MAX_MOTIFS:
            violations.append(f"motifs exceed max ({len(state.motifs)} > {MAX_MOTIFS})")
        if len(state.callbacks) > MAX_CALLBACKS:
            violations.append(f"callbacks exceed max ({len(state.callbacks)} > {MAX_CALLBACKS})")
        if len(state.arc_syntheses) > MAX_ARC_SYNTHESIS:
            violations.append(f"arc_syntheses exceed max ({len(state.arc_syntheses)} > {MAX_ARC_SYNTHESIS})")
        if state.coherence_score < 0.0 or state.coherence_score > 1.0:
            violations.append(f"coherence_score out of range: {state.coherence_score}")
        return violations

    @staticmethod
    def normalize_state(state: NarrativeCoherenceState) -> NarrativeCoherenceState:
        themes = list(state.themes)
        if len(themes) > MAX_THEMES:
            themes.sort(key=lambda t: t.get("occurrences", 0), reverse=True)
            themes = themes[:MAX_THEMES]
        motifs = list(state.motifs)
        if len(motifs) > MAX_MOTIFS:
            motifs.sort(key=lambda m: m.get("count", 0), reverse=True)
            motifs = motifs[:MAX_MOTIFS]
        callbacks = list(state.callbacks)
        if len(callbacks) > MAX_CALLBACKS:
            paid = [c for c in callbacks if c.get("paid_off")]
            unpaid = [c for c in callbacks if not c.get("paid_off")]
            if len(unpaid) >= MAX_CALLBACKS:
                callbacks = unpaid[:MAX_CALLBACKS]
            else:
                remaining = MAX_CALLBACKS - len(unpaid)
                callbacks = unpaid + paid[-remaining:] if remaining > 0 else unpaid
        syntheses = list(state.arc_syntheses)
        if len(syntheses) > MAX_ARC_SYNTHESIS:
            syntheses = syntheses[-MAX_ARC_SYNTHESIS:]
        return NarrativeCoherenceState(
            tick=state.tick, themes=themes, motifs=motifs,
            callbacks=callbacks, payoffs=list(state.payoffs),
            arc_syntheses=syntheses,
            coherence_score=_clamp(state.coherence_score),
        )
