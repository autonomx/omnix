from __future__ import annotations

from app.jobs.models import CreateJobRequest, ResourceClass


def test_character_avatar_semantic_owner_is_not_used_as_postgres_user_fk(monkeypatch) -> None:
    import app.platform.effective_defaults as defaults

    monkeypatch.setattr(defaults, "load_settings", lambda: {})

    request = CreateJobRequest(
        owner_id="character:donald-trump",
        module="character-avatar",
        type="image.generate",
        resource_class=ResourceClass.GPU_IMAGE,
        input_payload={
            "prompt": "portrait",
            "metadata": {"character_id": "donald-trump"},
        },
        compat={"character_id": "donald-trump"},
    )

    assert request.owner_id is None
    assert request.compat["character_id"] == "donald-trump"
    assert request.compat["subject_owner_id"] == "character:donald-trump"


def test_non_character_job_owner_is_preserved() -> None:
    request = CreateJobRequest(
        owner_id="user:local",
        module="maintenance",
        type="cleanup",
        resource_class=ResourceClass.CPU,
    )

    assert request.owner_id == "user:local"
    assert "subject_owner_id" not in request.compat
