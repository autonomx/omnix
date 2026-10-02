from app.jobs.models import CreateJobRequest, ResourceClass
from app.rpg.jobs.turn_job_guard import rpg_turn_submission_policy


def test_character_job_owner_maps_to_local_user_and_preserves_subject() -> None:
    request = CreateJobRequest(
        owner_id="character:anaka",
        module="character-avatar",
        type="image.generate",
        resource_class=ResourceClass.GPU_IMAGE,
        compat={"character_id": "anaka"},
    )

    normalized = rpg_turn_submission_policy(request)

    assert normalized.owner_id == "user:local"
    assert normalized.compat == {
        "character_id": "anaka",
        "subject_owner_id": "character:anaka",
    }
    assert request.owner_id == "character:anaka"
    assert request.compat == {"character_id": "anaka"}


def test_user_job_owner_remains_unchanged() -> None:
    request = CreateJobRequest(
        owner_id="user:local",
        module="image-generation",
        type="image.generate",
        resource_class=ResourceClass.GPU_IMAGE,
    )

    normalized = rpg_turn_submission_policy(request)

    assert normalized.owner_id == request.owner_id
    assert normalized.compat == request.compat
