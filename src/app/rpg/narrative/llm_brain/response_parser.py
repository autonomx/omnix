import json
import logging

from .narrative_brain import NarrativeDecision


class ResponseParser:  
    def parse(self, raw):  
        try:  
            d = json.loads(raw.strip())  
            return NarrativeDecision.from_dict(d)  
        except Exception:  
            return NarrativeDecision.fallback()  
