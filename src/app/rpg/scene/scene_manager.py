"""Scene Manager — Narrative scene structure and pacing layer.

This module implements PATCH 5 from rpg-design.txt:
"Add Scene / Narrative Structure Layer"

The Problem: Continuous event stream with no scene boundaries.
The Solution: A Scene Manager that structures narrative into scenes
with goals, participants, and progress tracking.

Architecture:
    Scene(goal, participants) →
        Track progress →
        Director triggers new scene on completion

Usage:
    manager = SceneManager()
    scene = manager.new_scene("Escape the dungeon", ["player", "guard"])
    manager.update_progress(scene, events)
    if scene.is_complete():
        new_scene = manager.advance_scene()

Design Compliance:
    - Scenes with explicit goals
    - Scene transitions
    - Pacing control
    - Director integration for scene changes
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Set


class Scene:
    """A narrative scene with goals and participants.
    
    Scenes are the building blocks of the story. Each scene has:
    - A clear goal/objective
    - Active participants
    - Progress toward completion
    - Optional time limits
    
    Attributes:
        id: Unique scene identifier.
        goal: The scene's objective.
        participants: Entity IDs participating in the scene.
        progress: Float progress toward goal completion (0.0-1.0+).
        created_at: Timestamp when scene was created.
        completed: Whether scene has been completed.
        tags: Scene tags for categorization.
        events: Events that occurred during this scene.
    """
    
    def __init__(
        self,
        goal: str,
        participants: Optional[Set[str]] = None,
        scene_id: Optional[str] = None,
        max_progress: float = 1.0,
        tags: Optional[List[str]] = None,
    ):
        """Initialize a Scene.
        
        Args:
            goal: Scene objective description.
            participants: Entity IDs participating in scene.
            scene_id: Unique identifier (auto-generated if None).
            max_progress: Progress threshold for completion.
            tags: Scene categorization tags.
        """
        self.id = scene_id or f"scene_{id(self)}"
        self.goal = goal
        self.participants = participants or set()
        self.progress = 0.0
        self.max_progress = max_progress
        self.created_at = time.time()
        self.completed = False
        self.tags = tags or []
        self.events: List[Dict[str, Any]] = []
        
        # Scene mood/atmosphere
        self.mood = "neutral"
        self.description = ""
        
    def add_event(self, event: Dict[str, Any]) -> float:
        """Record an event and update progress.
        
        Events contribute to scene progress based on their type
        and relevance to the scene goal.
        
        Args:
            event: Event dict to record.
            
        Returns:
            Progress delta from this event.
        """
        self.events.append(event)
        delta = self._calculate_event_progress(event)
        self.progress += delta
        return delta
        
    def _calculate_event_progress(self, event: Dict[str, Any]) -> float:
        """Calculate how much an event contributes to scene progress.
        
        Args:
            event: Event dict to evaluate.
            
        Returns:
            Progress delta (0.0-0.3 per event).
        """
        etype = event.get("type", "")
        
        # Action events contribute more
        if etype in ("damage", "death", "critical_hit"):
            return 0.15
        elif etype in ("attack", "combat"):
            return 0.1
        elif etype in ("speak", "dialogue"):
            # Dialogue events that involve participants contribute
            speaker = event.get("speaker", event.get("source", ""))
            target = event.get("target", "")
            if speaker in self.participants or target in self.participants:
                return 0.05
        elif etype == "move":
            # Movement toward goal
            return 0.05
        elif etype == "story_event":
            # Director-injected story beats always contribute
            return 0.1
            
        return 0.02  # Minimal progress for other events
        
    def is_complete(self) -> bool:
        """Check if scene goal has been achieved.
        
        Returns:
            True if progress meets or exceeds max_progress.
        """
        if not self.completed and self.progress >= self.max_progress:
            self.completed = True
        return self.completed
        
    def update_participants(self, participants: Set[str]) -> None:
        """Update scene participants.
        
        Args:
            participants: New set of participant entity IDs.
        """
        self.participants = participants
        
    def add_participant(self, entity_id: str) -> None:
        """Add a participant to the scene.
        
        Args:
            entity_id: Entity ID to add.
        """
        self.participants.add(entity_id)
        
    def remove_participant(self, entity_id: str) -> None:
        """Remove a participant from the scene.
        
        Args:
            entity_id: Entity ID to remove.
        """
        self.participants.discard(entity_id)
        
    # =========================================================
    # PATCH 6: SCENE CONSTRAINTS (actions limited by scene context)
    # =========================================================
    
    def get_allowed_actions(self) -> List[str]:
        """Get list of action types allowed in this scene.
        
        Scenes constrain what actions are available based on their
        goal and context. This prevents inappropriate actions
        from being taken in certain contexts.
        
        Returns:
            List of allowed action type strings.
        """
        # Default: all actions allowed
        allowed = ["attack", "defend", "move", "speak", "wander", 
                   "observe", "flee", "heal"]
                   
        # Stealth scenes restrict violent actions
        if "stealth" in self.tags or "stealth" in self.goal.lower():
            allowed = ["move", "hide", "observe", "speak"]
            
        # Combat scenes restrict non-combat actions
        elif "combat" in self.tags or "combat" in self.goal.lower():
            allowed = ["attack", "defend", "flee", "heal"]
            
        # Social scenes restrict aggressive actions
        elif "social" in self.tags or "dialogue" in self.goal.lower():
            allowed = ["speak", "observe", "persuade"]
            
        # Exploration scenes restrict combat
        elif "explore" in self.tags or "explore" in self.goal.lower():
            allowed = ["move", "observe", "pick_up"]
            
        return allowed
        
    def is_action_allowed(self, action_type: str) -> bool:
        """Check if a specific action is allowed in this scene.
        
        Args:
            action_type: Action type to check.
            
        Returns:
            True if action is allowed.
        """
        allowed = self.get_allowed_actions()
        
        # Wildcard allows everything
        if "*" in allowed:
            return True
            
        return action_type in allowed
        
    def filter_actions(self, actions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filter a list of actions to only include allowed ones.
        
        Args:
            actions: List of action dicts.
            
        Returns:
            Filtered list of only allowed actions.
        """
        if not actions:
            return []
            
        allowed = self.get_allowed_actions()
        if "*" in allowed:
            return actions
            
        return [
            action for action in actions
            if action.get("action") in allowed
        ]
        
    def to_dict(self) -> Dict[str, Any]:
        """Serialize scene to dict.
        
        Returns:
            Scene data as dict.
        """
        return {
            "id": self.id,
            "goal": self.goal,
            "participants": list(self.participants),
            "progress": round(self.progress, 3),
            "max_progress": self.max_progress,
            "completed": self.completed,
            "tags": self.tags,
            "mood": self.mood,
            "description": self.description,
            "event_count": len(self.events),
        }
        
    def summary(self) -> str:
        """Get human-readable scene summary.
        
        Returns:
            One-line scene summary.
        """
        status = "COMPLETE" if self.completed else "IN PROGRESS"
        pct = min(100, int((self.progress / max(self.max_progress, 0.01)) * 100))
        return (
            f"[{status}] {self.goal} "
            f"({pct}%, {len(self.participants)} participants)"
        )


