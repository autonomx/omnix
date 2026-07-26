from app.rpg.session.genesis.world_forge_causal_presentation import (
    project_causal_link_presentations,
)
from app.rpg.session.genesis.world_forge_generation import GeneratedTopic
from app.rpg.session.genesis.world_forge_profile_generation import (
    default_profile_registry,
)
from app.rpg.session.genesis.world_forge_profile_graph import build_profile_topic_graph
from app.rpg_world_forge_provider import _payload


def _causal_node():
    profile = default_profile_registry().resolve("fantasy")
    assert profile is not None
    graph = build_profile_topic_graph(
        profile,
        campaign_template="causal-generation",
        depth="quick",
    )
    return graph.node_map()["causal_links"]


def test_causal_generation_contract_is_sent_in_provider_payload() -> None:
    node = _causal_node()
    contract = node.metadata["causal_generation_contract"]
    payload = _payload(
        node,
        seed=17,
        campaign_context={"world_brief": {"description": "River frontier"}},
        dependency_topics={},
    )

    assert contract["schema_version"] == "rpg_world_forge_causal_generation_v1"
    assert contract["topic_id"] == "causal_links"
    assert set(contract["authoritative_fields"]) == {"cause_event_ids", "effect_id"}
    assert payload["topic"]["metadata"]["causal_generation_contract"] == contract
    assert any("distinct cause/effect pairs" in rule for rule in contract["rules"])


def test_causal_presentation_is_a_structured_projection() -> None:
    topic = GeneratedTopic(
        topic_id="causal_links",
        entities=(
            {
                "id": "ent:causal:001",
                "cause_event_ids": ["event:war"],
                "effect_id": "place:ironford",
                "effect_type": "founded",
                "mechanism": "The army required a permanent fortified crossing.",
                "persistence": "continuing",
                "start_year": 411,
                "end_year": 414,
            },
        ),
    )

    rendered = project_causal_link_presentations(topic)
    entity = rendered.entities[0]

    assert entity["causal_presentation"] == {
        "cause_event_ids": ["event:war"],
        "effect_id": "place:ironford",
        "effect_type": "founded",
        "mechanism": "The army required a permanent fortified crossing.",
        "persistence": "continuing",
        "start_year": 411,
        "end_year": 414,
    }
    assert "permanent fortified crossing" in entity["short_summary"]
    assert rendered.provenance["causal_presentation_source"] == "structured_fields_only"
