from app.rpg.session.environment_context import scene_context_for_location


def test_pass_and_quarry_starts_are_outdoor() -> None:
    pass_context = scene_context_for_location("glimmerdeep_pass", region_id="mountain_pass")
    quarry_context = scene_context_for_location("old_quarry", region_id="abandoned_works")

    assert pass_context["exposure"] == "outdoor"
    assert pass_context["shelter"] == "exposed"
    assert quarry_context["exposure"] == "outdoor"
    assert quarry_context["shelter"] == "exposed"
