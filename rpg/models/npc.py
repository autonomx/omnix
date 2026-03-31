class NPC:
    def __init__(self, id: str, name: str, personality: str, faction: str, hp: int = 100, stats=None):
        self.id = id
        self.name = name
        self.personality = personality
        self.faction = faction
        self.hp = hp
        self.stats = stats or {"strength": 10, "dexterity": 10, "intelligence": 10}
        self.goals = []
        self.current_goal = None
        self.memory = {
            "events": [],
            "facts": [],
            "relationships": {}
        }
        self.emotional_state = {
            "neutral": 0.0,
            "angry": 0.0,
            "happy": 0.0,
            "fearful": 0.0
        }
        self.opinions = {}  # opinions of other characters, affected by emotions
        self.voice_style = "neutral"  # calm, aggressive, formal, casual, etc.
        self.speaking_patterns = ["direct", "concise"]  # List of speaking patterns

    def update_emotions(self, new_emotion):
        """Update emotional state with decay and new emotion."""
        # Decay all emotions
        for emotion in self.emotional_state:
            self.emotional_state[emotion] *= 0.9

        # Apply new emotion
        if new_emotion in self.emotional_state:
            self.emotional_state[new_emotion] = min(
                1.0,
                self.emotional_state[new_emotion] + 0.3
            )