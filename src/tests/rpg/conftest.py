from __future__ import annotations

import pytest


@pytest.fixture(scope="session", autouse=True)
def register_feature_repositories_for_rpg_tests():
    """Use the same lazy feature repository registrations as app composition."""
    from app.persistence.repository_registry import (
        install_repository_specs,
        reset_repository_specs,
    )
    from app.persistence.shared_repository_specs import shared_repository_specs
    from app.runtime.config import RuntimeConfig
    from app.runtime.feature_catalog import enabled_feature_ids, load_feature

    reset_repository_specs()
    install_repository_specs(shared_repository_specs())
    from app.runtime_composition import shared_service_repository_specs

    install_repository_specs(shared_service_repository_specs())
    for feature_id in enabled_feature_ids(RuntimeConfig()):
        install_repository_specs(tuple(load_feature(feature_id).repositories))
    yield
    reset_repository_specs()


@pytest.fixture(autouse=True)
def in_memory_narrative_responses(request, monkeypatch):
    """Engine tests keep canonical responses in memory unless they test PostgreSQL.

    The production default follows the runtime (PostgreSQL), which needs a
    campaign row for every response; the engine tests do not create campaigns.
    """
    from app.rpg.narrative_repository import _cached_repository

    if request.node.get_closest_marker("postgres") is None:
        monkeypatch.setenv("OMNIX_RPG_NARRATIVE_REPOSITORY", "in_memory")
    _cached_repository.cache_clear()
    yield
    _cached_repository.cache_clear()
