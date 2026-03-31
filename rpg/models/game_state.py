from rpg.scene.scene import Scene

class GameState:
    def __init__(self):
        self.active = True
        self.scene = Scene()