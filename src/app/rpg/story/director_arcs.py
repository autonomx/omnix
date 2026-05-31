"""Story arc primitives used by the RPG story director."""
from __future__ import annotations

# Arc phase enumeration
ARC_PHASES = ["build", "tension", "climax", "resolution"]


class StoryArc:
    """A single story arc with phase-based progression.

    Each arc progresses through phases based on events and tension.
    """

    def __init__(self, arc_type, originator, target, **kwargs):
        """Initialize a story arc.

        Args:
            arc_type: Type of arc (revenge, betrayal, alliance).
            originator: The entity that initiated the arc.
            target: The target entity of the arc.
            **kwargs: Additional arc properties.
        """
        self.type = arc_type
        self.originator = originator
        self.target = target
        self.phase = "build"  # build → tension → climax → resolution
        self.progress = 0.0
        self.intensity = kwargs.get("intensity", 1.0)
        self.tick_created = kwargs.get("tick_created", 0)
        self.active = True
        self.members = kwargs.get("members", [])
        self.resolved = False
        self.resolution_event = None

    def advance(self, global_tension, events):
        """Advance arc phase based on progress and tension.

        Args:
            global_tension: Current global tension level.
            events: Recent events that may affect this arc.
        """
        if not self.active:
            return

        # Count relevant events for this arc
        relevant_events = 0
        for event in events:
            if self._is_relevant_event(event):
                relevant_events += 1
                self.progress += 0.3
            else:
                self.progress += 0.05

        # Phase transitions
        if self.phase == "build" and self.progress >= 3.0:
            self.phase = "tension"
            self.intensity = min(1.0, self.intensity + 0.2)
        elif self.phase == "tension" and global_tension >= 7.0:
            self.phase = "climax"
            self.intensity = min(1.0, self.intensity + 0.3)
        elif self.phase == "climax":
            # Climax resolves after enough progress
            if self.progress >= 6.0:
                self.phase = "resolution"
                self.active = False
                self.resolved = True
        elif self.phase == "resolution":
            self.active = False
            self.resolved = True

    def _is_relevant_event(self, event):
        """Check if an event is relevant to this arc.

        Args:
            event: The event to check.

        Returns:
            True if the event relates to this arc.
        """
        source = event.get("source")
        target = event.get("target")
        involved = {self.originator, self.target} | set(self.members)

        return source in involved or target in involved

    def get_forced_goal(self, entity_id):
        """Get a forced goal for an entity in this arc.

        During tension and climax phases, the arc mandates behavior.

        Args:
            entity_id: The entity to get a forced goal for.

        Returns:
            Dict with forced goal, or None if no force applies.
        """
        if self.phase not in ("tension", "climax"):
            return None

        if not self.active:
            return None

        force_strength = self.intensity if self.phase == "climax" else self.intensity * 0.5

        if self.type == "revenge":
            if entity_id == self.originator:
                return {
                    "type": "attack_target",
                    "target": self.target,
                    "reason": "forced_revenge",
                    "force": force_strength,
                }
        elif self.type == "betrayal":
            if entity_id == self.originator:
                return {
                    "type": "attack_target",
                    "target": self.target,
                    "reason": "forced_betrayal",
                    "force": force_strength,
                }
        elif self.type == "alliance":
            if entity_id in self.members and self.target:
                return {
                    "type": "attack_target",
                    "target": self.target,
                    "reason": "forced_alliance",
                    "force": force_strength,
                }

        return None

    def to_dict(self):
        """Convert arc to dictionary representation."""
        return {
            "type": self.type,
            "originator": self.originator,
            "target": self.target,
            "phase": self.phase,
            "progress": self.progress,
            "intensity": self.intensity,
            "active": self.active,
            "resolved": self.resolved,
            "members": self.members,
        }
