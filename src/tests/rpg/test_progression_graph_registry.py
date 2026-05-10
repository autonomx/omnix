def test_progression_graph_registry_imports_and_validates():
    from app.rpg.progression.graph_registry import (
        get_progression_graphs_for_seed,
        validate_progression_graph_registry,
    )

    validation = validate_progression_graph_registry()
    assert validation["ok"], validation

    graphs = get_progression_graphs_for_seed("tavern_story_seed")
    graph_ids = [graph.graph_id for graph in graphs]

    assert "graph:tavern_story_seed:witness_to_quarry" in graph_ids
    assert "graph:tavern_story_seed:bandit_aftermath" in graph_ids


def test_first_tavern_graph_still_contains_quarry_road_end_nodes():
    from app.rpg.progression.graph_registry import get_progression_graph_by_id

    graph = get_progression_graph_by_id(
        "tavern_story_seed",
        "graph:tavern_story_seed:witness_to_quarry",
    )
    assert graph is not None

    node_ids = [node.node_id for node in graph.nodes]

    assert "leave_by_quarry_road" in node_ids
    assert "scout_quarry_road" in node_ids
    assert "spot_bridge_watchers" in node_ids
    assert "choose_ambush_response" in node_ids
    assert "protect_wagon_or_lure_bandits" in node_ids


def test_second_tavern_graph_contains_document_nodes():
    from app.rpg.progression.graph_registry import get_progression_graph_by_id

    graph = get_progression_graph_by_id(
        "tavern_story_seed",
        "graph:tavern_story_seed:bandit_aftermath",
    )
    assert graph is not None

    node_ids = [node.node_id for node in graph.nodes]

    assert "read_wax_sealed_order" in node_ids
    assert "decide_mill_next_step" in node_ids


def test_third_tavern_graph_contains_north_road_shrine_nodes():
    from app.rpg.progression.graph_registry import get_progression_graph_by_id

    graph = get_progression_graph_by_id(
        "tavern_story_seed",
        "graph:tavern_story_seed:north_road_shrine",
    )
    assert graph is not None

    node_ids = [node.node_id for node in graph.nodes]

    assert node_ids == [
        "travel_to_north_road_shrine",
        "inspect_shrine_tracks",
        "find_shrine_token",
        "wait_for_contact_signal",
        "shadow_black_briar_contact",
        "reach_ruined_tollhouse",
        "eavesdrop_tollhouse_meeting",
        "recover_tollhouse_manifest",
        "confront_black_briar_contact",
        "return_to_allies_with_voss_proof",
    ]