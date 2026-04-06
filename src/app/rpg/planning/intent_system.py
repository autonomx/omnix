"""Phase 12 — Planning / Intent system.

Goal generation, multi-step plan construction, execution, interruption,
companion planning, faction coordination, inspector and determinism
validation.  All state bounded and deterministic.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))

def _safe_str(v: Any, default: str = "") -> str:
    return str(v) if v is not None else default

def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default

def _safe_int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_ACTIVE_GOALS = 5
MAX_COMPLETED_GOALS = 20
MAX_PLAN_STEPS = 5
MAX_GLOBAL_OBJECTIVES = 10
VALID_GOAL_STATUSES = {"active", "completed", "failed", "suspended"}
VALID_STEP_STATUSES = {"pending", "active", "completed", "failed"}
GOAL_TYPES = {"neutralize", "protect", "survive", "acquire", "explore", "negotiate"}
INTERRUPT_TYPES = {"threat_detected", "goal_invalidated", "better_opportunity",
                   "ally_in_danger", "plan_blocked"}

# ---------------------------------------------------------------------------
# 12.0 — Goal / intent state foundations
# ---------------------------------------------------------------------------

@dataclass
class GoalState:
    goal_id: str = ""
    actor_id: str = ""
    goal_type: str = ""
    description: str = ""
    priority: float = 0.5
    status: str = "active"
    created_tick: int = 0
    deadline_tick: Optional[int] = None
    progress: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "goal_id": self.goal_id,
            "actor_id": self.actor_id,
            "goal_type": self.goal_type,
            "description": self.description,
            "priority": self.priority,
            "status": self.status,
            "created_tick": self.created_tick,
            "deadline_tick": self.deadline_tick,
            "progress": self.progress,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "GoalState":
        return cls(
            goal_id=_safe_str(d.get("goal_id")),
            actor_id=_safe_str(d.get("actor_id")),
            goal_type=_safe_str(d.get("goal_type")),
            description=_safe_str(d.get("description")),
            priority=_clamp(_safe_float(d.get("priority"), 0.5)),
            status=_safe_str(d.get("status"), "active"),
            created_tick=_safe_int(d.get("created_tick")),
            deadline_tick=d.get("deadline_tick"),
            progress=_clamp(_safe_float(d.get("progress"))),
            metadata=dict(d.get("metadata") or {}),
        )


@dataclass
class PlanStep:
    step_id: str = ""
    action_type: str = ""
    target_id: Optional[str] = None
    preconditions: Dict[str, Any] = field(default_factory=dict)
    expected_outcome: str = ""
    status: str = "pending"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "action_type": self.action_type,
            "target_id": self.target_id,
            "preconditions": dict(self.preconditions),
            "expected_outcome": self.expected_outcome,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "PlanStep":
        return cls(
            step_id=_safe_str(d.get("step_id")),
            action_type=_safe_str(d.get("action_type")),
            target_id=d.get("target_id"),
            preconditions=dict(d.get("preconditions") or {}),
            expected_outcome=_safe_str(d.get("expected_outcome")),
            status=_safe_str(d.get("status"), "pending"),
        )


@dataclass
class Plan:
    plan_id: str = ""
    goal_id: str = ""
    steps: List[PlanStep] = field(default_factory=list)
    status: str = "active"
    created_tick: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "goal_id": self.goal_id,
            "steps": [s.to_dict() for s in self.steps],
            "status": self.status,
            "created_tick": self.created_tick,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Plan":
        return cls(
            plan_id=_safe_str(d.get("plan_id")),
            goal_id=_safe_str(d.get("goal_id")),
            steps=[PlanStep.from_dict(s) for s in (d.get("steps") or [])],
            status=_safe_str(d.get("status"), "active"),
            created_tick=_safe_int(d.get("created_tick")),
        )


@dataclass
class IntentState:
    actor_id: str = ""
    active_goals: List[GoalState] = field(default_factory=list)
    completed_goals: List[GoalState] = field(default_factory=list)
    plan_cache: Dict[str, Any] = field(default_factory=dict)
    last_plan_tick: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "actor_id": self.actor_id,
            "active_goals": [g.to_dict() for g in self.active_goals],
            "completed_goals": [g.to_dict() for g in self.completed_goals],
            "plan_cache": dict(self.plan_cache),
            "last_plan_tick": self.last_plan_tick,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "IntentState":
        return cls(
            actor_id=_safe_str(d.get("actor_id")),
            active_goals=[GoalState.from_dict(g) for g in (d.get("active_goals") or [])],
            completed_goals=[GoalState.from_dict(g) for g in (d.get("completed_goals") or [])],
            plan_cache=dict(d.get("plan_cache") or {}),
            last_plan_tick=_safe_int(d.get("last_plan_tick")),
        )

    def _enforce_bounds(self) -> None:
        if len(self.active_goals) > MAX_ACTIVE_GOALS:
            self.active_goals.sort(key=lambda g: g.priority, reverse=True)
            self.active_goals = self.active_goals[:MAX_ACTIVE_GOALS]
        if len(self.completed_goals) > MAX_COMPLETED_GOALS:
            self.completed_goals = self.completed_goals[-MAX_COMPLETED_GOALS:]


@dataclass
class PlanningSystemState:
    actors: Dict[str, IntentState] = field(default_factory=dict)
    global_objectives: List[Dict[str, Any]] = field(default_factory=list)
    tick: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "actors": {k: v.to_dict() for k, v in self.actors.items()},
            "global_objectives": list(self.global_objectives),
            "tick": self.tick,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "PlanningSystemState":
        return cls(
            actors={k: IntentState.from_dict(v) for k, v in (d.get("actors") or {}).items()},
            global_objectives=list(d.get("global_objectives") or []),
            tick=_safe_int(d.get("tick")),
        )


# ---------------------------------------------------------------------------
# 12.1 — Actor goal generation
# ---------------------------------------------------------------------------

class GoalGenerator:
    """Generate goals from beliefs and world context."""

    _counter = 0

    @classmethod
    def _next_id(cls, prefix: str = "goal") -> str:
        cls._counter += 1
        return f"{prefix}_{cls._counter}"

    @classmethod
    def generate_goals(
        cls,
        actor_id: str,
        beliefs: Dict[str, Any],
        memory_summary: Dict[str, Any],
        world_context: Dict[str, Any],
        tick: int,
    ) -> List[GoalState]:
        goals: List[GoalState] = []

        hostile = beliefs.get("hostile_targets") or []
        if hostile:
            goals.append(GoalState(
                goal_id=cls._next_id("goal"),
                actor_id=actor_id,
                goal_type="neutralize",
                description=f"Neutralize hostile target: {hostile[0] if hostile else 'unknown'}",
                priority=_clamp(0.6 + len(hostile) * 0.1),
                status="active",
                created_tick=tick,
                metadata={"targets": list(hostile[:3])},
            ))

        trusted = beliefs.get("trusted_allies") or []
        if trusted:
            goals.append(GoalState(
                goal_id=cls._next_id("goal"),
                actor_id=actor_id,
                goal_type="protect",
                description=f"Protect ally: {trusted[0] if trusted else 'unknown'}",
                priority=_clamp(0.5 + len(trusted) * 0.05),
                status="active",
                created_tick=tick,
                metadata={"allies": list(trusted[:3])},
            ))

        threat_level = _safe_float(beliefs.get("world_threat_level"), 0.0)
        if threat_level > 0.5:
            goals.append(GoalState(
                goal_id=cls._next_id("goal"),
                actor_id=actor_id,
                goal_type="survive",
                description="Survive high threat environment",
                priority=_clamp(0.7 + threat_level * 0.2),
                status="active",
                created_tick=tick,
                metadata={"threat_level": threat_level},
            ))

        resources = _safe_float(world_context.get("resources"), 1.0)
        if resources < 0.3:
            goals.append(GoalState(
                goal_id=cls._next_id("goal"),
                actor_id=actor_id,
                goal_type="acquire",
                description="Acquire needed resources",
                priority=_clamp(0.4 + (1.0 - resources) * 0.3),
                status="active",
                created_tick=tick,
                metadata={"resource_level": resources},
            ))

        goals.sort(key=lambda g: g.priority, reverse=True)
        return goals[:3]


# ---------------------------------------------------------------------------
# 12.2 — Multi-step plan construction
# ---------------------------------------------------------------------------

_GOAL_STEP_TEMPLATES: Dict[str, List[Dict[str, str]]] = {
    "neutralize": [
        {"action_type": "approach", "outcome": "within range of target"},
        {"action_type": "engage", "outcome": "target engaged in conflict"},
        {"action_type": "resolve", "outcome": "target neutralized or fled"},
    ],
    "protect": [
        {"action_type": "move_to", "outcome": "near ally"},
        {"action_type": "guard", "outcome": "ally protected"},
        {"action_type": "alert", "outcome": "allies warned of danger"},
    ],
    "survive": [
        {"action_type": "assess", "outcome": "threats identified"},
        {"action_type": "retreat_or_defend", "outcome": "position secured"},
        {"action_type": "recover", "outcome": "resources replenished"},
    ],
    "acquire": [
        {"action_type": "locate", "outcome": "resource location found"},
        {"action_type": "obtain", "outcome": "resource acquired"},
        {"action_type": "secure", "outcome": "resource stored safely"},
    ],
}

class PlanBuilder:
    """Build multi-step plans from goals."""

    _counter = 0

    @classmethod
    def _next_id(cls, prefix: str = "plan") -> str:
        cls._counter += 1
        return f"{prefix}_{cls._counter}"

    @classmethod
    def build_plan(
        cls,
        goal: GoalState,
        actor_context: Dict[str, Any],
        world_context: Dict[str, Any],
    ) -> Plan:
        templates = _GOAL_STEP_TEMPLATES.get(goal.goal_type, [
            {"action_type": "observe", "outcome": "situation assessed"},
            {"action_type": "act", "outcome": "action taken"},
            {"action_type": "evaluate", "outcome": "outcome reviewed"},
        ])

        target_id = None
        targets = (goal.metadata or {}).get("targets") or []
        if targets:
            target_id = targets[0]
        allies = (goal.metadata or {}).get("allies") or []
        if not target_id and allies:
            target_id = allies[0]

        steps: List[PlanStep] = []
        for i, tmpl in enumerate(templates[:MAX_PLAN_STEPS]):
            steps.append(PlanStep(
                step_id=f"step_{goal.goal_id}_{i}",
                action_type=tmpl["action_type"],
                target_id=target_id,
                preconditions={},
                expected_outcome=tmpl["outcome"],
                status="pending",
            ))

        return Plan(
            plan_id=cls._next_id("plan"),
            goal_id=goal.goal_id,
            steps=steps,
            status="active",
            created_tick=goal.created_tick,
        )


# ---------------------------------------------------------------------------
# 12.3 — Plan execution hooks
# ---------------------------------------------------------------------------

class PlanExecutor:
    """Execute plans step by step."""

    @staticmethod
    def get_current_step(plan: Plan) -> Optional[PlanStep]:
        for step in plan.steps:
            if step.status in ("pending", "active"):
                return step
        return None

    @staticmethod
    def advance_step(plan: Plan, outcome: str = "success") -> Plan:
        for step in plan.steps:
            if step.status in ("pending", "active"):
                if outcome == "success":
                    step.status = "completed"
                else:
                    step.status = "failed"
                break
        # Check if all done
        all_done = all(s.status in ("completed", "failed") for s in plan.steps)
        if all_done:
            any_failed = any(s.status == "failed" for s in plan.steps)
            plan.status = "failed" if any_failed else "completed"
        return plan

    @staticmethod
    def is_plan_complete(plan: Plan) -> bool:
        return plan.status in ("completed", "failed")

    @staticmethod
    def get_plan_action(plan: Plan, actor_context: Dict[str, Any]) -> Dict[str, Any]:
        step = PlanExecutor.get_current_step(plan)
        if step is None:
            return {"action": "wait", "reason": "no pending steps"}
        return {
            "action": step.action_type,
            "target_id": step.target_id,
            "step_id": step.step_id,
            "expected_outcome": step.expected_outcome,
        }


# ---------------------------------------------------------------------------
# 12.4 — Plan interruption / replanning
# ---------------------------------------------------------------------------

class PlanInterruptHandler:
    """Handle plan interruptions."""

    @staticmethod
    def check_interrupts(
        plan: Plan,
        events: List[Dict[str, Any]],
        actor_context: Dict[str, Any],
    ) -> List[str]:
        reasons: List[str] = []
        for evt in events:
            etype = _safe_str(evt.get("type"))
            if etype in ("attack", "ambush", "threat"):
                reasons.append("threat_detected")
            if etype == "goal_completed" and evt.get("goal_id") == plan.goal_id:
                reasons.append("goal_invalidated")
            if etype == "opportunity":
                reasons.append("better_opportunity")
            if etype in ("ally_attacked", "ally_down"):
                reasons.append("ally_in_danger")
            if etype == "path_blocked":
                reasons.append("plan_blocked")
        return sorted(set(reasons))

    @staticmethod
    def should_replan(plan: Plan, interrupts: List[str]) -> bool:
        if not interrupts:
            return False
        critical = {"threat_detected", "goal_invalidated", "ally_in_danger"}
        return bool(set(interrupts) & critical)

    @staticmethod
    def suspend_plan(plan: Plan) -> Plan:
        plan.status = "suspended"
        return plan

    @staticmethod
    def resume_plan(plan: Plan) -> Plan:
        if plan.status == "suspended":
            plan.status = "active"
        return plan


# ---------------------------------------------------------------------------
# 12.5 — Companion planning behaviour
# ---------------------------------------------------------------------------

_COMPANION_ALIGNMENTS: Dict[str, str] = {
    "neutralize": "support_attack",
    "protect": "cover_ally",
    "survive": "cover_retreat",
    "acquire": "scout_ahead",
    "explore": "scout_ahead",
    "negotiate": "observe",
}

class CompanionPlanner:
    """Generate companion plans aligned with the leader's plan."""

    _counter = 0

    @classmethod
    def _next_id(cls) -> str:
        cls._counter += 1
        return f"comp_plan_{cls._counter}"

    @classmethod
    def generate_companion_plan(
        cls,
        companion_id: str,
        leader_id: str,
        leader_plan: Plan,
        companion_beliefs: Dict[str, Any],
    ) -> Plan:
        goal_type = ""
        for step in leader_plan.steps:
            goal_type = step.action_type
            break

        # Look up leader plan's goal type from template matching
        aligned_action = "follow"
        for gtype, action in _COMPANION_ALIGNMENTS.items():
            if any(s.action_type in _GOAL_STEP_TEMPLATES.get(gtype, [{}])
                   and s.action_type == _GOAL_STEP_TEMPLATES.get(gtype, [{}])[0].get("action_type")
                   for s in leader_plan.steps[:1]):
                aligned_action = action
                break

        # Simpler: map leader's first step action
        first_step = leader_plan.steps[0] if leader_plan.steps else None
        if first_step:
            act = first_step.action_type
            if act in ("approach", "engage", "resolve"):
                aligned_action = "support_attack"
            elif act in ("move_to", "guard", "alert"):
                aligned_action = "cover_ally"
            elif act in ("assess", "retreat_or_defend", "recover"):
                aligned_action = "cover_retreat"
            elif act in ("locate", "obtain", "secure"):
                aligned_action = "scout_ahead"

        steps = [
            PlanStep(
                step_id=f"comp_step_{companion_id}_0",
                action_type=aligned_action,
                target_id=leader_id,
                expected_outcome=f"supporting {leader_id}",
                status="pending",
            ),
            PlanStep(
                step_id=f"comp_step_{companion_id}_1",
                action_type="follow",
                target_id=leader_id,
                expected_outcome=f"staying near {leader_id}",
                status="pending",
            ),
        ]

        return Plan(
            plan_id=cls._next_id(),
            goal_id=leader_plan.goal_id,
            steps=steps,
            status="active",
            created_tick=leader_plan.created_tick,
        )


