from app.rpg.session.genesis.canon_relationships import (
    compile_cross_domain_relationships,
)
from app.rpg.session.genesis.world_forge_generation import GeneratedTopic


def test_typed_reference_facts_compile_cross_domain_relationships() -> None:
    topic = GeneratedTopic(
        topic_id="actors",
        entities=(
            {
                "id": "actor:ada",
                "kind": "actor",
                "name": "Ada",
                "location_id": "place:harbor",
                "group_ids": ["group:wardens"],
            },
        ),
        facts=(
            {
                "id": "fact:actor_ada:location_id",
                "subject": "actor:ada",
                "predicate": "location_id",
                "field_id": "location_id",
                "object": "place:harbor",
                "value_type": "entity_ref",
                "content": "Ada is located at the harbor.",
                "source": "profile_structured_fact_compiler_v1",
                "visibility": "game_master_canon",
            },
            {
                "id": "fact:actor_ada:group_ids",
                "subject": "actor:ada",
                "predicate": "group_ids",
                "field_id": "group_ids",
                "object": ["group:wardens"],
                "value_type": "entity_ref_list",
                "content": "Ada belongs to the Wardens.",
                "source": "profile_structured_fact_compiler_v1",
                "visibility": "game_master_canon",
            },
        ),
    )

    relationships = compile_cross_domain_relationships((topic,))
    by_kind = {row["kind"]: row for row in relationships}

    assert by_kind["location"]["source_id"] == "actor:ada"
    assert by_kind["location"]["target_id"] == "place:harbor"
    assert by_kind["location"]["compiled_by"] == (
        "profile_typed_relationship_compiler_v1"
    )
    assert by_kind["group"]["target_id"] == "group:wardens"
    assert "present_at" not in by_kind
