"""Regression coverage for feature-owned foreground RPG job handling."""

from app.jobs.handlers import registry_from_features
from app.runtime.feature_catalog import load_feature


def test_rpg_turn_jobs_are_registered_by_the_rpg_feature() -> None:
    registry = registry_from_features((load_feature("rpg"),))

    turn = registry.require("rpg.turn")
    report = registry.require("rpg.report.last10")
    narration = registry.require("rpg.narration")
    scene_lore = registry.require("rpg.scene_lore")

    assert turn.input_model.__name__ == "RpgTurnJobInput"
    assert report.input_model.__name__ == "RpgReportJobInput"
    assert narration.input_model.__name__ == "RpgNarrationJobInput"
    assert scene_lore.input_model.__name__ == "RpgSceneLoreJobInput"
    assert registry.types() == ("rpg.game_master", "rpg.narration", "rpg.report.last10", "rpg.scene_lore", "rpg.turn")
