from typing import Any, Dict 
 
class EmergenceMetrics: 
    def compute(self, divergence, causality, loop_penalty): 
        score = divergence * 0.5 + causality * 0.4 - loop_penalty * 0.3 
        return max(0.0, min(score, 1.0)) 
