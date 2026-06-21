from app.rpg.session.environment_context import transition_scene_context


def test_transition_updates_scene_only() -> None:
    state = {
        "world": {"environment": {"region_id": "market_road", "active_events": [{"type": "weather", "condition": "rain"}]}},
        "scene": {},
    }

    moved = transition_scene_context(
        state,
        location_id="rusty_flagon_tavern",
        location_label="Rusty Flagon Tavern",
    )

    assert moved["scene"]["environment_context"]["exposure"] == "indoor"
    assert moved["world"]["environment"] == state["world"]["environment"]
