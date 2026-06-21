from app.rpg.session.environment_npc_schedule import build_npc_schedule_environment_context


def test_indoor_scene_is_not_currently_outdoor() -> None:
    context = build_npc_schedule_environment_context({"context": {"exposure": "indoor"}})

    assert context["outdoor_activity"] == "not_currently_outdoor"


def test_night_and_daylight_preferences_are_context_notes() -> None:
    context = build_npc_schedule_environment_context(
        {"light_level": "night", "context": {"exposure": "outdoor"}},
        prefers_daylight=True,
    )

    assert "night_context" in context["notes"]
    assert "prefers_daylight_context" in context["notes"]


def test_indoor_preference_reads_context_without_mutation() -> None:
    snapshot = {"weather": {"condition": "clear"}, "context": {"exposure": "outdoor"}}

    context = build_npc_schedule_environment_context(snapshot, prefers_indoor=True)

    assert "prefers_indoor_context" in context["notes"]
    assert snapshot["context"]["exposure"] == "outdoor"
