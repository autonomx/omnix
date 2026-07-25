from __future__ import annotations

from app.rpg.session.genesis.world_forge_default import ReferenceSafeWorldForgeGenerator
from app.rpg.session.genesis.world_forge_generation import GeneratedTopic


def test_manual_field_retry_preserves_unselected_entities_and_fields() -> None:
    prior = GeneratedTopic(
        topic_id="actors",
        entities=(
            {
                "id": "actor:ada",
                "kind": "actor",
                "name": "Ada",
                "motivation": "Protect the relay workers.",
                "next_action": "Wait.",
            },
            {
                "id": "actor:bram",
                "kind": "actor",
                "name": "Bram",
                "motivation": "Control the harbor cranes.",
                "next_action": "Inspect the eastern crane.",
            },
        ),
    )
    generated = GeneratedTopic(
        topic_id="actors",
        entities=(
            {
                "id": "actor:ada",
                "kind": "actor",
                "name": "Changed Ada",
                "motivation": "Changed motivation.",
                "next_action": "Inspect the flooded relay chamber.",
            },
            {
                "id": "actor:bram",
                "kind": "actor",
                "name": "Changed Bram",
                "motivation": "Abandon the harbor.",
                "next_action": "Leave immediately.",
            },
        ),
    )

    scoped = ReferenceSafeWorldForgeGenerator._manual_retry_candidate(
        generated,
        {
            "topic_directives": {
                "manual_retry": {
                    "prior_candidate": prior.as_dict(),
                    "scope": "entity_fields",
                    "entity_ids": ["actor:ada"],
                    "fields": ["next_action"],
                    "reason_codes": ["weak_operational_state"],
                    "instructions": ["Replace the placeholder with a concrete action."],
                }
            }
        },
    )

    assert scoped.entities[0]["name"] == "Ada"
    assert scoped.entities[0]["motivation"] == "Protect the relay workers."
    assert scoped.entities[0]["next_action"] == "Inspect the flooded relay chamber."
    assert scoped.entities[1] == prior.entities[1]
    assert scoped.provenance["targeted_regeneration_updated_fields"] == ["next_action"]
