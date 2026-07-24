from app.rpg.session.genesis.world_forge_contract import build_campaign_topic_graph
from app.rpg.session.genesis.world_forge_profile_graph import (
    build_profile_launch_topic_graph,
    build_profile_topic_graph,
)
from app.rpg.session.genesis.world_forge_profiles import (
    DomainDefinition,
    DomainTargetRange,
    FieldDefinition,
    GenreProfile,
    LaunchRequirements,
)


def _post_apocalyptic_profile() -> GenreProfile:
    return GenreProfile(
        profile_id="post_apocalyptic",
        version=1,
        display_name="Post-apocalyptic",
        domains=(
            DomainDefinition(
                "setting_rules",
                "Setting Rules",
                "setting_rule",
                required_before_launch=True,
                semantic_roles=("starting_context",),
                fields=(FieldDefinition("name", "string", required=True),),
            ),
            DomainDefinition(
                "settlements",
                "Settlements",
                "settlement",
                dependencies=("setting_rules",),
                required_before_launch=True,
                semantic_roles=("starting_context",),
                fields=(FieldDefinition("name", "string", required=True),),
                target_range=DomainTargetRange((2, 3), (4, 6), (8, 12)),
            ),
            DomainDefinition(
                "factions",
                "Factions",
                "faction",
                dependencies=("settlements",),
                required_before_launch=True,
                semantic_roles=("initial_conflict",),
                fields=(
                    FieldDefinition("name", "string", required=True),
                    FieldDefinition(
                        "settlement_ids",
                        "entity_ref_list",
                        allowed_target_domains=("settlements",),
                    ),
                ),
            ),
            DomainDefinition(
                "actors",
                "Actors",
                "actor",
                dependencies=("factions", "settlements"),
                required_before_launch=True,
                semantic_roles=("initial_actors",),
                fields=(
                    FieldDefinition("name", "string", required=True),
                    FieldDefinition(
                        "faction_id",
                        "entity_ref",
                        allowed_target_domains=("factions",),
                    ),
                ),
            ),
            DomainDefinition(
                "mutations",
                "Mutations",
                "mutation",
                dependencies=("setting_rules",),
                fields=(FieldDefinition("name", "string", required=True),),
            ),
        ),
        launch_requirements=LaunchRequirements(
            required_domain_ids=(
                "setting_rules",
                "settlements",
                "factions",
                "actors",
            ),
        ),
    )


def test_profile_graph_contains_only_profile_domains() -> None:
    profile = _post_apocalyptic_profile()
    graph = build_profile_topic_graph(
        profile,
        campaign_template="wasteland",
        depth="standard",
    )
    nodes = graph.node_map()
    assert "settlements" in nodes
    assert "mutations" in nodes
    assert "spells" not in nodes
    assert "pantheon" not in nodes
    assert "classes" not in nodes
    assert nodes["settlements"].target_count == 5
    assert graph.metadata["resolved_profile_hash"] == profile.content_hash


def test_launch_graph_uses_profile_requirements_and_dependency_closure() -> None:
    profile = _post_apocalyptic_profile()
    graph = build_profile_topic_graph(
        profile,
        campaign_template="wasteland",
        depth="quick",
    )
    launch = build_profile_launch_topic_graph(graph, profile)
    nodes = launch.node_map()
    assert {"setting_rules", "settlements", "factions", "actors"}.issubset(nodes)
    assert "mutations" not in nodes
    assert nodes["relationships"].dependencies == (
        "setting_rules",
        "settlements",
        "factions",
        "actors",
    )
    assert launch.metadata["deferred_topic_ids"] == ["mutations"]


def test_reference_schema_is_embedded_in_node_metadata() -> None:
    profile = _post_apocalyptic_profile()
    graph = build_profile_topic_graph(profile, campaign_template="wasteland")
    faction = graph.node_map()["factions"]
    assert faction.metadata["entity_kind"] == "faction"
    assert faction.metadata["reference_fields"]["settlement_ids"] == {
        "value_type": "entity_ref_list",
        "allowed_target_domains": ["settlements"],
    }


def test_cyberpunk_fallback_graph_uses_only_cyberpunk_profile_domains() -> None:
    graph = build_campaign_topic_graph(
        campaign_template="cyberpunk",
        genre="cyberpunk",
        tone="neon noir",
        depth="standard",
        background_expansion=True,
    )
    nodes = graph.node_map()

    assert graph.graph_version == "rpg_profile_topic_graph_v1"
    assert {"networks", "augmentations", "places", "groups", "actors"}.issubset(nodes)
    assert {
        "spells",
        "races",
        "classes",
        "pantheon",
        "hero_system",
        "monsters",
    }.isdisjoint(nodes)
