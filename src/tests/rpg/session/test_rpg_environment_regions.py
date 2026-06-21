from __future__ import annotations

import json
from copy import deepcopy

from app.rpg.session.environment import build_initial_environment_seed_state
from app.rpg.session.environment_regions import (
    advance_region_environments,
    derive_active_region_snapshot,
    get_active_region_environment,
    switch_active_region,
)


def _environment(location_id: str, condition: str, region_id: str) -> dict[str, object]:
    state = build_initial_environment_seed_state(
        campaign_seed=88,
        campaign_contract={"campaign_template": "classic_fantasy", "tone": "regional test"},
        location_id=location_id,
        location={"time_label": "Day 3 • 09:00", "weather": condition, "location": location_id},
    )
    environment = deepcopy(state["environment"])
    environment["region_id"] = region_id
    event = dict(environment["active_events"][0])
    event["condition"] = condition
    event["remaining_minutes"] = 600
    event["region_id"] = region_id
    environment["active_events"] = [event]
    return environment


def _world() -> dict[str, object]:
    return {
        "environment": {"active_region_id": "northern_mountains"},
        "regions": {
            "northern_mountains": {
                "environment": _environment("glimmerdeep_pass", "snow", "northern_mountains")
            },
            "southern_coast": {
                "environment": _environment("rusty_flagon_tavern", "rain", "southern_coast")
            },
        },
    }


def test_region_snapshots_keep_separate_weather() -> None:
    world = _world()
    north = derive_active_region_snapshot(world, {"exposure": "outdoor", "shelter": "exposed"})
    south_world = switch_active_region(world, "southern_coast")
    south = derive_active_region_snapshot(south_world, {"exposure": "outdoor", "shelter": "exposed"})

    assert north["region_id"] == "northern_mountains"
    assert north["weather"]["condition"] == "snow"
    assert south["region_id"] == "southern_coast"
    assert south["weather"]["condition"] == "rain"
    assert world["regions"]["northern_mountains"]["environment"]["active_events"][0]["condition"] == "snow"


def test_switch_active_region_does_not_rewrite_region_environments() -> None:
    world = _world()
    original = deepcopy(world)

    switched = switch_active_region(world, "southern_coast")

    assert switched["environment"]["active_region_id"] == "southern_coast"
    assert switched["regions"] == original["regions"]
    assert world == original
    assert get_active_region_environment(switched)["region_id"] == "southern_coast"


def test_region_advancement_is_deterministic_across_save_load_shape() -> None:
    world = _world()
    restored = json.loads(json.dumps(world))

    first = advance_region_environments(world, active_elapsed_minutes=10, offscreen_elapsed_minutes=60)
    second = advance_region_environments(restored, active_elapsed_minutes=10, offscreen_elapsed_minutes=60)

    assert first == second
    assert first["regions"]["northern_mountains"]["environment"]["absolute_minutes"] == 3490
    assert first["regions"]["southern_coast"]["environment"]["absolute_minutes"] == 3540
