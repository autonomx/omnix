from __future__ import annotations

from app.rpg.session.genesis.compiler import compile_campaign_genesis
from app.rpg.session.genesis.contract import CampaignGenesisContract
from app.rpg.session.genesis.world_forge_contract import (
    build_campaign_topic_graph,
    world_forge_depth_profile,
)


def test_standard_world_forge_graph_is_prose_free_valid_and_launch_ordered() -> None:
    graph = build_campaign_topic_graph(
        campaign_template="summoned_heroes",
        genre="portal_fantasy",
        tone="darkly heroic",
        depth="standard",
        starting_location="vanta_gate",
    )
    assert graph.validate() == ()
    ordered = [node.topic_id for node in graph.topological_order()]
    assert ordered.index("realm") < ordered.index("regions") < ordered.index(
        "locations"
    )
    assert ordered.index("factions") < ordered.index("npcs") < ordered.index(
        "opening_threads"
    )
    assert ordered[-2:] == ["retrieval_index", "opening_materialization"]
    payload = graph.as_dict()
    assert payload["depth"] == "standard"
    assert payload["metadata"]["depth_profile"]["major_npc_range"] == [8, 12]
    assert all("full_text" not in node for node in payload["nodes"])


def test_generation_depth_profiles_match_launch_targets() -> None:
    assert world_forge_depth_profile("quick").lore_page_range == (12, 20)
    assert world_forge_depth_profile("standard").major_npc_range == (8, 12)
    assert world_forge_depth_profile("epic").faction_range == (8, 14)
    fallback = world_forge_depth_profile("unknown")
    assert fallback.depth == "standard"


def test_genesis_compiler_embeds_profile_policy_and_dependency_graph() -> None:
    contract = CampaignGenesisContract.model_validate(
        {
            "campaign_template": "summoned_heroes",
            "genre": "portal_fantasy",
            "tone": "fractured mythic fantasy",
            "world_options": {
                "starting_location": "vanta_gate",
                "difficulty": "normal",
                "world_activity": "living_world",
                "economy_pressure": "normal",
                "combat_lethality": "deadly",
                "seed": 99,
            },
            "world_forge": {
                "depth": "epic",
                "background_expansion": False,
                "max_parallel_jobs": 99,
                "custom_directives": [
                    "Summoned heroes destabilize politics."
                ],
            },
        }
    )
    compiled = compile_campaign_genesis(contract)
    world_forge = compiled["compiled_world_forge"]
    assert world_forge["enabled"] is True
    assert world_forge["depth_profile"]["depth"] == "epic"
    assert world_forge["max_parallel_jobs"] == 4
    assert world_forge["topic_graph"]["campaign_template"] == "summoned_heroes"
    assert "opening_materialization" in world_forge["topic_graph"][
        "launch_required_topic_ids"
    ]
    assert world_forge["resolved_profile_hash"].startswith("sha256:")
    assert world_forge["genre_profile_resolution"]["generated"] is True
    assert compiled["compiler_version"] == "rpg_genesis_compiler_v3"
