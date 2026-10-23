"""Fixtures for the playthrough suite (RQ-0.3): a scripted model, and campaigns to play."""
from __future__ import annotations

import pytest

from tests.rpg.playthrough.campaigns import Playthrough, launch_aurelia, launch_vesper, new_genesis_game, new_starter_game
from tests.rpg.playthrough.scripted_model import ScriptedRoleModel, scripted_model_installed


@pytest.fixture
def model(monkeypatch) -> ScriptedRoleModel:
    """Every RPG model call answered by role; the PostgreSQL job store installed."""
    with scripted_model_installed(monkeypatch) as scripted:
        yield scripted


@pytest.fixture
def launch(model, tmp_path, monkeypatch):
    """Start a campaign ("aurelia", "vesper", "starter", or "genesis": a wizard-made new game) and return its
    playthrough."""

    def start(world: str) -> Playthrough:
        if world == "aurelia":
            session_id, _ = launch_aurelia(tmp_path, monkeypatch)
        elif world == "vesper":
            session_id, _ = launch_vesper(tmp_path, monkeypatch)
        elif world == "starter":
            session_id = new_starter_game(seed=7)
        elif world == "genesis":
            session_id = new_genesis_game()
        else:
            raise ValueError(world)
        play = Playthrough(session_id)
        play.model = model
        play.world = world
        return play

    return start
