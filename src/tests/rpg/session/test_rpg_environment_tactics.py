from app.rpg.session.environment_tactics import build_tactical_environment_context


def test_ranged_context_includes_wind_and_visibility() -> None:
    context = build_tactical_environment_context(
        {"wind": "strong", "visibility": "reduced", "terrain_condition": "firm_ground", "context": {"exposure": "outdoor"}}
    )

    assert "ranged_wind_context" in context["combat"]["notes"]
    assert "limited_visibility_context" in context["combat"]["notes"]
