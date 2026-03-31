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