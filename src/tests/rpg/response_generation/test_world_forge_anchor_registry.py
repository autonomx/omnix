from app.rpg.session.genesis.world_forge_anchor_registry import (
    allocate_global_anchor_registry,
    anchor_slice_for_domain,
    validate_global_anchor_registry,
)
from app.rpg.session.genesis.world_forge_generation import (
    GeneratedTopic,
    generate_campaign_topics,
)
from app.rpg.session.genesis.world_forge_profile_generation import (
    default_profile_registry,
)
from app.rpg.session.genesis.world_forge_profile_graph import build_profile_topic_graph


def _graph():
    profile = default_profile_registry().resolve("fantasy")
    assert profile is not None
    return build_profile_topic_graph(
        profile,
        campaign_template="anchor-registry",
        depth="quick",
    )


def test_global_anchor_registry_allocates_only_major_stable_slots() -> None:
    registry = allocate_global_anchor_registry(
        _graph(),
        seed=17,
        world_key="campaign:one",
    )

    assert validate_global_anchor_registry(registry) == ()
    assert registry == allocate_global_anchor_registry(
        _graph(),
        seed=17,
        world_key="campaign:one",
    )
    domains = {row["domain_id"] for row in registry["anchors"]}
    assert domains == {
        "regions",
        "places",
        "groups",
        "cultures",
        "actors",
        "history_timeline",
    }
    assert all(row["anchor_kind"] != "minor_actor" for row in registry["anchors"])
    assert len({row["id"] for row in registry["anchors"]}) == len(registry["anchors"])


def test_anchor_slice_contains_only_requested_domain() -> None:
    registry = allocate_global_anchor_registry(
        _graph(),
        seed=4,
        world_key="campaign:two",
    )
    places = anchor_slice_for_domain("places", registry)

    assert places["registry_hash"] == registry["registry_hash"]
    assert places["anchors"]
    assert {row["domain_id"] for row in places["anchors"]} == {"places"}
    assert all(row["id"].startswith("ent:places:") for row in places["anchors"])


def test_scheduler_injects_only_permitted_anchor_slice() -> None:
    graph = _graph()
    registry = allocate_global_anchor_registry(
        graph,
        seed=9,
        world_key="campaign:three",
    )
    observed: dict[str, dict] = {}

    class Generator:
        def generate(self, node, *, seed, campaign_context, dependency_topics):
            observed[node.topic_id] = dict(campaign_context.get("planning_slice") or {})
            return GeneratedTopic(topic_id=node.topic_id)

    result = generate_campaign_topics(
        graph,
        generator=Generator(),
        seed=9,
        campaign_context={"planning_topics": {"anchor_registry": registry}},
        max_parallel_jobs=1,
    )

    assert result.passed
    place_registry = observed["places"]["anchor_registry"]
    actor_registry = observed["actors"]["anchor_registry"]
    assert {row["domain_id"] for row in place_registry["anchors"]} == {"places"}
    assert {row["domain_id"] for row in actor_registry["anchors"]} == {"actors"}
    assert "anchor_registry" not in observed["pressures"]
