from app.rpg.session.genesis.canon_relationships import (
    compile_cross_domain_relationships,
)
from app.rpg.session.genesis.world_forge_generation import GeneratedTopic


def test_causal_links_compile_event_to_effect_relationships() -> None:
    topic = GeneratedTopic(
        topic_id="causal_links",
        entities=(
            {
                "id": "ent:causal:001",
                "kind": "causal_link",
                "name": "Copper War founded Ironford",
                "cause_event_ids": ["ent:historical_event:001"],
                "effect_id": "ent:place:003",
                "effect_type": "founded",
                "mechanism": "The army required a permanent fortified river crossing.",
                "persistence": "continuing",
                "start_year": 411,
                "end_year": 414,
                "visibility": "game_master_canon",
            },
        ),
    )

    relationships = compile_cross_domain_relationships((topic,))
    row = next(
        relationship
        for relationship in relationships
        if relationship["compiled_by"] == "causal_relationship_compiler_v1"
    )

    assert row["source_id"] == "ent:historical_event:001"
    assert row["target_id"] == "ent:place:003"
    assert row["kind"] == "founded"
    assert row["causal_link_id"] == "ent:causal:001"
    assert row["persistence"] == "continuing"
    assert row["start_year"] == 411
    assert row["end_year"] == 414
    assert set(row["entity_refs"]) == {
        "ent:historical_event:001",
        "ent:place:003",
        "ent:causal:001",
    }


def test_multi_cause_link_compiles_one_relationship_per_event() -> None:
    topic = GeneratedTopic(
        topic_id="causal_links",
        entities=(
            {
                "id": "ent:causal:002",
                "kind": "causal_link",
                "cause_event_ids": [
                    "ent:historical_event:001",
                    "ent:historical_event:002",
                ],
                "effect_id": "ent:group:001",
                "effect_type": "fragmented",
                "mechanism": "Two defeats split the old command hierarchy.",
                "persistence": "continuing",
            },
        ),
    )

    rows = tuple(
        row
        for row in compile_cross_domain_relationships((topic,))
        if row["compiled_by"] == "causal_relationship_compiler_v1"
    )

    assert len(rows) == 2
    assert {row["source_id"] for row in rows} == {
        "ent:historical_event:001",
        "ent:historical_event:002",
    }
    assert {row["target_id"] for row in rows} == {"ent:group:001"}
