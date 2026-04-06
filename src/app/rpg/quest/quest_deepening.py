"""Phase 18 — Quest / objective deepening.

Objective graph, branching progression, dynamic generation,
failure/recovery, director+memory integration, UI, analytics, determinism.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))

def _sf(v: Any, d: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return d

def _si(v: Any, d: int = 0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return d

def _ss(v: Any, d: str = "") -> str:
    return str(v) if v is not None else d

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_ACTIVE_QUESTS = 20
MAX_COMPLETED_QUESTS = 50
MAX_OBJECTIVES_PER_QUEST = 10
MAX_BRANCHES = 5
QUEST_STATUSES = {"active", "completed", "failed", "abandoned"}
OBJECTIVE_STATUSES = {"pending", "active", "completed", "failed", "skipped"}

# ---------------------------------------------------------------------------
# 18.0 — Quest state foundations
# ---------------------------------------------------------------------------

@dataclass
class QuestObjectiveV2:
    objective_id: str = ""
    quest_id: str = ""
    description: str = ""
    status: str = "pending"
    progress: float = 0.0
    dependencies: List[str] = field(default_factory=list)
    optional: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "objective_id": self.objective_id, "quest_id": self.quest_id,
            "description": self.description, "status": self.status,
            "progress": self.progress,
            "dependencies": list(self.dependencies),
            "optional": self.optional,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "QuestObjectiveV2":
        return cls(
            objective_id=_ss(d.get("objective_id")),
            quest_id=_ss(d.get("quest_id")),
            description=_ss(d.get("description")),
            status=_ss(d.get("status"), "pending"),
            progress=_clamp(_sf(d.get("progress"))),
            dependencies=list(d.get("dependencies") or []),
            optional=bool(d.get("optional", False)),
            metadata=dict(d.get("metadata") or {}),
        )


@dataclass
class QuestBranch:
    branch_id: str = ""
    quest_id: str = ""
    condition: str = ""
    target_objectives: List[str] = field(default_factory=list)
    chosen: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "branch_id": self.branch_id, "quest_id": self.quest_id,
            "condition": self.condition,
            "target_objectives": list(self.target_objectives),
            "chosen": self.chosen,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "QuestBranch":
        return cls(
            branch_id=_ss(d.get("branch_id")),
            quest_id=_ss(d.get("quest_id")),
            condition=_ss(d.get("condition")),
            target_objectives=list(d.get("target_objectives") or []),
            chosen=bool(d.get("chosen", False)),
        )


@dataclass
class QuestV2:
    quest_id: str = ""
    title: str = ""
    description: str = ""
    status: str = "active"
    priority: float = 0.5
    objectives: List[QuestObjectiveV2] = field(default_factory=list)
    branches: List[QuestBranch] = field(default_factory=list)
    created_tick: int = 0
    completed_tick: int = 0
    entities: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "quest_id": self.quest_id, "title": self.title,
            "description": self.description, "status": self.status,
            "priority": self.priority,
            "objectives": [o.to_dict() for o in self.objectives],
            "branches": [b.to_dict() for b in self.branches],
            "created_tick": self.created_tick,
            "completed_tick": self.completed_tick,
            "entities": list(self.entities),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "QuestV2":
        return cls(
            quest_id=_ss(d.get("quest_id")),
            title=_ss(d.get("title")),
            description=_ss(d.get("description")),
            status=_ss(d.get("status"), "active"),
            priority=_clamp(_sf(d.get("priority"), 0.5)),
            objectives=[QuestObjectiveV2.from_dict(o) for o in (d.get("objectives") or [])],
            branches=[QuestBranch.from_dict(b) for b in (d.get("branches") or [])],
            created_tick=_si(d.get("created_tick")),
            completed_tick=_si(d.get("completed_tick")),
            entities=list(d.get("entities") or []),
            metadata=dict(d.get("metadata") or {}),
        )


@dataclass
class QuestSystemState:
    tick: int = 0
    active_quests: List[QuestV2] = field(default_factory=list)
    completed_quests: List[QuestV2] = field(default_factory=list)
    quest_history: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tick": self.tick,
            "active_quests": [q.to_dict() for q in self.active_quests],
            "completed_quests": [q.to_dict() for q in self.completed_quests],
            "quest_history": list(self.quest_history),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "QuestSystemState":
        return cls(
            tick=_si(d.get("tick")),
            active_quests=[QuestV2.from_dict(q) for q in (d.get("active_quests") or [])],
            completed_quests=[QuestV2.from_dict(q) for q in (d.get("completed_quests") or [])],
            quest_history=list(d.get("quest_history") or []),
        )


# ---------------------------------------------------------------------------
# 18.1 — Objective graph / dependency model
# ---------------------------------------------------------------------------

class ObjectiveGraph:
    """Manage objective dependencies."""

    @staticmethod
    def get_available_objectives(quest: QuestV2) -> List[QuestObjectiveV2]:
        completed_ids = {o.objective_id for o in quest.objectives if o.status == "completed"}
        available: List[QuestObjectiveV2] = []
        for obj in quest.objectives:
            if obj.status != "pending":
                continue
            deps_met = all(d in completed_ids for d in obj.dependencies)
            if deps_met:
                available.append(obj)
        return available

    @staticmethod
    def complete_objective(quest: QuestV2, objective_id: str) -> bool:
        for obj in quest.objectives:
            if obj.objective_id == objective_id:
                obj.status = "completed"
                obj.progress = 1.0
                return True
        return False

    @staticmethod
    def fail_objective(quest: QuestV2, objective_id: str) -> bool:
        for obj in quest.objectives:
            if obj.objective_id == objective_id:
                obj.status = "failed"
                return True
        return False

    @staticmethod
    def is_quest_completable(quest: QuestV2) -> bool:
        required = [o for o in quest.objectives if not o.optional]
        return all(o.status == "completed" for o in required)

    @staticmethod
    def is_quest_failed(quest: QuestV2) -> bool:
        required = [o for o in quest.objectives if not o.optional]
        return any(o.status == "failed" for o in required)


# ---------------------------------------------------------------------------
# 18.2 — Branching quest progression
# ---------------------------------------------------------------------------

class QuestBranchManager:
    """Handle quest branching."""

    @staticmethod
    def choose_branch(quest: QuestV2, branch_id: str) -> Dict[str, Any]:
        for b in quest.branches:
            if b.branch_id == branch_id and not b.chosen:
                b.chosen = True
                for obj in quest.objectives:
                    if obj.objective_id in b.target_objectives:
                        obj.status = "active"
                return {"success": True, "branch_id": branch_id,
                        "activated": list(b.target_objectives)}
        return {"success": False, "reason": "branch not found or already chosen"}

    @staticmethod
    def get_available_branches(quest: QuestV2) -> List[QuestBranch]:
        return [b for b in quest.branches if not b.chosen]


# ---------------------------------------------------------------------------
# 18.3 — Dynamic quest generation
# ---------------------------------------------------------------------------

class DynamicQuestGenerator:
    """Generate quests from world state."""

    TEMPLATES: Dict[str, Dict[str, Any]] = {
        "rescue": {
            "title_template": "Rescue {entity}",
            "objectives": [
                {"description": "Find the location of {entity}", "optional": False},
                {"description": "Defeat the captors", "optional": False},
                {"description": "Escort {entity} to safety", "optional": False},
            ],
        },
        "investigate": {
            "title_template": "Investigate {location}",
            "objectives": [
                {"description": "Travel to {location}", "optional": False},
                {"description": "Gather clues", "optional": False},
                {"description": "Report findings", "optional": True},
            ],
        },
        "eliminate": {
            "title_template": "Eliminate threat at {location}",
            "objectives": [
                {"description": "Locate the threat", "optional": False},
                {"description": "Engage and eliminate", "optional": False},
            ],
        },
    }

    _counter = 0

    @classmethod
    def _next_id(cls, prefix: str = "quest") -> str:
        cls._counter += 1
        return f"{prefix}_{cls._counter}"

    @classmethod
    def generate_quest(cls, template_type: str,
                       context: Dict[str, Any],
                       tick: int) -> Optional[QuestV2]:
        tmpl = cls.TEMPLATES.get(template_type)
        if tmpl is None:
            return None

        entity = _ss(context.get("entity"), "someone")
        location = _ss(context.get("location"), "somewhere")
        quest_id = cls._next_id("quest")

        title = tmpl["title_template"].format(entity=entity, location=location)
        objectives: List[QuestObjectiveV2] = []
        for i, obj_tmpl in enumerate(tmpl["objectives"]):
            obj_id = f"{quest_id}_obj_{i}"
            desc = obj_tmpl["description"].format(entity=entity, location=location)
            deps = [f"{quest_id}_obj_{i-1}"] if i > 0 else []
            objectives.append(QuestObjectiveV2(
                objective_id=obj_id, quest_id=quest_id,
                description=desc, optional=obj_tmpl.get("optional", False),
                dependencies=deps,
            ))

        return QuestV2(
            quest_id=quest_id, title=title,
            description=f"A quest to {template_type} involving {entity}",
            objectives=objectives, created_tick=tick,
            entities=[entity],
        )


# ---------------------------------------------------------------------------
# 18.4 — Quest failure / recovery / alternate paths
# ---------------------------------------------------------------------------

class QuestRecoveryEngine:
    """Handle quest failure and recovery."""

    @staticmethod
    def check_failure(quest: QuestV2) -> bool:
        return ObjectiveGraph.is_quest_failed(quest)

    @staticmethod
    def attempt_recovery(quest: QuestV2, tick: int) -> Dict[str, Any]:
        if quest.status != "active":
            return {"success": False, "reason": "quest not active"}
        failed = [o for o in quest.objectives if o.status == "failed" and not o.optional]
        if not failed:
            return {"success": False, "reason": "no failed required objectives"}

        # Create alternate path by skipping failed objective
        for obj in failed:
            obj.status = "skipped"
        quest.metadata["recovery_tick"] = tick
        quest.metadata["recovered"] = True
        return {"success": True, "skipped_count": len(failed)}

    @staticmethod
    def abandon_quest(quest: QuestV2, tick: int) -> QuestV2:
        quest.status = "abandoned"
        quest.completed_tick = tick
        return quest


# ---------------------------------------------------------------------------
# 18.5 — Director + memory integration for quests
# ---------------------------------------------------------------------------

class QuestDirectorIntegration:
    """Integrate quest system with director and memory."""

    @staticmethod
    def get_quest_context_for_director(
        quest_state: QuestSystemState,
    ) -> Dict[str, Any]:
        active = quest_state.active_quests
        return {
            "active_quest_count": len(active),
            "highest_priority_quest": (
                max(active, key=lambda q: q.priority).quest_id if active else None
            ),
            "entities_involved": sorted(set(
                e for q in active for e in q.entities
            )),
            "completion_ratio": (
                sum(1 for q in active if ObjectiveGraph.is_quest_completable(q))
                / len(active) if active else 0.0
            ),
        }

    @staticmethod
    def get_quest_memory_entries(quest: QuestV2) -> List[Dict[str, Any]]:
        entries: List[Dict[str, Any]] = []
        entries.append({
            "type": "quest_start",
            "quest_id": quest.quest_id,
            "title": quest.title,
            "tick": quest.created_tick,
        })
        for obj in quest.objectives:
            if obj.status in ("completed", "failed"):
                entries.append({
                    "type": f"objective_{obj.status}",
                    "quest_id": quest.quest_id,
                    "objective_id": obj.objective_id,
                    "description": obj.description,
                })
        return entries


# ---------------------------------------------------------------------------
# 18.6 — Quest UI / journal / tracking
# ---------------------------------------------------------------------------

class QuestPresenter:
    """Format quest state for UI."""

    @staticmethod
    def present_quest_journal(state: QuestSystemState) -> Dict[str, Any]:
        return {
            "active_quests": [
                {
                    "quest_id": q.quest_id, "title": q.title,
                    "status": q.status, "priority": q.priority,
                    "objective_count": len(q.objectives),
                    "completed_objectives": len([o for o in q.objectives if o.status == "completed"]),
                }
                for q in state.active_quests
            ],
            "completed_quests": [
                {"quest_id": q.quest_id, "title": q.title, "status": q.status}
                for q in state.completed_quests[-10:]
            ],
        }

    @staticmethod
    def present_quest_detail(quest: QuestV2) -> Dict[str, Any]:
        return {
            "quest_id": quest.quest_id, "title": quest.title,
            "description": quest.description, "status": quest.status,
            "objectives": [o.to_dict() for o in quest.objectives],
            "branches": [b.to_dict() for b in quest.branches],
            "entities": list(quest.entities),
        }


# ---------------------------------------------------------------------------
# 18.7 — Quest analytics / diff visibility
# ---------------------------------------------------------------------------

class QuestAnalytics:
    @staticmethod
    def get_statistics(state: QuestSystemState) -> Dict[str, Any]:
        return {
            "active_count": len(state.active_quests),
            "completed_count": len(state.completed_quests),
            "history_entries": len(state.quest_history),
            "total_objectives": sum(len(q.objectives) for q in state.active_quests),
            "completed_objectives": sum(
                len([o for o in q.objectives if o.status == "completed"])
                for q in state.active_quests
            ),
        }


# ---------------------------------------------------------------------------
# 18.8 — Quest determinism / bounded-state fix pass
# ---------------------------------------------------------------------------

class QuestDeterminismValidator:
    @staticmethod
    def validate_determinism(s1: QuestSystemState, s2: QuestSystemState) -> bool:
        return s1.to_dict() == s2.to_dict()

    @staticmethod
    def validate_bounds(state: QuestSystemState) -> List[str]:
        violations: List[str] = []
        if len(state.active_quests) > MAX_ACTIVE_QUESTS:
            violations.append(f"active quests exceed max ({len(state.active_quests)} > {MAX_ACTIVE_QUESTS})")
        if len(state.completed_quests) > MAX_COMPLETED_QUESTS:
            violations.append(f"completed quests exceed max ({len(state.completed_quests)} > {MAX_COMPLETED_QUESTS})")
        for q in state.active_quests:
            if len(q.objectives) > MAX_OBJECTIVES_PER_QUEST:
                violations.append(f"quest {q.quest_id} objectives exceed max")
            if len(q.branches) > MAX_BRANCHES:
                violations.append(f"quest {q.quest_id} branches exceed max")
        return violations

    @staticmethod
    def normalize_state(state: QuestSystemState) -> QuestSystemState:
        active = list(state.active_quests)
        if len(active) > MAX_ACTIVE_QUESTS:
            active.sort(key=lambda q: q.priority, reverse=True)
            active = active[:MAX_ACTIVE_QUESTS]
        completed = list(state.completed_quests)
        if len(completed) > MAX_COMPLETED_QUESTS:
            completed = completed[-MAX_COMPLETED_QUESTS:]
        for q in active:
            if len(q.objectives) > MAX_OBJECTIVES_PER_QUEST:
                q.objectives = q.objectives[:MAX_OBJECTIVES_PER_QUEST]
            if len(q.branches) > MAX_BRANCHES:
                q.branches = q.branches[:MAX_BRANCHES]
        return QuestSystemState(
            tick=state.tick, active_quests=active,
            completed_quests=completed,
            quest_history=list(state.quest_history),
        )
