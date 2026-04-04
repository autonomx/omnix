from app.rpg.scene.scene import Scene


class SceneOutput:
    def __init__(self, location, tone, scene_type, tension, characters, narration, choices, event=None):
        self.location = location
        self.tone = tone
        self.scene_type = scene_type  # combat, dialogue, exploration, cinematic
        self.tension = tension  # 0.0 to 1.0
        self.characters = characters  # List of character dicts with name, dialogue, emotion
        self.narration = narration
        self.choices = choices  # List of choice dicts with text, intent, risk
        self.event = event  # Optional event info

    def to_dict(self):
        return {
            "location": self.location,
            "tone": self.tone,
            "scene_type": self.scene_type,
            "tension": self.tension,
            "characters": self.characters,
            "narration": self.narration,
            "choices": self.choices,
            "event": self.event
        }

class TurnContext:
    def __init__(self, player_input, intent=None, director_output=None, result=None, event=None, scene=None):
        self.player_input = player_input
        self.intent = intent
        self.director_output = director_output
        self.result = result
        self.event = event
        self.scene = scene


class GameState:
    def __init__(self):
        self.active = True
        self.scene = Scene()