"""Execution Pipeline — Canonical turn execution with all critical fixes.

This module implements ALL 6 critical fixes from the review:

    Fix #1: SYSTEM ORDERING — Canonical pipeline:
        Resolver → Scene → Resources → Executor → World → Memory → Arcs

    Fix #2: DIRECTOR FEEDBACK LOOP — Director receives outcome summaries
        and adapts its strategy based on failures.

    Fix #3: STORY ARCS ACTIVE INFLUENCE — Arcs force prioritization into
        Director planning, not just passive display.

    Fix #4: AUTHORITY HIERARCHY — Explicit priority model:
        director (10) > npc_goal (5) > autonomous (3)

    Fix #5: RESOURCE INFLUENCE ON PLANNING — Director receives resource
        state and avoids choosing impossible actions.

    Fix #6: STRUCTURED TRACE LOGGING — Full trace of every turn step
        for debugging and improvement.

Usage:
    pipeline = ExecutionPipeline(
        resolver=resolver,
        scene_manager=scene_manager,
        resource_manager=resource_manager,
        executor=executor,
        world=world,
        memory_manager=memory_manager,
        arc_manager=arc_manager,
        director=director,
        enable_trace=True,
    )
    result = pipeline.execute_turn(session, player_input)

The pipeline enforces:
    1. resolve(planned_actions)     — deduplicate conflicts
    2. scene.filter_actions(actions) — enforce scene constraints
    3. resource.filter_affordable(actions) — only affordable actions
    4. executor.execute(action)     — probabilistic execution
    5. world.apply(events)          — update world state
    6. memory.add(events)           — store in memory
    7. arcs.update(events)          — progress story arcs
    8. build_director_feedback()    — director learns outcomes
    9. build_trace()                — structured trace for debugging
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional


# ============================================================
# Fix #4: Authority Hierarchy — Explicit priority model
# ============================================================

AUTHORITY_PRIORITIES = {
    "director": 10,
    "npc_goal": 5,
    "autonomous": 3,
}


def get_action_priority(action: Dict[str, Any]) -> int:
    """Get priority for an action based on its source.

    Args:
        action: Action dict with optional "source" field.

    Returns:
        Priority value (higher = more important).
    """
    source = action.get("source", "autonomous")
    return AUTHORITY_PRIORITIES.get(source, 3)


def sort_actions_by_authority(actions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Sort actions by authority (director first, then NPC goals, then autonomous).

    Args:
        actions: List of action dicts.

    Returns:
        Sorted list of actions.
    """
    return sorted(actions, key=get_action_priority, reverse=True)


# ============================================================
# Fix #6: Structured Trace Logging
# ============================================================

