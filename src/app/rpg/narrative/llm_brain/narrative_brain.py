"""Narrative Brain Core - LLM-powered narrative intelligence.
TIER 19: LLM Narrative Brain Integration"""
from __future__ import annotations
import json, logging
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional
from .prompt_builder import PromptBuilder
from .response_parser import ResponseParser
from .memory_adapter import NarrativeMemoryAdapter
from .validator import BrainOutputValidator
logger = logging.getLogger(__name__)
def _clamp(v, lo, hi): return max(lo, min(hi, v))
@dataclass
class NarrativeDecision:
    intent: str = 'no_change'
    tension_delta: float = 0.0
    events: List[Dict[str, Any]] = field(default_factory=list)
    arc_updates: List[Dict[str, Any]] = field(default_factory=list)
    pacing: str = 'normal'
    def to_dict(self): return asdict(self)
    @classmethod
    def from_dict(cls, data):
        return cls(intent=data.get('intent','no_change'), tension_delta=_clamp(float(data.get('tension_delta',0.0)),-0.2,0.2), events=data.get('events',[])[:3], arc_updates=data.get('arc_updates',[]), pacing=data.get('pacing','normal'))
    @classmethod
    def fallback(cls): return cls(intent='system_fallback')
class NarrativeBrain:
    """LLM-powered narrative intelligence layer."""
    def __init__(self, llm_client):
        self.llm = llm_client
        self.prompt_builder = PromptBuilder()
        self.response_parser = ResponseParser()
        self.memory_adapter = NarrativeMemoryAdapter()
        self.validator = BrainOutputValidator()
    def evaluate(self, context: Dict[str, Any]) -> NarrativeDecision:
        compressed = self.memory_adapter.compress(context)
        prompt = self.prompt_builder.build(compressed)
        try:
            raw = self.llm.complete(prompt) if hasattr(self.llm, 'complete') else self.llm(prompt)
        except Exception as e:
            logger.warning('LLM call failed, using fallback: %s', e)
            return NarrativeDecision.fallback()
        try:
            decision = self.response_parser.parse(raw)
            return self.validator.validate(decision)
        except Exception as e:
            logger.warning('Parse failed, using fallback: %s', e)
            return NarrativeDecision.fallback()
