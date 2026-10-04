from app.rpg.session.genesis.canon_audit import CanonAuditReport
from app.rpg.session.genesis.canon_compiler import compile_campaign_bible
from app.rpg.session.genesis.world_forge_generation import (
    GeneratedTopic,
    WorldForgeGenerationResult,
    WorldForgeJobRecord,
)


def test_presentation_only_document_is_not_compiled_as_canon_retrieval() -> None:
    topic = GeneratedTopic(
        topic_id="actors",
        documents=(
            {
                "document_id": "document:ada",
                "topic_id": "actors",
                "title": "Unverified Biography",
                "full_text": "Ada commands an orbital fleet.",
                "summary_120": "Ada commands an orbital fleet.",
                "summary_500": "Ada commands an orbital fleet from a hidden moon base.",
                "authority": "presentation_only",
                "canonical_source_fact_ids": ["fact:actor_ada:goal"],
                "entities": ["actor:ada"],
                "visibility": "game_master_canon",
            },
        ),
        entities=(
            {
                "id": "actor:ada",
                "kind": "actor",
                "name": "Ada",
                "goal": "Restore the tidal warning network before autumn storms.",
                "dossier_status": "complete",
                "visibility": "game_master_canon",
            },
        ),
        facts=(
            {
                "id": "fact:actor_ada:goal",
                "subject": "actor:ada",
                "predicate": "goal",
                "object": "Restore the tidal warning network before autumn storms.",
                "content": "Ada: goal is to restore the tidal warning network.",
                "authority": "generated_proposal",
                "approved_authority": "objective_canon",
                "entity_refs": ["actor:ada"],
                "visibility": "game_master_canon",
            },
        ),
    )
    generation = WorldForgeGenerationResult(
        topics=(topic,),
        jobs=(WorldForgeJobRecord("actors", "completed", (), "world_forge"),),
        failed_topic_ids=(),
        generation_order=(("actors",),),
    )

    compilation = compile_campaign_bible(
        generation,
        compiled_relationships=(),
        audit=CanonAuditReport(True),
        topic_graph={"launch_required_topic_ids": []},
        campaign_id="campaign:test",
        campaign_template="test",
        starting_location="",
    )

    cards = compilation.document["retrieval_cards"]
    assert any(card.get("fact_id") == "fact:actor_ada:goal" for card in cards)
    assert not any(card.get("document_id") == "document:ada" for card in cards)
    assert all(card["authority"] == "objective_canon" for card in cards)
    assert compilation.document["documents"][0]["authority"] == "presentation_only"
