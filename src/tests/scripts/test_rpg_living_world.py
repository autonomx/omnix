"""The living-world harness's checks (W1): windows, presence by the time of day, and recaps naming only real changes."""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("omnix_rpg_living_world_tests_target", ROOT / "scripts/rpg_living_world.py")
living = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(living)


def test_every_full_window_needs_a_marked_turn() -> None:
    assert living.every_window_has({3, 27}, 50, 20) == {"windows": 2, "missing": [], "passed": True}
    assert living.every_window_has({3}, 50, 20)["missing"] == ["20-39"]  # the last, shorter window is not judged


def test_a_place_changes_with_the_time_of_day_only_if_its_people_do() -> None:
    same = [{"location_id": "inn", "part_of_day": part, "present": ["bran"]} for part in ("morning", "evening")]
    assert living.presence_by_time(same)["passed"] is False
    changed = same + [{"location_id": "inn", "part_of_day": "night", "present": []}]
    assert living.presence_by_time(changed)["places_changing_with_time"] == ["inn"]
    one_time = [{"location_id": "inn", "part_of_day": "morning", "present": people} for people in (["a"], ["b"])]
    assert living.presence_by_time(one_time)["passed"] is False  # different people, but never another time of day


def test_a_recap_names_only_what_happened() -> None:
    lines = ["Orik arrives, opening the forge.", "Liora leaves for Starfall Village.", "Word comes: the drought grows worse."]
    assert living.recap_is_real(lines, arrived={"Orik"}, left={"Liora"}, turned={"the drought"}) == []
    assert living.recap_is_real(lines, arrived=set(), left={"Liora"}, turned=set()) == [lines[0], lines[2]]


def test_the_parts_of_the_day() -> None:
    assert [living.part_of_day(hour * 60) for hour in (0, 7, 13, 20, 24 + 7)] == [
        "night", "morning", "afternoon", "evening", "morning"]
