from typing import Any, Dict, List  
  
class DivergenceAnalyzer:  
    def measure_divergence(self, tracker, npc_ids):  
        npc_patterns = {}  
        for npc_id in npc_ids:  
            actions = tracker.get_actions_for_npc(npc_id)  
            pattern = [a["action"] for a in actions]  
            npc_patterns[npc_id] = pattern  
        if not npc_patterns:  
            return 0.0  
        unique_patterns = set(tuple(p) for p in npc_patterns.values())  
        return len(unique_patterns) / max(len(npc_ids), 1)  
  
    def get_pattern_similarity(self, tracker, npc_id_a, npc_id_b):  
        actions_a = tracker.get_actions_for_npc(npc_id_a)  
        actions_b = tracker.get_actions_for_npc(npc_id_b)  
        set_a = set(a["action"] for a in actions_a)  
        set_b = set(a["action"] for a in actions_b)  
        if not set_a and not set_b:  
            return 1.0  
        intersection = set_a & set_b  
