from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


_MAX_GOALS = 5


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _goal_sort_key(goal: Dict[str, Any]):
    priority = _safe_float(goal.get("priority"), 0.0)
    goal_id = _safe_str(goal.get("goal_id"))
    return (-priority, goal_id)


@dataclass
class GoalEngine:
    goals: List[Dict[str, Any]] = field(default_factory=list)
    max_goals: int = _MAX_GOALS

    def to_dict(self) -> Dict[str, Any]:
        return {
            "goals": [dict(goal) for goal in self.goals],
            "max_goals": int(self.max_goals),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any] | None) -> "GoalEngine":
        data = data or {}
        raw_goals = data.get("goals") or []
        max_goals = int(data.get("max_goals", _MAX_GOALS) or _MAX_GOALS)
        goals: List[Dict[str, Any]] = []
        for item in raw_goals:
            if not isinstance(item, dict):
                continue
            goals.append({
                "goal_id": _safe_str(item.get("goal_id")),
                "type": _safe_str(item.get("type")),
                "target_id": _safe_str(item.get("target_id")),
                "priority": _safe_float(item.get("priority"), 0.0),
                "reason": _safe_str(item.get("reason")),
                "status": _safe_str(item.get("status")) or "active",
                "progress": _safe_float(item.get("progress"), 0.0),
            })
        engine = cls(goals=goals, max_goals=max_goals)
        engine.goals = sorted(engine.goals, key=_goal_sort_key)[: engine.max_goals]
        return engine

    def _make_goal(
        self,
        npc_id: str,
        goal_type: str,
        target_id: str,
        priority: float,
        reason: str,
    ) -> Dict[str, Any]:
        goal_id = f"goal:{npc_id}:{goal_type}:{target_id or 'none'}"
        return {
            "goal_id": goal_id,
            "type": goal_type,
            "target_id": target_id,
            "priority": float(priority),
            "reason": reason,
            "status": "active",
            "progress": 0.0,
        }

    def generate_goals(
        self,
        npc_context: Dict[str, Any],
        simulation_state: Dict[str, Any],
        belief_summary: Dict[str, Dict[str, float]],
        memory_summary: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        npc_context = npc_context or {}
        simulation_state = simulation_state or {}
        belief_summary = belief_summary or {}

        npc_id = _safe_str(npc_context.get("npc_id"))
        npc_location_id = _safe_str(npc_context.get("location_id"))
        npc_faction_id = _safe_str(npc_context.get("faction_id"))

        player_beliefs = belief_summary.get("player", {})
        trust = _safe_float(player_beliefs.get("trust"), 0.0)
        fear = _safe_float(player_beliefs.get("fear"), 0.0)
        hostility = _safe_float(player_beliefs.get("hostility"), 0.0)

        locations = simulation_state.get("locations") or {}
        location_state = locations.get(npc_location_id) or {}
        location_pressure = _safe_float(location_state.get("pressure"), 0.0)

        goals: List[Dict[str, Any]] = []

        if location_pressure >= 2.0 and npc_location_id:
            goals.append(self._make_goal(
                npc_id=npc_id,
                goal_type="stabilize_location",
                target_id=npc_location_id,
                priority=0.80 + min(location_pressure * 0.05, 0.15),
                reason="Local pressure is elevated",
            ))

        if npc_faction_id:
            goals.append(self._make_goal(
                npc_id=npc_id,
                goal_type="support_faction",
                target_id=npc_faction_id,
                priority=0.45,
                reason="Faction loyalty baseline",
            ))

        if hostility >= 0.35:
            goals.append(self._make_goal(
                npc_id=npc_id,
                goal_type="retaliate",
                target_id="player",
                priority=0.70 + min(hostility * 0.20, 0.20),
                reason="Player is viewed as hostile",
            ))
        elif fear >= 0.35:
            goals.append(self._make_goal(
                npc_id=npc_id,
                goal_type="avoid_player",
                target_id="player",
                priority=0.65 + min(fear * 0.20, 0.20),
                reason="Player is viewed as threatening",
            ))
        elif trust >= 0.35:
            goals.append(self._make_goal(
                npc_id=npc_id,
                goal_type="approach_player",
                target_id="player",
                priority=0.60 + min(trust * 0.20, 0.20),
                reason="Player is viewed as trustworthy",
            ))
        else:
            goals.append(self._make_goal(
                npc_id=npc_id,
                goal_type="observe",
                target_id="player",
                priority=0.35,
                reason="Maintain awareness of player",
            ))

        if memory_summary:
            top_memory = memory_summary[0]
            top_target = _safe_str(top_memory.get("target_id"))
            top_type = _safe_str(top_memory.get("type"))
            if top_target and top_target != "player" and top_type in {"incident", "attack", "destabilize", "threaten"}:
                goals.append(self._make_goal(
                    npc_id=npc_id,
                    goal_type="investigate",
                    target_id=top_target,
                    priority=0.55,
                    reason=f"Recent salient memory: {top_type}",
                ))

        goals = sorted(goals, key=_goal_sort_key)

        deduped: List[Dict[str, Any]] = []
        seen = set()
        for goal in goals:
            goal_id = goal["goal_id"]
            if goal_id in seen:
                continue
            seen.add(goal_id)
            deduped.append(goal)

        return deduped[: self.max_goals]

    def merge_goals(self, generated: List[Dict[str, Any]]) -> None:
        generated = generated or []
        merged = {}
        for goal in self.goals + generated:
            goal_id = _safe_str(goal.get("goal_id"))
            if not goal_id:
                continue
            existing = merged.get(goal_id)
            if existing is None or _safe_float(goal.get("priority"), 0.0) > _safe_float(existing.get("priority"), 0.0):
                merged[goal_id] = dict(goal)
        self.goals = sorted(merged.values(), key=_goal_sort_key)[: self.max_goals]

    def top_goal(self) -> Dict[str, Any] | None:
        if not self.goals:
            return None
        return dict(sorted(self.goals, key=_goal_sort_key)[0])

    def advance_from_event(self, event: Dict[str, Any]) -> None:
        event = event or {}
        target_id = _safe_str(event.get("target_id"))
        event_type = _safe_str(event.get("type"))

        updated: List[Dict[str, Any]] = []
        for goal in self.goals:
            new_goal = dict(goal)
            if target_id and target_id == _safe_str(goal.get("target_id")):
                progress = _safe_float(goal.get("progress"), 0.0)
                if event_type in {"help", "support", "stabilize", "investigate", "negotiate"}:
                    progress += 0.25
                elif event_type in {"attack", "sabotage", "retaliate"}:
                    progress += 0.15
                new_goal["progress"] = min(progress, 1.0)
            updated.append(new_goal)
        self.goals = sorted(updated, key=_goal_sort_key)[: self.max_goals]
