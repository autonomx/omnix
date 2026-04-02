from typing import Any, List 
 
class LoopDetector: 
    def detect(self, action_sequence): 
        if len(action_sequence) < 6: 
            return False 
        last = action_sequence[-3:] 
        prev = action_sequence[-6:-3] 
        return last == prev 
