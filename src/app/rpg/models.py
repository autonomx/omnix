class SceneOutput:
    def __init__(self, location, scene_type, tone, tension, narration, characters, choices, event=None):
        self.location = location
        self.scene_type = scene_type
        self.tone = tone
        self.tension = tension
        self.narration = narration
        self.characters = characters  # List of character dicts with name, dialogue, emotion
        self.choices = choices  # List of available player choices
        self.event = event

    def to_dict(self):
        return {
            "location": self.location,
            "scene_type": self.scene_type,
            "tone": self.tone,
            "tension": self.tension,
            "narration": self.narration,
            "characters": self.characters,
            "choices": self.choices,
            "event": self.event
        }


class GameSession:
    def __init__(self):
        from rpg.event_bus import EventBus
        self.event_bus = EventBus()

        self.event_log = []
        self.world = World()
        self.player = Player()
        self.npcs: list[NPC] = []

        self.story_arcs = []
        self.recent_events = []
        self.config = type('Config', (), {'tone': 'neutral'})()
        self.narrative_state = {
            "tension": 0.3,
            "last_mode": "exploration",
            "focus_npc": None,
            "phase": "setup"
        }

    def add_npc(self, npc):
        """Add an NPC to the session and attach the session reference."""
        npc.session = self
        self.npcs.append(npc)


class World:
    def __init__(self, size=(20, 20)):
        self.entities = {}
        self.locations = {}
        self.time = 0
        self.size = size


class Player:
    def __init__(self):
        self.id = "player"
        self.hp = 100
        self.profile = {}


class NPC:
    def __init__(self, id, name):
        self.id = id
        self.name = name
        self.hp = 100
        self.is_active = True

        self.goal = None
        self.plan = []
        self.memory = []
        self.relationships = {}
        self.emotional_state = {
            "anger": 0.0,
            "fear": 0.0,
            "loyalty": 0.0,
            "last_update": 0,
            "top_threat": None
        }
        self.position = (0, 0)
        self.session = None
