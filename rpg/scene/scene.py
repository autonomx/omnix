from rpg.models.npc import NPC

class Scene:
    def __init__(self):
        self.location = None
        self.characters = []
        self.active_conflicts = []
        self.summary = ""

def add_character(scene: Scene, npc: NPC):
    scene.characters.append(npc)

def remove_character(scene: Scene, npc: NPC):
    scene.characters.remove(npc)

def get_enemies(scene: Scene, npc: NPC):
    return [c for c in scene.characters if c.faction != npc.faction]

def has_enemy(scene: Scene, npc: NPC):
    return len(get_enemies(scene, npc)) > 0