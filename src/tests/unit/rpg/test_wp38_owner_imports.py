from __future__ import annotations

import sys


def test_npc_planner_uses_its_importable_owner_module():
    from app.rpg.ai.planner import Planner
    from app.rpg.ai.planner_core import Planner as OwnedPlanner

    assert Planner is OwnedPlanner
    assert "app.rpg.ai.planner_module" not in sys.modules


def test_game_session_uses_its_importable_owner_module():
    from app.rpg.legacy_models import GameSession as OwnedGameSession
    from app.rpg.models import GameSession

    assert GameSession is OwnedGameSession
    assert "app.rpg.models_file" not in sys.modules