# ---------------------------------------------------------------------------
# 12.6 — Group / faction intent coordination
# ---------------------------------------------------------------------------

class FactionIntentCoordinator:
    """Coordinate faction member plans to avoid conflicts."""

    @staticmethod
    def coordinate_faction_plans(
        faction_id: str,
        member_plans: Dict[str, Plan],
        faction_goals: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        target_assignments: Dict[str, List[str]] = {}
        for actor_id, plan in member_plans.items():
            for step in plan.steps:
                if step.target_id and step.status in ("pending", "active"):
                    target_assignments.setdefault(step.target_id, []).append(actor_id)

        coordination: Dict[str, Any] = {
            "faction_id": faction_id,
            "assignments": {},
            "conflicts_resolved": 0,
        }

        for target_id, actors in target_assignments.items():
            if len(actors) <= 1:
                for a in actors:
                    coordination["assignments"][a] = {"role": "primary", "target": target_id}
            else:
                coordination["assignments"][actors[0]] = {"role": "primary", "target": target_id}
                for a in actors[1:]:
                    coordination["assignments"][a] = {"role": "flank", "target": target_id}
                coordination["conflicts_resolved"] += 1

        return coordination


# ---------------------------------------------------------------------------
# 12.7 — Planner inspector / timeline visibility
# ---------------------------------------------------------------------------

class PlannerInspector:
    """Debug inspection for planning state."""

    @staticmethod
    def inspect_actor_plans(intent_state: IntentState) -> Dict[str, Any]:
        return {
            "actor_id": intent_state.actor_id,
            "active_goal_count": len(intent_state.active_goals),
            "completed_goal_count": len(intent_state.completed_goals),
            "last_plan_tick": intent_state.last_plan_tick,
            "goals": [g.to_dict() for g in intent_state.active_goals],
        }

    @staticmethod
    def inspect_plan_timeline(plan: Plan) -> List[Dict[str, Any]]:
        timeline: List[Dict[str, Any]] = []
        for i, step in enumerate(plan.steps):
            timeline.append({
                "index": i,
                "step_id": step.step_id,
                "action_type": step.action_type,
                "status": step.status,
                "target_id": step.target_id,
            })
        return timeline

    @staticmethod
    def get_planning_statistics(system_state: PlanningSystemState) -> Dict[str, Any]:
        total_goals = 0
        total_completed = 0
        for intent in system_state.actors.values():
            total_goals += len(intent.active_goals)
            total_completed += len(intent.completed_goals)
        return {
            "actor_count": len(system_state.actors),
            "total_active_goals": total_goals,
            "total_completed_goals": total_completed,
            "global_objective_count": len(system_state.global_objectives),
            "tick": system_state.tick,
        }


# ---------------------------------------------------------------------------
# 12.8 — Planning determinism / bounded-state fix pass
# ---------------------------------------------------------------------------

class PlanningDeterminismValidator:
    """Validate planning determinism and bounds."""

    @staticmethod
    def validate_determinism(s1: PlanningSystemState, s2: PlanningSystemState) -> bool:
        return s1.to_dict() == s2.to_dict()

    @staticmethod
    def validate_bounds(system_state: PlanningSystemState) -> List[str]:
        violations: List[str] = []
        if len(system_state.global_objectives) > MAX_GLOBAL_OBJECTIVES:
            violations.append(
                f"global_objectives exceeds max "
                f"({len(system_state.global_objectives)} > {MAX_GLOBAL_OBJECTIVES})"
            )
        for actor_id, intent in system_state.actors.items():
            if len(intent.active_goals) > MAX_ACTIVE_GOALS:
                violations.append(
                    f"actor {actor_id} active_goals exceeds max "
                    f"({len(intent.active_goals)} > {MAX_ACTIVE_GOALS})"
                )
            if len(intent.completed_goals) > MAX_COMPLETED_GOALS:
                violations.append(
                    f"actor {actor_id} completed_goals exceeds max "
                    f"({len(intent.completed_goals)} > {MAX_COMPLETED_GOALS})"
                )
            for g in intent.active_goals:
                if g.priority < 0.0 or g.priority > 1.0:
                    violations.append(f"goal {g.goal_id} priority out of range: {g.priority}")
                if g.progress < 0.0 or g.progress > 1.0:
                    violations.append(f"goal {g.goal_id} progress out of range: {g.progress}")
        return violations

    @staticmethod
    def normalize_state(system_state: PlanningSystemState) -> PlanningSystemState:
        objs = list(system_state.global_objectives)
        if len(objs) > MAX_GLOBAL_OBJECTIVES:
            objs = objs[:MAX_GLOBAL_OBJECTIVES]

        actors: Dict[str, IntentState] = {}
        for actor_id, intent in system_state.actors.items():
            ag = list(intent.active_goals)
            if len(ag) > MAX_ACTIVE_GOALS:
                ag.sort(key=lambda g: g.priority, reverse=True)
                ag = ag[:MAX_ACTIVE_GOALS]
            for g in ag:
                g.priority = _clamp(g.priority)
                g.progress = _clamp(g.progress)

            cg = list(intent.completed_goals)
            if len(cg) > MAX_COMPLETED_GOALS:
                cg = cg[-MAX_COMPLETED_GOALS:]

            actors[actor_id] = IntentState(
                actor_id=actor_id,
                active_goals=ag,
                completed_goals=cg,
                plan_cache=dict(intent.plan_cache),
                last_plan_tick=intent.last_plan_tick,
            )

        return PlanningSystemState(
            actors=actors,
            global_objectives=objs,
            tick=system_state.tick,
        )
