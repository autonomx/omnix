from __future__ import annotations

from typing import Any, Dict, List

from app.rpg.progression.graphs.bandit_aftermath import _build_tavern_aftermath_graph
from app.rpg.progression.graphs.captain_voss_consequence import _build_captain_voss_consequence_graph
from app.rpg.progression.graphs.caravan_ambush import _caravan_ambush_graph
from app.rpg.progression.graphs.handler_veska_leadership_pursuit import _build_handler_veska_leadership_pursuit_graph
from app.rpg.progression.graphs.north_road_shrine import _build_north_road_shrine_graph
from app.rpg.progression.graphs.sable_chain_countermove import _build_sable_chain_countermove_graph
from app.rpg.progression.graphs.sable_chain_endgame_opener import _build_sable_chain_endgame_opener_graph
from app.rpg.progression.graphs.sable_chain_handler_route_pressure import _build_sable_chain_handler_route_pressure_graph
from app.rpg.progression.graphs.voss_backers_investigation import _build_voss_backers_investigation_graph
from app.rpg.progression.graphs.witness_to_quarry import _rusty_flagon_graph
from app.rpg.progression.models import ScenarioProgressionGraph


_GRAPHS: Dict[str, List[ScenarioProgressionGraph]] = {
    "tavern_story_seed": [
        _rusty_flagon_graph(),
        _build_tavern_aftermath_graph(),
        _build_north_road_shrine_graph(),
        _build_captain_voss_consequence_graph(),
        _build_voss_backers_investigation_graph(),
        _build_sable_chain_countermove_graph(),
        _build_sable_chain_handler_route_pressure_graph(),
        _build_handler_veska_leadership_pursuit_graph(),
        _build_sable_chain_endgame_opener_graph(),
    ],
    "caravan_ambush_seed": [_caravan_ambush_graph()],
}


def get_progression_graph_for_seed(scenario_seed: str) -> ScenarioProgressionGraph | None:
    graphs = _GRAPHS.get(scenario_seed, [])
    return graphs[0] if graphs else None


def get_progression_graphs_for_seed(scenario_seed: str) -> List[ScenarioProgressionGraph]:
    return _GRAPHS.get(scenario_seed, [])


def get_progression_graph_by_id(scenario_seed: str, graph_id: str) -> ScenarioProgressionGraph | None:
    for graph in get_progression_graphs_for_seed(scenario_seed):
        if graph.graph_id == graph_id:
            return graph
    return None


def validate_progression_graph_registry() -> Dict[str, Any]:
    errors: List[str] = []
    for seed, graphs in _GRAPHS.items():
        seen_graph_ids = set()
        for graph in graphs:
            if not graph.graph_id:
                errors.append(f"{seed}:graph_missing_id")
            if graph.graph_id in seen_graph_ids:
                errors.append(f"{seed}:duplicate_graph_id:{graph.graph_id}")
            seen_graph_ids.add(graph.graph_id)
            node_ids = [node.node_id for node in graph.nodes]
            if len(node_ids) != len(set(node_ids)):
                errors.append(f"{seed}:{graph.graph_id}:duplicate_node_ids")
            if not node_ids:
                errors.append(f"{seed}:{graph.graph_id}:no_nodes")
    return {
        "ok": not errors,
        "errors": errors,
        "graph_count": sum(len(graphs) for graphs in _GRAPHS.values()),
        "seeds": sorted(_GRAPHS.keys()),
    }
