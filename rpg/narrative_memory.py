class NarrativeMemory:
    def __init__(self):
        self.relationships = {}  # Character relationships and their evolution
        self.unresolved_threads = []  # Plot threads that need resolution
        self.emotional_states = {}  # Emotional context for characters
        self.key_events = []  # Important narrative events

    def update_relationship(self, char1, char2, change):
        """Update relationship between two characters."""
        key = f"{char1}-{char2}"
        self.relationships[key] = self.relationships.get(key, 0) + change

    def add_unresolved_thread(self, thread):
        """Add a narrative thread that needs resolution."""
        self.unresolved_threads.append(thread)

    def resolve_thread(self, thread_index):
        """Mark a thread as resolved."""
        if 0 <= thread_index < len(self.unresolved_threads):
            self.unresolved_threads[thread_index]["resolved"] = True

    def update_emotional_state(self, character, emotion, intensity):
        """Update emotional state for a character."""
        if character not in self.emotional_states:
            self.emotional_states[character] = {}
        self.emotional_states[character][emotion] = intensity

    def add_key_event(self, event):
        """Record an important narrative event."""
        self.key_events.append(event)


def build_narrative_context(session):
    """
    Build narrative context from memory for director decisions.
    """
    if not hasattr(session, 'narrative_memory'):
        return {}

    memory = session.narrative_memory
    return {
        "relationships": memory.relationships,
        "unresolved_threads": memory.unresolved_threads,
        "emotional_states": memory.emotional_states,
        "key_events": memory.key_events[-5:],  # Last 5 events
        "tension_trend": getattr(session, 'narrative_state', {}).get('last_tension', 0.5)
    }


def update_narrative_memory(session, scene):
    """
    Maintain narrative continuity by updating memory with scene information.
    """
    if not hasattr(session, 'narrative_memory'):
        session.narrative_memory = NarrativeMemory()

    memory = session.narrative_memory

    # Update emotional states from scene
    for character in scene.characters:
        emotion = character.get("emotion", "neutral")
        memory.update_emotional_state(character["name"], emotion, 0.5)

    # Add key events if any dramatic elements
    if scene.event:
        memory.add_key_event({
            "type": "event",
            "description": scene.event.get("description", ""),
            "location": scene.location
        })

    return memory