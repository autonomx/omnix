from app.rpg.player_action_context.runtime import build_player_action_context


def test_player_action_context_has_player_agent_schema_and_restrictions():
    context = build_player_action_context({}, turn_index=1)

    assert context["player_agent_schema"]["format_version"] == "rpg_player_action_v1"
    assert "action" in context["player_agent_schema"]
    assert any("do not decide the outcome" in row.lower() for row in context["restrictions"])
    assert any("simulation resolves" in row.lower() for row in context["restrictions"])


def test_player_action_context_empty_state_has_fallback_actions():
    context = build_player_action_context({}, turn_index=1)

    assert context["ok"] is True
    assert context["suggested_actions"]
    assert any(row["category"] == "exploration" for row in context["suggested_actions"])