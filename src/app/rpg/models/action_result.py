class ActionResult:
    def __init__(self, actor_id, action_type, outcome, description, dialogue="", emotion="neutral"):
        self.actor_id = actor_id
        self.action_type = action_type
        self.outcome = outcome
        self.description = description
        self.dialogue = dialogue
        self.emotion = emotion

    def to_dict(self):
        text = self.description
        if self.dialogue:
            text += f' "{self.dialogue}"'

        return {
            "actor_id": self.actor_id,
            "action_type": self.action_type,
            "outcome": self.outcome,
            "text": text,
            "description": self.description,
            "dialogue": self.dialogue,
            "emotion": self.emotion
        }