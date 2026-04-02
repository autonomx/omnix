from typing import Any, Dict, List 
 
class CausalityTracker: 
    def __init__(self): 
        self.links = [] 
    def link(self, action_event, world_event): 
        self.links.append({"action": action_event, "effect": world_event}) 
    def get_links(self): 
        return self.links 
    def causality_score(self): 
        if not self.links: 
            return 0.0 
        return min(len(self.links) / 10.0, 1.0) 