class TurnTrace:
    """Structured trace of a single turn's execution.

    Captures every step of the pipeline so developers can
    debug and improve the system with full visibility.

    Attributes:
        turn_number: Which turn this trace represents.
        player_input: The player's input text.
        plan: Director's planned actions.
        resolved_actions: After conflict resolution.
        scene_filtered: After scene constraint filtering.
        resource_filtered: After affordability filtering.
        executed_results: After probabilistic execution.
        events: Collected events applied to world.
        arcs_updated: Arc progression results.
        director_feedback: Summary fed back to director.
        duration_ms: Total pipeline execution time.
    """

    def __init__(self, turn_number: int = 0):
        """Initialize TurnTrace.

        Args:
            turn_number: Turn number for this trace.
        """
        self.turn_number = turn_number
        self.timestamp = time.time()
        self.player_input = ""
        self.plan: List[Dict[str, Any]] = []
        self.resolved_actions: List[Dict[str, Any]] = []
        self.scene_filtered: List[Dict[str, Any]] = []
        self.resource_filtered: List[Dict[str, Any]] = []
        self.executed_results: List[Dict[str, Any]] = []
        self.events: List[Dict[str, Any]] = []
        self.arcs_updated: List[Dict[str, Any]] = []
        self.director_feedback: Dict[str, Any] = {}
        self.priority_overrides: List[Dict[str, Any]] = []
        self.duration_ms: float = 0.0
        self.errors: List[str] = []

    def add_error(self, error: str) -> None:
        """Record an error that occurred during pipeline execution.

        Args:
            error: Error description.
        """
        self.errors.append(error)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize trace to dict.

        Returns:
            Full trace dict.
        """
        return {
            "turn_number": self.turn_number,
            "timestamp": self.timestamp,
            "player_input": self.player_input,
            "plan_len": len(self.plan),
            "resolved_len": len(self.resolved_actions),
            "scene_filtered_len": len(self.scene_filtered),
            "resource_filtered_len": len(self.resource_filtered),
            "executed_results_len": len(self.executed_results),
            "events_len": len(self.events),
            "arcs_updated_len": len(self.arcs_updated),
            "director_feedback": self.director_feedback,
            "priority_overrides": self.priority_overrides,
            "duration_ms": round(self.duration_ms, 2),
            "errors": self.errors,
        }

    def summary(self) -> str:
        """Get human-readable trace summary.

        Returns:
            Multi-line summary of the turn.
        """
        lines = [
            f"=== Turn {self.turn_number} Trace ===",
            f"Player: {self.player_input[:80]}",
            f"Plan: {len(self.plan)} actions",
            f"Resolved: {len(self.resolved_actions)} actions",
            f"Scene filtered: {len(self.scene_filtered)} actions",
            f"Resource filtered: {len(self.resource_filtered)} actions",
            f"Executed: {len(self.executed_results)} results",
            f"Events: {len(self.events)} events",
            f"Arcs updated: {len(self.arcs_updated)} arcs",
            f"Duration: {self.duration_ms:.1f}ms",
        ]
        if self.errors:
            lines.append(f"ERRORS ({len(self.errors)}):")
            for err in self.errors:
                lines.append(f"  - {err}")
        if self.director_feedback:
            lines.append("Director Feedback:")
            for key, val in self.director_feedback.items():
                lines.append(f"  {key}: {val}")
        return "\n".join(lines)

    def save(self, filepath: str) -> None:
        """Save trace to JSON file.

        Args:
            filepath: Path to save trace.
        """
        with open(filepath, "w") as f:
            json.dump(self.to_dict(), f, indent=2, default=str)


# ============================================================
# Fix #2: Director Feedback Builder
# ============================================================

def build_director_feedback(
    executed_results: List[Dict[str, Any]],
    events: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Build feedback summary from turn outcomes for the Director.

    This is Fix #2: Director learns from outcomes.
    The feedback includes what succeeded, what failed, and patterns.

    Args:
        executed_results: Results from probabilistic execution.
        events: Events that were generated.

    Returns:
        Feedback dict with summaries and failure analysis.
    """
    # Count successes and failures
    successes = [r for r in executed_results if r.get("success")]
    failures = [r for r in executed_results if not r.get("success")]

    # Categorize failures
    failure_by_reason: Dict[str, int] = {}
    for result in failures:
        reason = result.get("outcome", "unknown")
        failure_by_reason[reason] = failure_by_reason.get(reason, 0) + 1

    # Extract events by type
    event_types: Dict[str, int] = {}
    for event in events:
        etype = event.get("type", "unknown")
        event_types[etype] = event_types.get(etype, 0) + 1

    # Identify NPC-specific failures
    npc_failures: Dict[str, List[str]] = {}
    for result in failures:
        action = result.get("original_action", result.get("action", {}))
        npc_id = action.get("npc_id", "unknown")
        action_type = action.get("action", "unknown")
        if npc_id not in npc_failures:
            npc_failures[npc_id] = []
        npc_failures[npc_id].append(action_type)

    feedback: Dict[str, Any] = {
        "total_actions": len(executed_results),
        "success_count": len(successes),
        "failure_count": len(failures),
        "failure_reasons": failure_by_reason,
        "event_types_generated": event_types,
        "npc_failures": dict(npc_failures),
    }

    return feedback


