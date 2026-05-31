"""Goal shaping and pacing mixin for the RPG story director."""
from __future__ import annotations


class DirectorGoalShapingMixin:
    # DESIGN SPEC METHODS (from rpg-design.txt)
    # =========================================================

    def adjust_goal(self, npc, proposed_goal, context):
        """MAIN ENTRY POINT — Apply arc shaping and pacing to proposed goal.

        This is the core method from the design spec that biases NPC goals
        based on story state without overriding simulation logic.

        Args:
            npc: The NPC whose goal is being adjusted.
            proposed_goal: The goal proposed by GOAP.
            context: Context dict with recent_events and other state.

        Returns:
            Modified goal dict with adjusted priority.
        """
        self._update_tension(context)
        self._update_phase()
        self._update_cooldowns()

        goal = dict(proposed_goal)  # Copy to avoid mutation
        goal.setdefault("priority", 1.0)
        goal.setdefault("name", goal.get("type", "unknown"))

        # Apply arc shaping
        if self.arc == "conflict":
            goal = self._bias_conflict(npc, goal)
        elif self.arc == "alliance":
            goal = self._bias_alliance(npc, goal)
        elif self.arc == "mystery":
            goal = self._bias_mystery(npc, goal)

        # Apply pacing rules
        goal = self._apply_pacing(npc, goal)

        # Apply anti-repetition
        goal = self.prevent_repetition(npc, goal)

        return goal

    def _update_tension(self, context):
        """Update tension based on recent events.

        Tension rises and falls based on what happens in the world.

        Event weights:
        - damage: +0.05
        - death: +0.2
        - assist: -0.03 (reduces tension)

        Args:
            context: Context dict with recent_events list.
        """
        events = context.get("recent_events", [])
        delta = 0.0

        for e in events:
            etype = e.get("type", "")
            if etype == "damage":
                delta += 0.05
            elif etype == "death":
                delta += 0.2
            elif etype == "assist":
                delta -= 0.03

        self.global_tension = max(0.0, min(1.0, self.global_tension + delta))

    def _update_phase(self):
        """Update story phase based on current tension.

        Phase progression:
        - intro: tension < 0.2 (calm, exploratory)
        - build: tension < 0.5 (suspicion rising)
        - tension: tension < 0.8 (cautious, reactive)
        - climax: tension >= 0.8 (decisive, emotional)

        Also triggers auto-arc selection.
        """
        if self.global_tension < 0.2:
            self.phase = "intro"
        elif self.global_tension < 0.5:
            self.phase = "build"
        elif self.global_tension < 0.8:
            self.phase = "tension"
        elif self.global_tension >= 0.8:
            self.phase = "climax"

        # Auto-select arc based on tension
        self.auto_select_arc()

    def auto_select_arc(self):
        """Design item 9: Dynamically select story arc based on tension.

        Arc selection:
        - Low tension (< 0.2): mystery arc (exploration)
        - Medium tension (0.2-0.6): alliance arc (cooperation)
        - High tension (> 0.6): conflict arc (combat)
        """
        if self.global_tension < 0.2:
            self.arc = "mystery"
        elif self.global_tension < 0.6:
            self.arc = "alliance"
        else:
            self.arc = "conflict"

    # =========================================================
    # GOAL SHAPING METHODS (design items 5-6)
    # =========================================================

    def _bias_conflict(self, npc, goal):
        """Bias goal toward conflict behavior.

        During conflict arcs:
        - Attack goals get +30% priority boost
        - Talk/social goals get -30% penalty

        Args:
            npc: The NPC whose goal is being biased.
            goal: The goal dict to modify.

        Returns:
            Modified goal dict.
        """
        goal_name = goal.get("name", goal.get("type", ""))

        if "attack" in goal_name.lower():
            goal["priority"] = goal.get("priority", 1.0) * 1.3

        if "talk" in goal_name.lower() or "assist" in goal_name.lower():
            goal["priority"] = goal.get("priority", 1.0) * 0.7

        return goal

    def _bias_alliance(self, npc, goal):
        """Bias goal toward alliance/cooperation behavior.

        During alliance arcs:
        - Assist/help goals get +50% priority boost
        - Attack goals get -40% penalty

        Args:
            npc: The NPC whose goal is being biased.
            goal: The goal dict to modify.

        Returns:
            Modified goal dict.
        """
        goal_name = goal.get("name", goal.get("type", ""))

        if "assist" in goal_name.lower() or "help" in goal_name.lower() or "ally" in goal_name.lower():
            goal["priority"] = goal.get("priority", 1.0) * 1.5

        if "attack" in goal_name.lower():
            goal["priority"] = goal.get("priority", 1.0) * 0.6

        return goal

    def _bias_mystery(self, npc, goal):
        """Bias goal toward exploration/mystery behavior.

        During mystery arcs:
        - Explore/observe goals get +40% priority boost
        - Attack goals get -20% penalty

        Args:
            npc: The NPC whose goal is being biased.
            goal: The goal dict to modify.

        Returns:
            Modified goal dict.
        """
        goal_name = goal.get("name", goal.get("type", ""))

        if "explore" in goal_name.lower() or "observe" in goal_name.lower():
            goal["priority"] = goal.get("priority", 1.0) * 1.4

        if "attack" in goal_name.lower():
            goal["priority"] = goal.get("priority", 1.0) * 0.8

        return goal

    def _apply_pacing(self, npc, goal):
        """Apply pacing rules based on current story phase.

        Pacing ensures natural story progression:
        - Intro: Suppress attacks (30% priority) for calm beginning
        - Tension: Boost all goals by 20% for building drama
        - Climax: Attacks get 50% boost for decisive resolution

        Args:
            npc: The NPC whose goal is being paced.
            goal: The goal dict to modify.

        Returns:
            Modified goal dict.
        """
        goal_name = goal.get("name", goal.get("type", ""))

        if self.phase == "intro":
            # Calm beginning - suppress aggression
            if "attack" in goal_name.lower():
                goal["priority"] = goal.get("priority", 1.0) * 0.3

        elif self.phase == "tension":
            # Building drama - boost everything
            goal["priority"] = goal.get("priority", 1.0) * 1.2

        elif self.phase == "climax":
            # Decisive resolution - boost attacks
            if "attack" in goal_name.lower():
                goal["priority"] = goal.get("priority", 1.0) * 1.5

        return goal

    def prevent_repetition(self, npc, goal):
        """Design item 11: Anti-repetition guard.

        Prevents NPCs from repeating the same goal too frequently.
        Sets a 3-tick cooldown on goals after they're used.

        Args:
            npc: The NPC whose goal is being checked.
            goal: The goal dict to check.

        Returns:
            Modified goal dict with priority reduced if on cooldown.
        """
        key = (npc.id, goal.get("name", goal.get("type", "")))

        if self.cooldowns.get(key, 0) > 0:
            goal["priority"] = goal.get("priority", 1.0) * 0.2

        self.cooldowns[key] = 3
        return goal

    def _update_cooldowns(self):
        """Tick down all cooldown counters each frame."""
        for key in list(self.cooldowns.keys()):
            self.cooldowns[key] -= 1
            if self.cooldowns[key] <= 0:
                del self.cooldowns[key]
