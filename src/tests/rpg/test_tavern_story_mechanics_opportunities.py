def test_tavern_story_seed_contains_mechanics_opportunities():
    from app.rpg.progression.graph_registry import get_progression_graphs_for_seed

    graphs = get_progression_graphs_for_seed("tavern_story_seed")
    text = repr(graphs).lower()

    assert "prepare_for_mill_road" in text
    assert "buy" in text
    assert "rations" in text
    assert "lodging" in text or "room" in text
    assert "garran" in text