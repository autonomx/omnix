def test_garran_party_setup_action_terms_are_present():
    from app.rpg.progression.graph_registry import get_progression_graphs_for_seed

    graphs = get_progression_graphs_for_seed("tavern_story_seed")
    text = repr(graphs).lower()

    assert "ask_garran_to_join" in text
    assert "join me" in text or "join us" in text
    assert "party_setup" in text
    assert "garran_recruited" in text or "companion_added" in text


def test_prepare_for_mill_road_has_mechanics_opportunities():
    from app.rpg.progression.graph_registry import get_progression_graphs_for_seed

    graphs = get_progression_graphs_for_seed("tavern_story_seed")
    text = repr(graphs).lower()

    assert "prepare_for_mill_road" in text
    assert "buy_rations" in text or "rations" in text
    assert "rent_room_rest" in text or "lodging" in text or "room" in text
    assert "ask_garran_to_join" in text