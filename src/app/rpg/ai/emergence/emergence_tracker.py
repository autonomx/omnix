from collections import defaultdict  
from typing import Any, Dict, List  
  
class EmergenceTracker:  
    def __init__(self):  
        self.actions = []  
        self.world_changes = []  
        self.tick_events = defaultdict(list)  
  
    def record_action(self, tick, npc_id, action):  
        event = {"tick": tick, "npc_id": npc_id, "action": action.get("type", action) if isinstance(action, dict) else action}  
        self.actions.append(event)  
        self.tick_events[tick].append(event)  
  
    def record_world_change(self, tick, change_type, delta):  
        self.world_changes.append({"tick": tick, "change": change_type, "delta": delta})  
  
    def get_actions_for_npc(self, npc_id):  
        return [a for a in self.actions if a["npc_id"] == npc_id]  
  
    def get_events_for_tick(self, tick):  
        return self.tick_events.get(tick, [])  
  
    def get_total_actions(self):  
        return len(self.actions)  
  
    def get_total_world_changes(self):  
        return len(self.world_changes)  
  
    def reset(self):  
        self.actions.clear()  
        self.world_changes.clear()  
        self.tick_events.clear()  
