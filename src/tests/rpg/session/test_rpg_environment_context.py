from app.rpg.session.environment_context import scene_context_for_location


def test_tavern_start_is_indoor_and_sheltered() -> None:
    context = scene_context_for_location(
        "rusty_flagon_tavern",
        region_id="market_road",
        location_label="Rusty Flagon Tavern",
    )

    assert context["exposure"] == "indoor"
    assert context["shelter"] == "sheltered"
