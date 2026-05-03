from __future__ import annotations

from typing import Any

from tests.rpg.manual.scenarios.registry import build_service_scenarios
from tests.rpg.manual.turn_execution import _extract_player_input_from_turn


def test_extract_player_input_accepts_string_turn():
    assert _extract_player_input_from_turn("I ask Bran for a room") == "I ask Bran for a room"


def test_extract_player_input_accepts_dict_turn_player():
    assert _extract_player_input_from_turn({"player": "hello"}) == "hello"


def test_extract_player_input_accepts_dict_turn_input():
    assert _extract_player_input_from_turn({"input": "hello"}) == "hello"


def test_extract_player_input_accepts_dict_turn_player_input():
    assert _extract_player_input_from_turn({"player_input": "hello"}) == "hello"


def test_legacy_string_turns_are_supported():
    scenarios = build_service_scenarios()
    assert isinstance(scenarios["lodging_success"]["turns"][0], str)
    assert _extract_player_input_from_turn(scenarios["lodging_success"]["turns"][0])