class SceneManager:
    """Manages narrative scenes and their progression.
    
    The SceneManager:
    - Creates scenes with goals
    - Tracks scene progress based on events
    - Handles scene transitions
    - Provides scene context to other systems
    
    Scene Lifecycle:
    1. Create scene with goal
    2. Feed events to update progress
    3. Scene completes when progress threshold reached
    4. Transition to next scene
    
    Attributes:
        current_scene: The active scene.
        scene_history: Completed scenes.
        scene_templates: Pre-defined scene templates.
    """
    
    def __init__(self):
        """Initialize SceneManager."""
        self.current_scene: Optional[Scene] = None
        self.scene_history: List[Scene] = []
        self.scene_templates: Dict[str, Dict[str, Any]] = {}
        self._scene_counter = 0
        
        # Scene pacing
        self._minimum_scene_time = 5.0  # Minimum seconds per scene
        self._max_scenes_in_history = 20
        
    def new_scene(
        self,
        goal: str,
        participants: Optional[Set[str]] = None,
        tags: Optional[List[str]] = None,
        max_progress: float = 1.0,
    ) -> Scene:
        """Create and activate a new scene.
        
        If there's a current scene, it's archived to history.
        
        Args:
            goal: Scene objective.
            participants: Participating entity IDs.
            tags: Scene categorization tags.
            max_progress: Progress threshold for completion.
            
        Returns:
            The newly created Scene.
        """
        # Archive current scene
        if self.current_scene:
            self.scene_history.append(self.current_scene)
            if len(self.scene_history) > self._max_scenes_in_history:
                self.scene_history = self.scene_history[-self._max_scenes_in_history:]
                
        self._scene_counter += 1
        self.current_scene = Scene(
            goal=goal,
            participants=participants,
            scene_id=f"scene_{self._scene_counter}",
            max_progress=max_progress,
            tags=tags,
        )
        
        return self.current_scene
        
    def new_scene_from_events(
        self,
        events: List[Dict[str, Any]],
        default_participants: Optional[Set[str]] = None,
    ) -> Optional[Scene]:
        """Create a scene inferred from recent events.
        
        Analyzes events to determine a natural scene goal
        and participants.
        
        Args:
            events: Recent events to analyze.
            default_participants: Fallback participants.
            
        Returns:
            New Scene, or None if no scene can be inferred.
        """
        if not events:
            return None
            
        # Extract participants from events
        participants: Set[str] = default_participants or set()
        for event in events:
            for key in ("source", "target", "actor", "speaker", "entity"):
                val = event.get(key, "")
                if val and isinstance(val, str):
                    participants.add(val)
                    
        # Determine scene goal from event patterns
        goal = self._infer_goal_from_events(events)
        
        # Determine tags
        tags = self._extract_event_types(events)
        
        return self.new_scene(
            goal=goal,
            participants=participants,
            tags=tags,
        )
        
    def _infer_goal_from_events(self, events: List[Dict[str, Any]]) -> str:
        """Infer a scene goal from event patterns.
        
        Args:
            events: Events to analyze.
            
        Returns:
            Inferred goal string.
        """
        event_types = set(e.get("type", "") for e in events)
        
        if "death" in event_types or "damage" in event_types:
            return "Survive the encounter"
        elif "speak" in event_types:
            return "Navigate the conversation"
        elif "move" in event_types:
            return "Reach the destination"
        elif "story_event" in event_types:
            summaries = [e.get("summary", "") for e in events if e.get("type") == "story_event"]
            if summaries:
                return summaries[-1][:100]  # Use last story event summary
        return "Progress the story"
        
    def _extract_event_types(self, events: List[Dict[str, Any]]) -> List[str]:
        """Extract unique event types from events list.
        
        Args:
            events: Events to analyze.
            
        Returns:
            List of event type strings.
        """
        types = set()
        for event in events:
            etype = event.get("type", "")
            if etype:
                types.add(etype)
        return list(types)
        
    def update_scene(self, events: List[Dict[str, Any]]) -> None:
        """Feed events to current scene for progress tracking.
        
        Args:
            events: Events to process.
        """
        if not self.current_scene:
            return
            
        for event in events:
            self.current_scene.add_event(event)
            
        # Also update participants from events
        for event in events:
            for key in ("source", "target", "actor", "speaker", "entity"):
                val = event.get(key, "")
                if val:
                    self.current_scene.add_participant(val)
                    
    def is_scene_complete(self) -> bool:
        """Check if current scene has completed.
        
        Returns:
            True if scene should transition.
        """
        if not self.current_scene:
            return False
        return self.current_scene.is_complete()
        
    def advance_scene(
        self,
        new_goal: str = "",
        participants: Optional[Set[str]] = None,
        tags: Optional[List[str]] = None,
    ) -> Optional[Scene]:
        """Force scene transition.
        
        Archives the current scene and creates a new one.
        
        Args:
            new_goal: Goal for the new scene.
            participants: Participants for the new scene.
            tags: Tags for the new scene.
            
        Returns:
            The new Scene, or None if no goal provided.
        """
        if not new_goal:
            new_goal = "Continue the story"
            
        return self.new_scene(
            goal=new_goal,
            participants=participants,
            tags=tags,
        )
        
    def get_scene_context(self) -> Optional[Dict[str, Any]]:
        """Get current scene context for LLM prompts.
        
        Returns:
            Dict with scene information for prompt building.
        """
        if not self.current_scene:
            return None
            
        return {
            "current_scene": self.current_scene.goal,
            "scene_progress": round(
                min(1.0, self.current_scene.progress / max(self.current_scene.max_progress, 0.01)),
                2
            ),
            "scene_mood": self.current_scene.mood,
            "scene_participants": list(self.current_scene.participants),
            "scene_completed": self.current_scene.completed,
        }
        
    def register_template(
        self,
        name: str,
        goal: str,
        tags: Optional[List[str]] = None,
        max_progress: float = 1.0,
    ) -> None:
        """Register a scene template for quick creation.
        
        Args:
            name: Template name.
            goal: Default goal for template.
            tags: Default tags.
            max_progress: Default max progress.
        """
        self.scene_templates[name] = {
            "goal": goal,
            "tags": tags or [],
            "max_progress": max_progress,
        }
        
    def create_from_template(
        self,
        name: str,
        participants: Optional[Set[str]] = None,
    ) -> Optional[Scene]:
        """Create a scene from a registered template.
        
        Args:
            name: Template name.
            participants: Scene participants.
            
        Returns:
            New Scene, or None if template not found.
        """
        template = self.scene_templates.get(name)
        if not template:
            return None
            
        return self.new_scene(
            goal=template["goal"],
            participants=participants,
            tags=template["tags"],
            max_progress=template["max_progress"],
        )
        
    def get_completed_scenes(self) -> List[Scene]:
        """Get all completed scenes from history.
        
        Returns:
            List of completed Scene objects.
        """
        completed = []
        for scene in self.scene_history:
            if scene.completed:
                completed.append(scene)
        if self.current_scene and self.current_scene.completed:
            completed.append(self.current_scene)
        return completed
        
    def get_recent_scenes(self, count: int = 5) -> List[Scene]:
        """Get most recent scenes (including current).
        
        Args:
            count: Number of scenes to return.
            
        Returns:
            List of recent Scene objects.
        """
        scenes = list(self.scene_history[-count:])
        if self.current_scene:
            scenes.append(self.current_scene)
        return scenes[-count:]
        
    def get_scene_summary(self) -> str:
        """Get human-readable scene status summary.
        
        Returns:
            Multi-line string with scene information.
        """
        lines = ["## Scene Status"]
        
        if self.current_scene:
            lines.append(f"Current: {self.current_scene.summary()}")
        else:
            lines.append("Current: No active scene")
            
        if self.scene_history:
            lines.append(f"Completed Scenes: {sum(1 for s in self.scene_history if s.completed)}")
            
        return "\n".join(lines)
        
    def reset(self) -> None:
        """Reset scene manager state."""
        self.current_scene = None
        self.scene_history.clear()
        self._scene_counter = 0