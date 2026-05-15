def test_tavern_graph_core_mechanics_have_metadata():
    from app.rpg.progression.graph_registry import _rusty_flagon_graph

    graph = _rusty_flagon_graph()
    text = repr(graph).lower()

    assert "buy_rations_from_bran" in text
    assert "mechanic:buying" in text
    assert "mechanic:inventory_change" in text
    assert "mechanic:currency_change" in text

    assert "rent_room_from_bran" in text
    assert "mechanic:service_or_lodging" in text

    assert "ask_garran_to_join" in text
    assert "mechanic:party_setup" in text
    assert "mechanic:party_recruitment" in text

    assert "combat_started" in text
    assert "combat_resolved" in text
    assert "xp_gain" in text