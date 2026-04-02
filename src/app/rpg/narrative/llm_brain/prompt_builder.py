from __future__ import annotations  
from typing import Any, Dict  
PROMPT = """Analyze state. World: {summary}. Tension: {tension}. Phase: {phase}. Arcs: {arcs}. Return JSON with intent, tension_delta, events, arc_updates, pacing."""  
class PromptBuilder:  
    def build(self, c):  
        return PROMPT.format(summary=c.get("summary",""), tension=c.get("tension",0.3), phase=c.get("phase","rising"), arcs=c.get("arcs",""))  
