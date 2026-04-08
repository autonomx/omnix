import os
import sys

from .game_state import SceneOutput
from .npc import NPC

_models_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "models.py")
if os.path.isfile(_models_file):
    import importlib.util
    _spec = importlib.util.spec_from_file_location("app.rpg.models_file", _models_file)
    _mod = importlib.util.module_from_spec(_spec)
    sys.modules["app.rpg.models_file"] = _mod
    _spec.loader.exec_module(_mod)
    GameSession = _mod.GameSession
