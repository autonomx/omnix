from __future__ import annotations

from app.jobs.models import CreateJobRequest, JobRecord, ResourceClass


def test_world_generation_resource_class_is_runtime_valid_but_not_public() -> None:
    schema = CreateJobRequest.model_json_schema()
    public_values = schema["$defs"]["ResourceClass"]["enum"]

    assert ResourceClass.RPG_WORLD_GENERATION.value not in public_values
    assert ResourceClass.RPG_CAMPAIGN_GENESIS.value in public_values

    job = JobRecord.model_validate(
        {
            "id": "world-topic:test",
            "module": "rpg",
            "type": "rpg.world.topic.generate",
            "status": "queued",
            "resource_class": "rpg_world_generation",
            "created_at": "2026-07-16T00:00:00Z",
            "updated_at": "2026-07-16T00:00:00Z",
        }
    )

    assert job.resource_class is ResourceClass.RPG_WORLD_GENERATION
