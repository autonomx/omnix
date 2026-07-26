from app.rpg.session.genesis.world_forge_profile_generation import (
    default_profile_registry,
)
from app.rpg.session.genesis.world_forge_profile_graph import (
    build_profile_launch_topic_graph,
    build_profile_topic_graph,
)
from app.rpg.session.genesis.world_forge_profiles import DomainDefinition, GenreProfile


def _profile():
    profile = default_profile_registry().resolve("fantasy")
    assert profile is not None
    return profile


def test_causal_traceability_is_added_to_full_profile_graph() -> None:
    graph = build_profile_topic_graph(
        _profile(),
        campaign_template="causal-test",
        depth="quick",
    )
    nodes = graph.node_map()

    assert graph.graph_version == "rpg_profile_topic_graph_v2"
    assert "causal_links" in nodes
    assert set(nodes["causal_links"].dependencies) == {
        "history_timeline",
        "regions",
        "places",
        "groups",
        "cultures",
        "actors",
    }

    history_fields = {
        row["field_id"]: row
        for row in nodes["history_timeline"].metadata["field_definitions"]
    }
    assert history_fields["cause_event_ids"]["value_type"] == "entity_ref_list"
    assert history_fields["legacy_status"]["enum_values"]
    assert "history_timeline" not in nodes["history_timeline"].dependencies

    actor_fields = {
        row["field_id"]: row
        for row in nodes["actors"].metadata["field_definitions"]
    }
    assert "culture_id" in actor_fields
    assert "culture_ids" in actor_fields
    assert "formative_event_ids" in actor_fields


def test_causal_links_remain_deferred_from_launch_graph() -> None:
    profile = _profile()
    graph = build_profile_topic_graph(
        profile,
        campaign_template="causal-test",
        depth="quick",
    )
    launch = build_profile_launch_topic_graph(graph, profile)

    assert "causal_links" not in launch.node_map()
    assert "causal_links" in launch.metadata["deferred_topic_ids"]


def test_custom_profiles_without_standard_domains_are_not_augmented() -> None:
    profile = GenreProfile(
        profile_id="minimal",
        version=1,
        display_name="Minimal",
        domains=(DomainDefinition("rules", "Rules", "rule"),),
    )
    graph = build_profile_topic_graph(profile, campaign_template="minimal")

    assert tuple(graph.node_map())[:1] == ("rules",)
    assert "causal_links" not in graph.node_map()
    assert graph.metadata["resolved_profile_hash"] == profile.content_hash
