"""Plot Engine — Long-term narrative structure and quest management.

This module implements PART 1 of Tier 6 (Narrative Intelligence Systems)
from the RPG design specification: the Plot Engine.

Purpose:
    Manages long-term story structure (setup → buildup → payoff),
    persistent quests, and arc progression over time. This gives the
    narrative a sense of direction — stories actually go somewhere.

The Problem:
    The current system generates events, shapes tension, produces dialogue —
    but lacks setup → buildup → payoff structures, persistent goals,
    and resolution tracking.

The Solution:
    PlotEngine wraps StoryArcManager, adds Quest management, and provides
    a unified interface for long-term narrative progression. It tracks
    setups awaiting payoffs, quest objectives, and arc-driven event injection.

Usage:
    engine = PlotEngine()
    engine.add_arc("defeat_dragon", "Defeat the Dragon", {"player", "dragon"})
    engine.add_quest("find_sword", "Find the Ancient Sword",
                     objectives=["go_to_cave", "defeat_guardian", "take_sword"])
    
    # Each tick:
    engine.update(events)
    injected = engine.generate_arc_events()
    events.extend(injected)

Architecture:
    PlotEngine
    ├── StoryArcManager (from narrative.story_arc)
    ├── QuestManager (this module)
    ├── SetupTracker (this module)
    └── EventInjector (this module)

Integration:
    - PlayerLoop: Updates plot engine, injects arc events
    - AgencySystem: Flags advance arcs (betrayed_faction → arc progress)
    - StoryDirector: Arc summaries inform Director decisions
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from rpg.narrative.story_arc import StoryArc, StoryArcManager


@dataclass
class Quest:
    """A player-facing or system-tracked objective with completion criteria.
    
    Quests differ from arcs in that arcs are narrative structure
    (internal story progression) while quests are concrete objectives
    with checkable conditions.
    
    Attributes:
        id: Unique quest identifier.
        title: Human-readable quest name.
        description: Detailed quest description.
        status: Current status (active, completed, failed).
        objectives: List of objective dicts with 'id', 'description', 'completed'.
        completion_conditions: Conditions that mark quest complete.
        related_arc_id: Arc this quest advances, if any.
        rewards: Rewards granted on completion.
        created_at: Tick when quest was created.
    """
    
    id: str
    title: str
    description: str = ""
    status: str = "active"  # active | completed | failed
    objectives: List[Dict[str, Any]] = field(default_factory=list)
    completion_conditions: List[Dict[str, Any]] = field(default_factory=list)
    related_arc_id: Optional[str] = None
    rewards: Dict[str, Any] = field(default_factory=dict)
    created_at: int = 0
    
    def add_objective(self, obj_id: str, description: str, 
                      completed: bool = False) -> None:
        """Add an objective to this quest.
        
        Args:
            obj_id: Unique objective ID within this quest.
            description: What the player must do.
            completed: Whether already completed.
        """
        self.objectives.append({
            "id": obj_id,
            "description": description,
            "completed": completed,
        })
        
    def complete_objective(self, obj_id: str) -> bool:
        """Mark an objective as completed.
        
        Args:
            obj_id: Objective to complete.
            
        Returns:
            True if objective was found and completed.
        """
        for obj in self.objectives:
            if obj["id"] == obj_id:
                obj["completed"] = True
                return True
        return False
        
    def check_completion(self) -> bool:
        """Check if all objectives are complete.
        
        Returns:
            True if all objectives completed.
        """
        if not self.objectives:
            return self.status == "completed"
        return all(obj.get("completed", False) for obj in self.objectives)
        
    def progress_fraction(self) -> float:
        """Get quest progress as 0.0-1.0.
        
        Returns:
            Fraction of objectives completed.
        """
        if not self.objectives:
            return 0.0
        completed = sum(1 for obj in self.objectives if obj.get("completed", False))
        return completed / len(self.objectives)
        
    def to_dict(self) -> Dict[str, Any]:
        """Serialize quest to dict.
        
        Returns:
            Quest data as dictionary.
        """
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "status": self.status,
            "objectives": self.objectives,
            "progress": self.progress_fraction(),
            "related_arc_id": self.related_arc_id,
            "rewards": self.rewards,
        }


@dataclass
class Setup:
    """A narrative setup awaiting a future payoff.
    
    Setups are things the narrative establishes that should pay off later:
    a hinted weakness, a foreshadowed event, a planted clue.
    
    Attributes:
        id: Unique setup identifier.
        description: What was established.
        payoff_trigger: Event type that fulfills this setup.
        payoff_description: What happens when payoff triggers.
        arc_id: Arc this setup belongs to.
        fulfilled: Whether payoff has triggered.
        created_at: Tick when setup was created.
        max_age: Maximum ticks before setup expires (0 = no expiry).
    """
    
    id: str
    description: str
    payoff_trigger: str
    payoff_description: str = ""
    arc_id: Optional[str] = None
    fulfilled: bool = False
    created_at: int = 0
    max_age: int = 0  # 0 = no expiry
        
    def to_dict(self) -> Dict[str, Any]:
        """Serialize setup to dict.
        
        Returns:
            Setup data as dictionary.
        """
        return {
            "id": self.id,
            "description": self.description,
            "payoff_trigger": self.payoff_trigger,
            "payoff_description": self.payoff_description,
            "arc_id": self.arc_id,
            "fulfilled": self.fulfilled,
            "age": self.created_at,
        }


class QuestManager:
    """Manages player-facing quests with objectives and rewards.
    
    The QuestManager tracks concrete goals the player can pursue.
    Unlike arcs (which are narrative structure), quests are actionable
    objectives with checkable conditions.
    
    Usage:
        manager = QuestManager()
        manager.add_quest("find_sword", "Find the Ancient Sword")
        manager.complete_objective("find_sword", "defeat_guardian")
        quests = manager.get_active_quests()
    """
    
    def __init__(self):
        """Initialize the QuestManager."""
        self.quests: Dict[str, Quest] = {}
        self._quest_counter = 0
        
    def add_quest(self, quest: Quest) -> Quest:
        """Add a quest to the manager.
        
        Args:
            quest: Quest instance to add.
            
        Returns:
            The added quest.
        """
        self.quests[quest.id] = quest
        return quest
        
    def create_quest(
        self,
        quest_id: str,
        title: str,
        description: str = "",
        objectives: Optional[List[Dict[str, Any]]] = None,
        related_arc_id: Optional[str] = None,
        rewards: Optional[Dict[str, Any]] = None,
    ) -> Quest:
        """Create and register a new quest.
        
        Args:
            quest_id: Unique quest identifier.
            title: Quest name.
            description: Quest description.
            objectives: List of objective dicts.
            related_arc_id: Arc this quest relates to.
            rewards: Rewards granted on completion.
            
        Returns:
            Newly created Quest instance.
        """
        self._quest_counter += 1
        
        quest = Quest(
            id=quest_id,
            title=title,
            description=description,
            objectives=objectives or [],
            related_arc_id=related_arc_id,
            rewards=rewards or {},
        )
        
        self.quests[quest.id] = quest
        return quest
        
    def complete_objective(self, quest_id: str, objective_id: str) -> bool:
        """Mark an objective as completed.
        
        Args:
            quest_id: Quest containing the objective.
            objective_id: Objective to complete.
            
        Returns:
            True if objective was completed.
        """
        quest = self.quests.get(quest_id)
        if not quest or quest.status != "active":
            return False
            
        completed = quest.complete_objective(objective_id)
        
        # Check if quest is now fully complete
        if completed and quest.check_completion():
            quest.status = "completed"
            
        return completed
        
    def fail_quest(self, quest_id: str) -> bool:
        """Mark a quest as failed.
        
        Args:
            quest_id: Quest to fail.
            
        Returns:
            True if quest was found and set to failed.
        """
        quest = self.quests.get(quest_id)
        if not quest or quest.status != "active":
            return False
        
        quest.status = "failed"
        return True
        
    def update_quests(self, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Update all active quests based on recent events.
        
        Scans events for objective completions and quest condition checks.
        
        Args:
            events: Recent event dicts to process.
            
        Returns:
            List of quests that changed status (completed/failed).
        """
        changes = []
        
        for quest_id, quest in self.quests.items():
            if quest.status != "active":
                continue
                
            # Check each pending objective for auto-completion
            for obj in quest.objectives:
                if obj.get("completed"):
                    continue
                    
                # Check if any event completes this objective
                for event in events:
                    if self._event_completes_objective(event, obj, quest):
                        obj["completed"] = True
                        changes.append({
                            "type": "objective_completed",
                            "quest_id": quest_id,
                            "objective_id": obj["id"],
                            "quest_title": quest.title,
                        })
                        
            # Check overall quest completion
            if quest.check_completion():
                quest.status = "completed"
                changes.append({
                    "type": "quest_completed",
                    "quest_id": quest_id,
                    "title": quest.title,
                    "rewards": quest.rewards,
                })
                
        return changes
        
    def _event_completes_objective(
        self, event: Dict[str, Any], objective: Dict[str, Any], quest: Quest
    ) -> bool:
        """Check if an event completes a quest objective.
        
        Args:
            event: Event dict to check.
            objective: Objective dict to complete.
            quest: Parent quest for context.
            
        Returns:
            True if event completes objective.
        """
        event_type = event.get("type", "")
        obj_id = objective.get("id", "")
        
        # Direct match: event type matches objective id
        if event_type == obj_id:
            return True
            
        # Keyword match: event type contains objective keywords
        obj_desc = objective.get("description", "").lower()
        keywords = obj_desc.split()
        for kw in keywords:
            if len(kw) > 3 and kw in event_type:
                return True
                
        return False
        
    def get_active_quests(self) -> List[Quest]:
        """Get all active quests.
        
        Returns:
            List of active Quest instances.
        """
        return [q for q in self.quests.values() if q.status == "active"]
        
    def get_completed_quests(self) -> List[Quest]:
        """Get all completed quests.
        
        Returns:
            List of completed Quest instances.
        """
        return [q for q in self.quests.values() if q.status == "completed"]
        
    def get_quest_summary(self) -> str:
        """Get formatted quest summary for display.
        
        Returns:
            Multi-line string summarizing active and completed quests.
        """
        lines = ["=== Quests ==="]
        
        active = self.get_active_quests()
        if active:
            for quest in active:
                pct = int(quest.progress_fraction() * 100)
                lines.append(f"  ⬡ {quest.title} [{pct}%]")
                for obj in quest.objectives:
                    status = "✓" if obj.get("completed") else "○"
                    lines.append(f"    [{status}] {obj['description']}")
        else:
            lines.append("  No active quests")
            
        completed = self.get_completed_quests()
        if completed:
            lines.append("Completed:")
            for quest in completed[-5:]:
                lines.append(f"  ✓ {quest.title}")
                
        return "\n".join(lines)
        
    def reset(self) -> None:
        """Clear all quest data."""
        self.quests.clear()
        self._quest_counter = 0


