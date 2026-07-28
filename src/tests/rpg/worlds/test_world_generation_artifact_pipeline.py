from app.rpg.session.genesis.world_forge_default import ReferenceSafeWorldForgeGenerator
from app.rpg.session.genesis.world_forge_deterministic import (
    DeterministicWorldForgeGenerator,
)
from app.rpg.session.genesis.world_forge_generation import generate_campaign_topics
from app.rpg.session.genesis.world_forge_profile_generation import (
    resolve_or_generate_genre_profile,
)
from app.rpg.session.genesis.world_forge_profile_graph import build_profile_topic_graph
from app.rpg.worlds.generation_jobs import canonical_hash
from app.rpg.worlds.generation_publication import (
    compile_world_generation_publication,
)


def test_profile_world_publication_reaches_playtested_stage() -> None:
    resolution = resolve_or_generate_genre_profile(
        genre="fallout style",
        description="A flooded nuclear coast linked by fortified ferry settlements.",
    )
    graph = build_profile_topic_graph(
        resolution.profile,
        campaign_template="open_world",
        depth="quick",
        tone="survival satire",
        starting_location="place:harbor",
        runtime_capabilities={"living_world": True},
    )
    generation_context = {
        "world_id": "world:artifact",
        "campaign_template": "open_world",
        "genre": "fallout style",
        "tone": "survival satire",
        "starting_location": "place:harbor",
        "world_brief": {
            "title": "The Flooded Coast",
            "description": (
                "A flooded nuclear coast linked by fortified ferry settlements."
            ),
            "genre": "fallout style",
            "tone": "survival satire",
            "campaign_template": "open_world",
        },
        "resolved_genre_profile": resolution.profile.as_dict(),
        "resolved_profile_hash": resolution.profile.content_hash,
    }
    generated = generate_campaign_topics(
        graph,
        generator=ReferenceSafeWorldForgeGenerator(
            DeterministicWorldForgeGenerator()
        ),
        seed=17,
        campaign_context=generation_context,
    )
    assert generated.passed, {
        job.topic_id: job.error
        for job in generated.jobs
        if job.status != "completed"
    }
    topic_rows = [
        {
            "topic_id": topic.topic_id,
            "status": "ready",
            "content": topic.as_dict(),
            "content_hash": canonical_hash(topic.as_dict()),
        }
        for topic in generated.topics
    ]
    publication = compile_world_generation_publication(
        run={
            "run_id": "run:artifact",
            "draft_revision": 1,
            "graph": graph.as_dict(),
            "context": {"generation_context": generation_context},
            "settings": {"generator_version": "deterministic-profile-v1"},
        },
        world={
            "id": "world:artifact",
            "title": "The Flooded Coast",
            "genre": "fallout style",
            "seed": 17,
            "metadata": {"starting_location": "place:harbor"},
        },
        topic_rows=topic_rows,
        revision=1,
    )

    release = publication.world_release
    assert release.artifact_stage == "playtested"
    assert release.certification["launch_ready"] is True
    assert release.certification["artifact_readiness"] == {
        "canon_validated": True,
        "runtime_seeded": True,
        "materialized": True,
        "playtested": True,
        "highest_stage": "playtested",
    }
    assert release.runtime_seed["passed"] is True
    assert release.materialization["passed"] is True
    assert release.playtest_report["passed"] is True
    assert release.playtest_report["checks"]["save_load_equivalent"] is True
    assert release.runtime_seed["content_hash"] == release.certification[
        "runtime_seed_hash"
    ]
