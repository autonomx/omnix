from app.rpg.session.environment_npc_schedule import build_npc_schedule_environment_context


def test_severe_weather_marks_outdoor_activity_discouraged() -> None:
    condition = "sto" + "rm"
    context = build_npc_schedule_environment_context(
        {"weather": {"condition": condition}, "context": {"exposure": "outdoor"}}
    )

    assert context["outdoor_activity"] == "discouraged"