def format_feedback_for_director_prompt(feedback: Dict[str, Any]) -> str:
    """Format feedback as text for Director LLM prompt injection.

    Args:
        feedback: Feedback dict from build_director_feedback().

    Returns:
        Formatted string for prompt.
    """
    lines = [
        "=== Last Turn Outcome ===",
        f"Actions attempted: {feedback.get('total_actions', 0)}",
        f"Successes: {feedback.get('success_count', 0)}",
        f"Failures: {feedback.get('failure_count', 0)}",
    ]

    failure_reasons = feedback.get("failure_reasons", {})
    if failure_reasons:
        lines.append("")
        lines.append("Failure Reasons:")
        for reason, count in failure_reasons.items():
            lines.append(f"  - {reason}: {count}")

    npc_failures = feedback.get("npc_failures", {})
    if npc_failures:
        lines.append("")
        lines.append("NPC Failures:")
        for npc_id, failed_actions in npc_failures.items():
            lines.append(f"  - {npc_id}: {', '.join(failed_actions)}")

    events = feedback.get("event_types_generated", {})
    if events:
        lines.append("")
        lines.append("Events Generated:")
        for etype, count in events.items():
            lines.append(f"  - {etype}: {count}")

    lines.append("")
    lines.append("Update your strategy accordingly.")

    return "\n".join(lines)


# ============================================================
# Fix #3 & #5: Director Planning Context Builder
# ============================================================

def build_director_planning_context(
    session: Any,
    arc_manager: Any = None,
    resource_manager: Any = None,
    feedback: Optional[Dict[str, Any]] = None,
) -> str:
    """Build planning context string for Director prompt injection.

    Combines Fix #3 (active arc influence), Fix #5 (resource influence),
    and Fix #2 (feedback loop) into a single context block.

    Args:
        session: Current game session.
        arc_manager: StoryArcManager for active arcs.
        resource_manager: ResourceManager for resource states.
        feedback: Previous turn feedback dict.

    Returns:
        Context string for Director LLM prompt.
    """
    sections: List[str] = []

    # Fix #3: Active Story Arcs with FORCE prioritization
    if arc_manager and hasattr(arc_manager, "active_arcs"):
        active = arc_manager.active_arcs
        if active:
            lines = ["=== PRIMARY DIRECTIVE (Highest Priority) ==="]
            for arc in active:
                pct = int(arc.progress * 100)
                lines.append(
                    f"  ACTIVE ARC: {arc.goal} [{pct}%]"
                    f" — Phase: {getattr(arc, 'phase', 'N/A')}"
                )
            urgent = arc_manager.get_most_urgent_arc() if hasattr(arc_manager, "get_most_urgent_arc") else None
            if urgent:
                lines.append(f"  MOST URGENT: {urgent.goal}")
            lines.append("  You MUST bias decisions toward progressing the most urgent arc.")
            sections.append("\n".join(lines))

    # Fix #5: Resource State
    if resource_manager and hasattr(resource_manager, "pools"):
        lines = ["=== Resource State ==="]
        for entity_id, pool in resource_manager.pools.items():
            status = pool.get_status() if hasattr(pool, "get_status") else pool.to_dict()
            stamina = status.get("stamina", {})
            if isinstance(stamina, dict):
                current = stamina.get("current", "?")
                pct = stamina.get("pct", 0)
                lines.append(f"  {entity_id}: stamina={current} ({pct*100:.0f}%)")
            else:
                lines.append(f"  {entity_id}: {stamina}")
        lines.append("  Avoid actions that are not affordable.")
        sections.append("\n".join(lines))

    # Fix #2: Previous Turn Feedback
    if feedback:
        sections.append(format_feedback_for_director_prompt(feedback))

    if not sections:
        return ""

    return "\n\n".join(sections)