class SetupTracker:
    """Tracks narrative setups and their payoffs.
    
    The SetupTracker manages the setup → payoff pattern that makes
    stories feel planned and satisfying. When a setup is created,
    it waits for a matching payoff event to trigger.
    
    Usage:
        tracker = SetupTracker()
        tracker.add_setup("dragon_weakness", "dragon_fire_resistance",
                         payoff_trigger="player_uses_ice_weapon")
        
        # Later, when player uses ice weapon:
        payoffs = tracker.check_payoffs(events)
        # → Returns the dragon_weakness setup payoff
    """
    
    def __init__(self):
        """Initialize the SetupTracker."""
        self.setups: Dict[str, Setup] = {}
        self._setup_counter = 0
        
    def add_setup(
        self,
        setup_id: str,
        description: str,
        payoff_trigger: str,
        payoff_description: str = "",
        arc_id: Optional[str] = None,
        max_age: int = 0,
    ) -> Setup:
        """Add a narrative setup awaiting payoff.
        
        Args:
            setup_id: Unique setup identifier.
            description: What the narrative established.
            payoff_trigger: Event type that fulfills this setup.
            payoff_description: Description of the payoff event.
            arc_id: Arc this setup belongs to.
            max_age: Ticks until this setup expires (0 = no expiry).
            
        Returns:
            The created Setup instance.
        """
        self._setup_counter += 1
        
        setup = Setup(
            id=setup_id,
            description=description,
            payoff_trigger=payoff_trigger,
            payoff_description=payoff_description or description,
            arc_id=arc_id,
            max_age=max_age,
        )
        
        self.setups[setup_id] = setup
        return setup
        
    def check_payoffs(self, events: List[Dict[str, Any]]) -> List[Setup]:
        """Check if any setups have been fulfilled by recent events.
        
        Args:
            events: Recent event dicts to process.
            
        Returns:
            List of setups that were fulfilled by these events.
        """
        fulfilled = []
        
        for event in events:
            event_type = event.get("type", "")
            
            for setup_id, setup in self.setups.items():
                if setup.fulfilled:
                    continue
                    
                if event_type == setup.payoff_trigger:
                    setup.fulfilled = True
                    fulfilled.append(setup)
                    
        return fulfilled
        
    def update(self) -> List[str]:
        """Tick down setup ages and remove expired ones.
        
        Returns:
            List of IDs of setups that expired.
        """
        expired = []
        
        for setup_id, setup in list(self.setups.items()):
            if setup.max_age > 0:
                setup.created_at += 1
                if setup.created_at >= setup.max_age and not setup.fulfilled:
                    expired.append(setup_id)
                    del self.setups[setup_id]
                    
        return expired
        
    def get_pending_setups(self) -> List[Setup]:
        """Get all setups that haven't been fulfilled or expired.
        
        Returns:
            List of pending Setup instances.
        """
        return [s for s in self.setups.values() if not s.fulfilled]
        
    def get_setup_summary(self) -> str:
        """Get formatted setup summary for display.
        
        Returns:
            Multi-line string of pending setups.
        """
        pending = self.get_pending_setups()
        if not pending:
            return "No pending setups"
            
        lines = ["=== Pending Setups ==="]
        for setup in pending:
            lines.append(f"  → {setup.description}")
            lines.append(f"    Payoff: {setup.payoff_description}")
        return "\n".join(lines)
        
    def reset(self) -> None:
        """Clear all setup data."""
        self.setups.clear()
        self._setup_counter = 0


