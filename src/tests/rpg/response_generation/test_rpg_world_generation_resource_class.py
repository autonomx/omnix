from __future__ import annotations

from app.jobs.models import CreateJobRequest, JobRecord, ResourceClass


def test_internal_rpg_worker_resource_classes_are_runtime_valid_but_not_public() -> None:
    schema = CreateJobRequest.model_json_schema()
    public_values = schema["$defs"]["ResourceClass"]["enum"]

    assert ResourceClass.RPG_WORLD_GENERATION.value not in public_values
    assert ResourceClass.RPG_MAP_MATERIALIZATION.value not in public_values
    assert ResourceClass.RPG_CAMPAIGN_GENESIS.value in public_values

    world_job = JobRecord.model_validate(
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
    map_job = JobRecord.model_validate(
        {
            "id": "world-map:test",
            "module": "rpg",
            "type": "rpg.world.map.materialize",
            "status": "queued",
            "resource_class": "rpg_map_materialization",
            "created_at": "2026-07-16T00:00:00Z",
            "updated_at": "2026-07-16T00:00:00Z",
        }
    )

    assert world_job.resource_class is ResourceClass.RPG_WORLD_GENERATION
    assert map_job.resource_class is ResourceClass.RPG_MAP_MATERIALIZATION
