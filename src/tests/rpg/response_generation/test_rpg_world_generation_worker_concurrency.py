from __future__ import annotations

from app.rpg.worlds.generation_worker import world_generation_worker_limit


def test_lmstudio_world_generation_defaults_to_four_workers() -> None:
    assert world_generation_worker_limit(
        {"OMNIX_RPG_WORLD_FORGE_PROVIDER": "lmstudio"}
    ) == 4


def test_lmstudio_namespaced_provider_defaults_to_four_workers() -> None:
    assert world_generation_worker_limit(
        {"OMNIX_RPG_WORLD_FORGE_PROVIDER": "llm:lmstudio"}
    ) == 4


def test_cloud_world_generation_keeps_bounded_parallelism() -> None:
    assert world_generation_worker_limit(
        {"OMNIX_RPG_WORLD_FORGE_PROVIDER": "cerebras"}
    ) == 4


def test_world_generation_worker_override_is_bounded() -> None:
    assert world_generation_worker_limit(
        {
            "OMNIX_RPG_WORLD_FORGE_PROVIDER": "lmstudio",
            "OMNIX_RPG_WORLD_GENERATION_WORKERS": "3",
        }
    ) == 3
    assert world_generation_worker_limit(
        {"OMNIX_RPG_WORLD_GENERATION_WORKERS": "99"}
    ) == 4
