from app.platform.characters.avatar_generation_service import CharacterAvatarGenerationService
from app.platform.characters.avatar_viseme_generation import CharacterVisemeGenerationService
from app.platform.characters.persistence import avatar_generation_repository
from app.persistence import runtime as persistence_runtime


def test_avatar_generation_uses_postgres_repository_in_postgres_runtime(monkeypatch) -> None:
    repository = object()
    monkeypatch.setattr(persistence_runtime, "uses_postgresql_runtime", lambda: True)
    monkeypatch.setattr(
        avatar_generation_repository,
        "PostgresCharacterAvatarGenerationRepositoryAdapter",
        lambda: repository,
    )

    service = CharacterAvatarGenerationService()

    assert service.repository is repository


def test_viseme_generation_uses_postgres_repository_in_postgres_runtime(monkeypatch) -> None:
    repository = object()
    monkeypatch.setattr(persistence_runtime, "uses_postgresql_runtime", lambda: True)
    monkeypatch.setattr(
        avatar_generation_repository,
        "PostgresCharacterVisemeGenerationRepositoryAdapter",
        lambda: repository,
    )

    service = CharacterVisemeGenerationService(
        character_service=object(),
        avatar_service=object(),
        job_store=object(),
    )

    assert service.repository is repository