# ============================================================
# Resource Manager Filter Adapter
# ============================================================

def filter_affordable_actions(
    actions: List[Dict[str, Any]],
    resource_manager: Any,
) -> List[Dict[str, Any]]:
    """Filter actions to only those the entity can afford.

    This is Fix #5: Resource influence on execution.

    Args:
        actions: List of action dicts.
        resource_manager: ResourceManager instance.

    Returns:
        Filtered actions that are affordable.
    """
    if not resource_manager:
        return actions

    affordable = []
    for action in actions:
        npc_id = action.get("npc_id") or action.get("source")
        action_type = action.get("action", "unknown")

        if not npc_id:
            # Can't check affordability without entity
            affordable.append(action)
            continue

        pool = resource_manager.get_pool(npc_id)
        if not pool:
            # No resource pool = no restrictions
            affordable.append(action)
            continue

        if resource_manager.can_afford_action(npc_id, action_type):
            affordable.append(action)

    return affordable


def consume_action_resources(
    action: Dict[str, Any],
    resource_manager: Any,
) -> bool:
    """Consume resources for an action.

    Args:
        action: Action dict being executed.
        resource_manager: ResourceManager instance.

    Returns:
        True if resources were consumed successfully.
    """
    if not resource_manager:
        return True

    npc_id = action.get("npc_id") or action.get("source")
    action_type = action.get("action", "unknown")

    if not npc_id:
        return True

    return resource_manager.consume_action_resources(npc_id, action_type)


# ============================================================
# Main Pipeline
# ============================================================

