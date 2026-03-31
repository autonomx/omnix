class NarrativeDecision:
    def __init__(self, intent, scene_focus, npc_ids, event, tension, mode):
        self.intent = intent
        self.scene_focus = scene_focus
        self.npc_ids = npc_ids
        self.event = event
        self.tension = tension
        self.mode = mode  # combat, dialogue, exploration, cinematic


class NarrativeDirector:
    def __init__(self):
        self.pacing_state = "introduction"
        self.tension_level = 0.5

    def decide_next_step(self, session, player_input, narrative_context=None):
        """
        Interprets player input narratively and decides next step.
        Uses narrative state for continuity.
        """
        # Initialize narrative state if not exists
        if not hasattr(session, 'narrative_state'):
            session.narrative_state = {
                "last_tension": 0.5,
                "last_scene_type": "exploration",
                "focus_npc": None
            }

        state = session.narrative_state

        # Use narrative context if provided
        if narrative_context:
            # Incorporate memory into decision
            pass

        # Update tension based on history
        self.tension_level = state["last_tension"]

        # Simple heuristic-based decision
        input_lower = player_input.lower()
        if "attack" in input_lower or "fight" in input_lower:
            intent = "combat"
            scene_focus = "battlefield"
            npc_ids = ["enemy_guard"]
            event = "ambush"
            tension = min(1.0, self.tension_level + 0.2)
            mode = "combat"
        elif "talk" in input_lower or "speak" in input_lower:
            intent = "dialogue"
            scene_focus = "meeting_hall"
            npc_ids = ["king_arthur"] if state["focus_npc"] else []
            event = None
            tension = max(0.0, self.tension_level - 0.1)
            mode = "dialogue"
        else:
            intent = "exploration"
            scene_focus = "town_square"
            npc_ids = []
            event = "discovery"
            tension = self.tension_level
            mode = "exploration"

        # Update state
        state["last_tension"] = tension
        state["last_scene_type"] = mode
        if npc_ids:
            state["focus_npc"] = npc_ids[0]

        return NarrativeDecision(
            intent=intent,
            scene_focus=scene_focus,
            npc_ids=npc_ids,
            event=event,
            tension=tension,
            mode=mode
        )