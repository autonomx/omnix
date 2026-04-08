"""Narrative Decision - Isolated dataclass to avoid circular imports. TIER 19."""  
  
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List


def _clamp(v: float, lo: float, hi: float) -> float:  
    return max(lo, min(hi, v))  
  
  
@dataclass  
class NarrativeDecision:  
    """Structured output from the LLM brain."""  
    intent: str = 'no_change'  
    tension_delta: float = 0.0  
    events: List[Dict[str, Any]] = field(default_factory=list)  
    arc_updates: List[Dict[str, Any]] = field(default_factory=list)  
    pacing: str = 'normal'  
  
    def to_dict(self) -> Dict[str, Any]:  
        return asdict(self)  
  
    @classmethod  
    def from_dict(cls, data: Dict[str, Any]) -> 'NarrativeDecision':  
        return cls(  
            intent=data.get('intent', 'no_change'),  
            tension_delta=_clamp(float(data.get('tension_delta', 0.0)), -0.2, 0.2),  
            events=data.get('events', [])[:3],  
            arc_updates=data.get('arc_updates', []),  
            pacing=data.get('pacing', 'normal'),  
        )  
  
    @classmethod  
    def fallback(cls) -> 'NarrativeDecision':  
        return cls(intent='system_fallback') 