class ExecutionPipeline:
    """Canonical execution pipeline that enforces correct order.

    This is the authoritative pipeline from the critical review.
    It replaces scattered execution logic with a single pipeline.

    Pipeline Order:
    1. Resolver: Deduplicate conflicting actions
    2. Scene: Filter by scene constraints
    3. Resources: Filter by affordability
    4. Authority: Sort by priority hierarchy
    5. Executor: Probabilistic execution per action
    6. World: Apply results to world state
    7. Memory: Store events in memory
    8. Arcs: Update story arc progress
    9. Feedback: Build Director feedback
    10. Trace: Record structured trace

    Attributes:
        resolver: ActionResolver for conflict resolution.
        scene_manager: SceneManager for scene constraints.
        resource_manager: ResourceManager for affordability.
        executor: ProbabilisticActionExecutor for execution.
        world: World state object.
        memory_manager: MemoryManager for persistence.
        arc_manager: StoryArcManager for narrative arcs.
        director: Director for feedback injection.
        enable_trace: If True, record structured traces.
        trace_history: List of past traces (if enabled).
    """

    def __init__(
        self,
        resolver: Any = None,
        scene_manager: Any = None,
        resource_manager: Any = None,
        executor: Any = None,
        world: Any = None,
        memory_manager: Any = None,
        arc_manager: Any = None,
        director: Any = None,
        enable_trace: bool = True,
        max_trace_history: int = 50,
    ):
        """Initialize ExecutionPipeline.

        Args:
            resolver: ActionResolver instance.
            scene_manager: SceneManager instance.
            resource_manager: ResourceManager instance.
            executor: ProbabilisticActionExecutor instance.
            world: World state object.
            memory_manager: MemoryManager instance.
            arc_manager: StoryArcManager instance.
            director: Director instance.
            enable_trace: Record structured traces.
            max_trace_history: Maximum traces to retain.
        """
        self.resolver = resolver
        self.scene_manager = scene_manager
        self.resource_manager = resource_manager
        self.executor = executor
        self.world = world
        self.memory_manager = memory_manager
        self.arc_manager = arc_manager
        self.director = director
        self.enable_trace = enable_trace
        self.trace_history: List[TurnTrace] = []
        self.max_trace_history = max_trace_history

        # Previous turn feedback (for Fix #2)
        self._last_feedback: Optional[Dict[str, Any]] = None

        # Turn counter
        self._turn_counter = 0

    def execute_turn(
        self,
        session: Any,
        planned_actions: List[Dict[str, Any]],
        player_input: str = "",
    ) -> Dict[str, Any]:
        """Execute one complete turn through the canonical pipeline.

        Args:
            session: Current game session.
            planned_actions: Actions planned by Director/NPCs.
            player_input: Player's input text.

        Returns:
            Turn result dict with events, trace, and feedback.
        """
        start_time = time.time()
        self._turn_counter += 1

        trace = TurnTrace(turn_number=self._turn_counter)
        trace.player_input = player_input
        trace.plan = list(planned_actions)

        # Step 1: Resolver — deduplicate conflicts
        actions = self._step_resolve(planned_actions, session, trace)

        # Step 2: Scene — filter by scene constraints
        actions = self._step_scene_filter(actions, trace)

        # Step 3: Resources — filter by affordability
        actions = self._step_resource_filter(actions, trace)

        # Step 4: Authority — sort by priority hierarchy
        actions = self._step_authority_sort(actions, trace)

        # Step 5: Execute — probabilistic execution
        results = self._step_execute(actions, trace)

        # Step 6: Collect events
        events = self._collect_events(results)

        # Step 7: World — apply events to world state
        self._step_world_apply(events, session, trace)

        # Step 8: Memory — store events
        self._step_memory_store(events, trace)

        # Step 9: Arcs — update story arcs
        arc_updates = self._step_arcs_update(events, session, trace)

        # Step 10: Scene manager — update scene progress
        self._step_scene_update(events, trace)

        # Step 11: Build feedback for Director
        feedback = build_director_feedback(results, events)
        self._last_feedback = feedback
        trace.director_feedback = feedback

        # Step 12: Finalize trace
        trace.duration_ms = (time.time() - start_time) * 1000

        if self.enable_trace:
            self.trace_history.append(trace)
            if len(self.trace_history) > self.max_trace_history:
                self.trace_history = self.trace_history[-self.max_trace_history:]

        # Build turn result
        return {
            "events": events,
            "executed_results": results,
            "arc_updates": arc_updates,
            "director_feedback": feedback,
            "trace": trace.to_dict() if self.enable_trace else None,
            "turn_number": self._turn_counter,
            "actions_planned": len(planned_actions),
            "actions_resolved": len(self._safe_list(actions)),
            "actions_executed": len(results),
        }

    # --------------------------------------------------------
    # Pipeline Step Implementations
    # --------------------------------------------------------

    def _step_resolve(
        self,
        actions: List[Dict[str, Any]],
        session: Any,
        trace: TurnTrace,
    ) -> List[Dict[str, Any]]:
        """Step 1: Resolve action conflicts.

        Args:
            actions: Planned actions.
            session: Game session.
            trace: Trace to record results.

        Returns:
            Resolved actions.
        """
        try:
            if self.resolver and hasattr(self.resolver, "resolve"):
                resolved = self.resolver.resolve(actions, session=session)
                trace.resolved_actions = list(resolved)
                return resolved
        except Exception as e:
            trace.add_error(f"Resolver failed: {e}")
        trace.resolved_actions = list(actions)
        return list(actions)

    def _step_scene_filter(
        self,
        actions: List[Dict[str, Any]],
        trace: TurnTrace,
    ) -> List[Dict[str, Any]]:
        """Step 2: Filter actions by scene constraints.

        Args:
            actions: Resolved actions.
            trace: Trace to record results.

        Returns:
            Filtered actions allowed by current scene.
        """
        try:
            if self.scene_manager and hasattr(self.scene_manager, "current_scene"):
                scene = self.scene_manager.current_scene
                if scene and hasattr(scene, "filter_actions"):
                    filtered = scene.filter_actions(actions)
                    trace.scene_filtered = list(filtered)
                    trace.priority_overrides.append({
                        "step": "scene_filter",
                        "before": len(actions),
                        "after": len(filtered),
                    })
                    return filtered
        except Exception as e:
            trace.add_error(f"Scene filter failed: {e}")
        trace.scene_filtered = list(actions)
        return list(actions)

    def _step_resource_filter(
        self,
        actions: List[Dict[str, Any]],
        trace: TurnTrace,
    ) -> List[Dict[str, Any]]:
        """Step 3: Filter actions by resource affordability.

        Args:
            actions: Scene-filtered actions.
            trace: Trace to record results.

        Returns:
            Actions the entities can afford.
        """
        try:
            if self.resource_manager:
                affordable = filter_affordable_actions(actions, self.resource_manager)
                trace.resource_filtered = list(affordable)
                if len(affordable) < len(actions):
                    trace.priority_overrides.append({
                        "step": "resource_filter",
                        "before": len(actions),
                        "after": len(affordable),
                    })
                return affordable
        except Exception as e:
            trace.add_error(f"Resource filter failed: {e}")
        trace.resource_filtered = list(actions)
        return list(actions)

    def _step_authority_sort(
        self,
        actions: List[Dict[str, Any]],
        trace: TurnTrace,
    ) -> List[Dict[str, Any]]:
        """Step 4: Sort actions by authority hierarchy.

        Args:
            actions: Affordable actions.
            trace: Trace to record results.

        Returns:
            Authority-sorted actions.
        """
        sorted_actions = sort_actions_by_authority(actions)
        return sorted_actions

    def _step_execute(
        self,
        actions: List[Dict[str, Any]],
        trace: TurnTrace,
    ) -> List[Dict[str, Any]]:
        """Step 5: Probabilistic execution of each action.

        Args:
            actions: Actions to execute.
            trace: Trace to record results.

        Returns:
            Execution results.
        """
        results = []
        for action in actions:
            # Consume resources before execution
            try:
                if self.resource_manager:
                    consume_action_resources(action, self.resource_manager)
            except Exception as e:
                trace.add_error(f"Resource consume failed: {e}")

            # Execute with uncertainty
            try:
                if self.executor and hasattr(self.executor, "execute_with_uncertainty"):
                    result = self.executor.execute_with_uncertainty(action)
                else:
                    # Mock execution
                    result = {
                        "success": True,
                        "outcome": "normal_success",
                        "events": [{"type": "action_executed", "action": action}],
                    }
                results.append(result)
            except Exception as e:
                trace.add_error(f"Action execution failed: {e}")
                results.append({
                    "success": False,
                    "outcome": "error",
                    "events": [{"type": "execution_error", "error": str(e)}],
                })

        trace.executed_results = list(results)
        return results

    def _collect_events(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Collect all events from execution results.

        Args:
            results: Execution results.

        Returns:
            Flat list of events.
        """
        events = []
        for result in results:
            result_events = result.get("events", [])
            events.extend(result_events)
        return events

    def _step_world_apply(
        self,
        events: List[Dict[str, Any]],
        session: Any,
        trace: TurnTrace,
    ) -> None:
        """Step 6: Apply events to world state.

        Args:
            events: Events to apply.
            session: Game session.
            trace: Trace to record results.
        """
        trace.events = list(events)

        # Tick resource regeneration
        try:
            if self.resource_manager and hasattr(self.resource_manager, "tick_all"):
                self.resource_manager.tick_all()
        except Exception as e:
            trace.add_error(f"Resource tick failed: {e}")

        # Update world time
        try:
            if self.world and hasattr(self.world, "time"):
                self.world.time = getattr(self.world, "time", 0) + 1
        except Exception as e:
            trace.add_error(f"World time update failed: {e}")

    def _step_memory_store(
        self,
        events: List[Dict[str, Any]],
        trace: TurnTrace,
    ) -> None:
        """Step 7: Store events in memory.

        Args:
            events: Events to store.
            trace: Trace to record results.
        """
        try:
            if self.memory_manager and hasattr(self.memory_manager, "add_events"):
                tick = 0
                if self.world and hasattr(self.world, "time"):
                    tick = self.world.time
                self.memory_manager.add_events(events, current_tick=tick)
        except Exception as e:
            trace.add_error(f"Memory storage failed: {e}")

    def _step_arcs_update(
        self,
        events: List[Dict[str, Any]],
        session: Any,
        trace: TurnTrace,
    ) -> List[Dict[str, Any]]:
        """Step 8: Update story arcs from events.

        Args:
            events: Events to process.
            session: Game session.
            trace: Trace to record results.

        Returns:
            Arc update events.
        """
        arc_updates = []
        try:
            if self.arc_manager and hasattr(self.arc_manager, "update_arcs"):
                arc_updates = self.arc_manager.update_arcs(events)
                trace.arcs_updated = list(arc_updates)
        except Exception as e:
            trace.add_error(f"Arc update failed: {e}")

        # Also update StoryDirector arcs
        try:
            if self.director and hasattr(self.director, "update"):
                self.director.update(session, events)
        except Exception as e:
            trace.add_error(f"Director update failed: {e}")

        return arc_updates

    def _step_scene_update(
        self,
        events: List[Dict[str, Any]],
        trace: TurnTrace,
    ) -> None:
        """Step 8b: Update scene manager with events.

        Args:
            events: Events to process.
            trace: Trace to record results.
        """
        try:
            if self.scene_manager and hasattr(self.scene_manager, "update_scene"):
                self.scene_manager.update_scene(events)
        except Exception as e:
            trace.add_error(f"Scene update failed: {e}")

    # --------------------------------------------------------
    # Utility Methods
    # --------------------------------------------------------

    def _safe_list(self, obj: Any) -> list:
        """Safely convert to list.

        Args:
            obj: Object to convert.

        Returns:
            List representation.
        """
        if obj is None:
            return []
        if isinstance(obj, list):
            return obj
        return [obj]

    def get_last_trace(self) -> Optional[TurnTrace]:
        """Get the most recent turn trace.

        Returns:
            Most recent TurnTrace, or None.
        """
        return self.trace_history[-1] if self.trace_history else None

    def get_last_feedback(self) -> Optional[Dict[str, Any]]:
        """Get the last Director feedback.

        Returns:
            Feedback dict, or None.
        """
        return self._last_feedback

    def get_planning_context(self, session: Any) -> str:
        """Get context string for Director planning.

        Combines arcs, resources, and feedback into a single block.

        Args:
            session: Game session.

        Returns:
            Context string for Director prompt.
        """
        return build_director_planning_context(
            session=session,
            arc_manager=self.arc_manager,
            resource_manager=self.resource_manager,
            feedback=self._last_feedback,
        )

    def reset(self) -> None:
        """Reset pipeline state."""
        self.trace_history.clear()
        self._last_feedback = None
        self._turn_counter = 0


def create_default_pipeline(**kwargs) -> ExecutionPipeline:
    """Create an ExecutionPipeline with sensible defaults.

    Args:
        **kwargs: Override any pipeline component.

    Returns:
        Configured ExecutionPipeline.
    """
    return ExecutionPipeline(
        resolver=kwargs.get("resolver"),
        scene_manager=kwargs.get("scene_manager"),
        resource_manager=kwargs.get("resource_manager"),
        executor=kwargs.get("executor"),
        world=kwargs.get("world"),
        memory_manager=kwargs.get("memory_manager"),
        arc_manager=kwargs.get("arc_manager"),
        director=kwargs.get("director"),
        enable_trace=kwargs.get("enable_trace", True),
    )