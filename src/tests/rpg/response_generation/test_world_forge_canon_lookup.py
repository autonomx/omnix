import json

from app.rpg.session.genesis.world_forge_canon_lookup import (
    attach_structured_canon_lookup,
)
from app.rpg.session.genesis.world_forge_contract import CampaignTopicNode
from app.rpg.session.genesis.world_forge_fact_pipeline import (
    compile_structured_entity_facts,
)
from app.rpg.session.genesis.world_forge_generation import GeneratedTopic


def test_profile_fields_compile_to_exact_runtime_lookup_json() -> None:
    node = CampaignTopicNode(
        topic_id="actors",
        title="Actors and NPCs",
        category="actors",
        metadata={
            "entity_kind": "actor",
            "field_definitions": [
                {"field_id": "name", "value_type": "string", "required": True},
                {"field_id": "goal", "value_type": "string", "required": True},
                {
                    "field_id": "location_id",
                    "value_type": "entity_ref",
                    "required": True,
                    "allowed_target_domains": ["places"],
                },
            ],
        },
    )
    places = GeneratedTopic(
        topic_id="places",
        entities=(
            {"id": "place:night_market", "kind": "place", "name": "Night Market"},
        ),
    )
    topic = GeneratedTopic(
        topic_id="actors",
        entities=(
            {
                "id": "actor:nyra",
                "kind": "actor",
                "name": "Nyra Vek",
                "goal": "Expose the Helix Directorate's memory-auction ledger.",
                "location_id": "place:night_market",
            },
        ),
        provenance={"generator": "structured_world_forge_provider_v1"},
    )

    compiled = compile_structured_entity_facts(node, topic, {"places": places})
    enriched = attach_structured_canon_lookup(compiled)
    goal_fact = next(
        row for row in enriched.facts if row.get("predicate") == "goal"
    )

    assert goal_fact["display_text"].startswith("Nyra Vek: goal is")
    assert goal_fact["lookup"] == {
        "subject": "actor:nyra",
        "predicate": "goal",
        "object": "Expose the Helix Directorate's memory-auction ledger.",
        "value_type": "string",
        "semantic_role": "",
        "topic_id": "actors",
        "entity_refs": ["actor:nyra"],
    }
    assert json.loads(goal_fact["content"]) == goal_fact["lookup"]
    assert enriched.provenance["structured_canon_lookup_schema"] == (
        "rpg_structured_canon_lookup_v1"
    )
    assert enriched.provenance["structured_canon_fact_index"]["actor:nyra"]["goal"] == goal_fact["id"]
