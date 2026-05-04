from tests.rpg.manual.scenarios.story_pack_activation_m43_m45 import (
    STORY_PACK_ACTIVATION_M43_M45_SCENARIOS,
)


def test_m43_m45_manual_scenarios_use_supported_turn_shape():
    for name, scenario in STORY_PACK_ACTIVATION_M43_M45_SCENARIOS.items():
        turns = scenario.get("turns") or []
        assert turns, f"{name} has no turns"
        assert all(isinstance(turn, str) and turn.strip() for turn in turns), (
            f"{name} uses unsupported turn shape; manual_llm_transcript.py "
            "expects turns to be player input strings"
        )


def test_m43_m45_manual_scenarios_have_top_level_checks():
    for name, scenario in STORY_PACK_ACTIVATION_M43_M45_SCENARIOS.items():
        checks = scenario.get("checks") or []
        assert checks, f"{name} must put checks at top-level, not nested inside turn dicts"
        assert all(isinstance(check, dict) for check in checks), name