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


def test_fourth_tavern_graph_contains_captain_voss_nodes():
    from app.rpg.progression.graph_registry import get_progression_graph_by_id

    graph = get_progression_graph_by_id(
        "tavern_story_seed",
        "graph:tavern_story_seed:captain_voss_consequence",
    )
    assert graph is not None

    node_ids = [node.node_id for node in graph.nodes]

    assert node_ids == [
        "plan_against_captain_voss",
        "identify_voss_allies",
        "seek_magistrate_hearing",
        "present_manifest_to_magistrate",
        "secure_public_witnesses",
        "counter_voss_intimidation",
        "attend_public_hearing",
        "answer_voss_accusation",
        "force_voss_response",
        "choose_voss_outcome",
        "stabilize_town_after_voss",
        "close_voss_consequence_arc",
    ]


def test_fifth_tavern_graph_contains_voss_backer_nodes():
    from app.rpg.progression.graph_registry import get_progression_graph_by_id

    graph = get_progression_graph_by_id(
        "tavern_story_seed",
        "graph:tavern_story_seed:voss_backers_investigation",
    )
    assert graph is not None

    node_ids = [node.node_id for node in graph.nodes]

    assert node_ids == [
        "review_voss_backer_leads",
        "trace_voss_payment_marks",
        "ask_bran_about_silver_crow",
        "question_old_teamster",
        "travel_to_abandoned_cooperage",
        "inspect_cooperage_cellar",
        "open_silver_crow_cache",
        "read_silver_crow_ledger",
        "identify_sable_chain_agent",
        "locate_agent_marlowe",
        "confront_agent_marlowe",
        "return_with_sable_chain_proof",
    ]


def test_sixth_tavern_graph_contains_sable_chain_countermove_nodes():
    from app.rpg.progression.graph_registry import get_progression_graph_by_id

    graph = get_progression_graph_by_id(
        "tavern_story_seed",
        "graph:tavern_story_seed:sable_chain_countermove",
    )
    assert graph is not None

    node_ids = [node.node_id for node in graph.nodes]

    assert node_ids == [
        "plan_against_sable_chain",
        "secure_sable_chain_evidence",
        "detect_safehouse_watchers",
        "follow_safehouse_watchers",
        "travel_to_river_gate_warehouses",
        "inspect_warehouse_marks",
        "find_countermove_orders",
        "warn_allies_of_sable_chain_strike",
        "prepare_safehouse_defense",
        "intercept_sable_chain_strike_team",
        "capture_sable_chain_orders",
        "report_sable_chain_countermove",
    ]


def test_seventh_tavern_graph_contains_sable_chain_handler_route_pressure_nodes():
    from app.rpg.progression.graph_registry import get_progression_graph_by_id

    graph = get_progression_graph_by_id(
        "tavern_story_seed",
        "graph:tavern_story_seed:sable_chain_handler_route_pressure",
    )
    assert graph is not None

    node_ids = [node.node_id for node in graph.nodes]

    assert node_ids == [
        "review_handler_orders",
        "decode_handler_route_cipher",
        "warn_east_road_teamsters",
        "scout_east_road_pressure_points",
        "disable_false_toll_markers",
        "find_handler_dead_drop",
        "read_route_pressure_instructions",
        "travel_to_black_ford",
        "confront_route_pressure_agents",
        "secure_black_ford_crossing",
        "identify_handler_signature",
        "return_with_veska_name",
    ]


def test_eighth_tavern_graph_contains_handler_veska_leadership_pursuit_nodes():
    from app.rpg.progression.graph_registry import get_progression_graph_by_id

    graph = get_progression_graph_by_id(
        "tavern_story_seed",
        "graph:tavern_story_seed:handler_veska_leadership_pursuit",
    )
    assert graph is not None

    node_ids = [node.node_id for node in graph.nodes]

    assert node_ids == [
        "plan_pursuit_of_handler_veska",
        "trace_veska_courier_route",
        "travel_to_old_north_watchpost",
        "inspect_watchpost_courier_signs",
        "intercept_veska_courier",
        "recover_veska_coded_message",
        "decode_veska_coded_message",
        "travel_to_ridge_hideout",
        "scout_ridge_hideout",
        "confront_handler_veska",
        "secure_veska_ledgers",
        "return_with_veska_ledgers",
    ]


def test_ninth_tavern_graph_contains_sable_chain_endgame_opener_nodes():
    from app.rpg.progression.graph_registry import get_progression_graph_by_id

    graph = get_progression_graph_by_id(
        "tavern_story_seed",
        "graph:tavern_story_seed:sable_chain_endgame_opener",
    )
    assert graph is not None

    node_ids = [node.node_id for node in graph.nodes]

    assert node_ids == [
        "review_veska_ledgers_for_command_structure",
        "identify_hidden_paymaster",
        "trace_red_lantern_payments",
        "travel_to_old_counting_house",
        "inspect_counting_house_records",
        "secure_red_lantern_records",
        "return_with_red_lantern_records",
    ]