class PlotEngine:
    """Main plot engine managing arcs, quests, and setups/payoffs.
    
    The PlotEngine is the central coordinator for long-term narrative
    structure. It combines:
    - StoryArcManager: Persistent story arcs with progress tracking
    - QuestManager: Player-facing objectives with completion criteria
    - SetupTracker: Setup → payoff narrative patterns
    
    Integration with AgencySystem:
    When the player makes a consequential choice, the agency flags
    can advance arcs, complete quest objectives, or trigger payoffs.
    
    Usage:
        engine = PlotEngine()
        
        # Setup stories
        engine.add_arc("defeat_dragon", "Defeat the Dragon", 
                      {"player", "dragon"}, priority=2.0)
        engine.create_quest("find_sword", "Find the Ancient Sword",
                          objectives=[
                              {"id": "learn_location", "description": "Learn sword location"},
                              {"id": "travel_to_cave", "description": "Travel to the cave"},
                              {"id": "defeat_guardian", "description": "Defeat the cave guardian"},
                          ], related_arc_id="defeat_dragon")
        
        # Each game tick:
        engine.update(events)
        arc_events = engine.generate_arc_events()
        events.extend(arc_events)
    """
    
    def __init__(self):
        """Initialize the PlotEngine."""
        self.arc_manager = StoryArcManager()
        self.quest_manager = QuestManager()
        self.setup_tracker = SetupTracker()
        self._tick = 0
        
        # Arc-to-agency flag mappings
        self._arc_flag_boosts: Dict[str, List[str]] = {}
        
    def add_arc(
        self,
        arc_id: str,
        goal: str,
        entities: Set[str],
        progress: float = 0.0,
        tags: Optional[List[str]] = None,
        dependency: Optional[str] = None,
        priority: float = 1.0,
    ) -> StoryArc:
        """Create and register a story arc.
        
        Args:
            arc_id: Unique arc identifier.
            goal: Arc objective.
            entities: Entity IDs involved.
            progress: Initial progress (0.0-1.0).
            tags: Arc tags.
            dependency: Arc ID that must complete first.
            priority: Arc importance.
            
        Returns:
            Newly created StoryArc.
        """
        arc = self.arc_manager.create_arc(
            goal=goal,
            entities=entities,
            arc_id=arc_id,
            progress=progress,
            tags=tags,
            dependency=dependency,
            priority=priority,
        )
        return arc
        
    def add_quest(
        self,
        quest_id: str,
        title: str,
        description: str = "",
        objectives: Optional[List[Dict[str, Any]]] = None,
        related_arc_id: Optional[str] = None,
        rewards: Optional[Dict[str, Any]] = None,
    ) -> Quest:
        """Create and register a quest.
        
        Args:
            quest_id: Unique quest identifier.
            title: Quest name.
            description: Quest description.
            objectives: List of objective dicts.
            related_arc_id: Arc this quest advances.
            rewards: Rewards on completion.
            
        Returns:
            Newly created Quest.
        """
        return self.quest_manager.create_quest(
            quest_id=quest_id,
            title=title,
            description=description,
            objectives=objectives,
            related_arc_id=related_arc_id,
            rewards=rewards,
        )
        
    def add_setup(
        self,
        setup_id: str,
        description: str,
        payoff_trigger: str,
        payoff_description: str = "",
        arc_id: Optional[str] = None,
    ) -> Setup:
        """Add a narrative setup awaiting payoff.
        
        Args:
            setup_id: Setup identifier.
            description: What was established.
            payoff_trigger: Event type that fulfills this.
            payoff_description: Payoff description.
            arc_id: Related arc ID.
            
        Returns:
            Created Setup instance.
        """
        return self.setup_tracker.add_setup(
            setup_id=setup_id,
            description=description,
            payoff_trigger=payoff_trigger,
            payoff_description=payoff_description,
            arc_id=arc_id,
        )
        
    def register_arc_flag_boost(self, arc_id: str, flags: List[str]) -> None:
        """Register agency flags that boost arc progress.
        
        When any of these flags are set, the arc gets a progress boost.
        This connects player agency (their choices) to plot progression.
        
        Args:
            arc_id: Arc to boost.
            flags: List of agency flag keys that trigger boost.
        """
        self._arc_flag_boosts[arc_id] = flags
        
    def update(self, events: List[Dict[str, Any]], 
               agency_flags: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Update all plot systems with recent events.
        
        This should be called each game tick after the world tick.
        
        Pipeline:
        1. Update story arcs from events
        2. Update quests from events
        3. Check setup payoffs
        4. Apply agency flag boosts to arcs
        5. Tick down setup ages
        
        Args:
            events: Recent world events.
            agency_flags: Current agency system flags.
            
        Returns:
            Dict with update results:
            - arc_completions: List of completed arc events
            - quest_changes: List of quest status changes
            - payoff_setups: List of fulfilled setups
            - injected_events: Arc-driven events to add
        """
        self._tick += 1
        
        # 1. Update arcs
        arc_completions = self.arc_manager.update_arcs(events)
        
        # 2. Update quests
        quest_changes = self.quest_manager.update_quests(events)
        
        # 3. Check setup payoffs
        payoff_setups = self.setup_tracker.check_payoffs(events)
        
        # 4. Apply agency flag boosts
        if agency_flags:
            self._apply_agency_boosts(agency_flags)
            
        # 5. Tick setups
        self.setup_tracker.update()
        
        # 6. Generate arc-driven events
        injected_events = self.generate_arc_events()
        
        return {
            "arc_completions": arc_completions,
            "quest_changes": quest_changes,
            "payoff_setups": payoff_setups,
            "injected_events": injected_events,
        }
        
    def _apply_agency_boosts(self, agency_flags: Dict[str, Any]) -> None:
        """Boost arc progress based on agency flags.
        
        This is the critical link between player choices (agency)
        and story progression (plot). When the player does something
        meaningful (kills a key NPC, betrays a faction), relevant
        arcs advance.
        
        Args:
            agency_flags: AgencySystem.flags dict.
        """
        for arc_id, boost_flags in self._arc_flag_boosts.items():
            arc = self.arc_manager.arcs.get(arc_id) if hasattr(self.arc_manager, 'arcs') else None
            
            # Find the arc in active_arcs
            if arc is None:
                for check_arc in self.arc_manager.active_arcs:
                    if check_arc.id == arc_id:
                        arc = check_arc
                        break
                        
            if arc is None or arc.completed:
                continue
                
            for flag_key in boost_flags:
                if agency_flags.get(flag_key):
                    arc.progress = min(1.0, arc.progress + 0.1)
                    
    def generate_arc_events(self) -> List[Dict[str, Any]]:
        """Generate narrative events from arc state.
        
        Arcs in climax phase generate major conflict events.
        Arcs nearing completion generate build-up events.
        
        Returns:
            List of event dicts to inject into the event stream.
        """
        events = []
        
        for arc in self.arc_manager.active_arcs:
            # Get phase — handle existing StoryArc that may not have 'phase' attribute
            arc_phase = getattr(arc, 'phase', self._compute_phase(arc.progress))
            arc_completed = getattr(arc, 'completed', False)
            arc_goal = getattr(arc, 'goal', arc.id)
            
            if arc_phase == "climax":
                events.append({
                    "type": "major_conflict",
                    "arc_id": arc.id,
                    "importance": 0.9,
                    "description": f"The {arc_goal} reaches its climax",
                })
            elif arc.progress > 0.5 and arc_phase == "rising":
                events.append({
                    "type": "story_buildup",
                    "arc_id": arc.id,
                    "importance": 0.6,
                    "description": f"Events surrounding {arc_goal} escalate",
                })
            elif arc.progress > 0.8 and not arc_completed:
                events.append({
                    "type": "story_approaching_resolution",
                    "arc_id": arc.id,
                    "importance": 0.7,
                    "description": f"The {arc_goal} nears its conclusion",
                })
                
        return events

    def _compute_phase(self, progress: float) -> str:
        """Compute arc phase from progress for StoryArcs without phase attr.
        
        Args:
            progress: Arc progress (0.0-1.0).
            
        Returns:
            Phase string: setup, rising, climax, or resolution.
        """
        if progress < 0.3:
            return "setup"
        elif progress < 0.7:
            return "rising"
        elif progress < 1.0:
            return "climax"
        return "resolution"
        
    def get_summary(self) -> str:
        """Get comprehensive plot state summary.
        
        Returns:
            Multi-line string with arcs, quests, and setups.
        """
        parts = [
            self.arc_manager.get_summary_for_director(),
            self.quest_manager.get_quest_summary(),
            self.setup_tracker.get_setup_summary(),
        ]
        
        return "\n\n".join(p for p in parts if p)
        
    def get_narrative_context(self) -> Dict[str, Any]:
        """Get narrative context for Director/LLM prompts.
        
        Returns:
            Dict with active arc summaries, quest state, etc.
        """
        return {
            "tick": self._tick,
            "active_arcs": self.arc_manager.get_active_arc_summaries(),
            "quests": self.quest_manager.get_active_quests(),
            "pending_setups": [s.to_dict() for s in self.setup_tracker.get_pending_setups()],
            "most_urgent_arc": (
                self.arc_manager.get_most_urgent_arc().to_dict()
                if self.arc_manager.get_most_urgent_arc()
                else None
            ),
        }
        
    def get_direct_prompt_injection(self) -> str:
        """Format all plot state for Director prompt injection.
        
        Returns:
            Formatted string for AI Director prompt.
        """
        lines = ["=== PLOT ENGINE STATE ==="]
        
        # Arcs
        lines.append(self.arc_manager.get_summary_for_director())
        lines.append("")
        
        # Quests
        lines.append(self.quest_manager.get_quest_summary())
        lines.append("")
        
        # Urgent arc callout
        urgent = self.arc_manager.get_most_urgent_arc()
        if urgent:
            pct = int(urgent.progress * 100)
            lines.append(f"⚠ URGENT: {urgent.goal} [{pct}%] needs Director attention")
            
        return "\n".join(lines)
        
    def reset(self) -> None:
        """Reset all plot engine state."""
        self.arc_manager.reset()
        self.quest_manager.reset()
        self.setup_tracker.reset()
        self._tick = 0
        self._arc_flag_boosts.clear()