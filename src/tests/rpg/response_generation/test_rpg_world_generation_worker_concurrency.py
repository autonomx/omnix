from __future__ import annotations

import app.rpg.worlds.generation_worker as generation_worker
from app.rpg.worlds.generation_worker import (
    _WorkerPoolState,
    _worker_loop,
    world_generation_worker_limit,
)


def test_lmstudio_world_generation_defaults_to_two_workers() -> None:
    assert world_generation_worker_limit(
        {"OMNIX_RPG_WORLD_FORGE_PROVIDER": "lmstudio"}
    ) == 2


def test_lmstudio_namespaced_provider_defaults_to_two_workers() -> None:
    assert world_generation_worker_limit(
        {"OMNIX_RPG_WORLD_FORGE_PROVIDER": "llm:lmstudio"}
    ) == 2


def test_cloud_world_generation_keeps_bounded_parallelism() -> None:
    assert world_generation_worker_limit(
        {"OMNIX_RPG_WORLD_FORGE_PROVIDER": "cerebras"}
    ) == 2


def test_world_generation_worker_override_is_bounded() -> None:
    assert world_generation_worker_limit(
        {
            "OMNIX_RPG_WORLD_FORGE_PROVIDER": "lmstudio",
            "OMNIX_RPG_WORLD_GENERATION_WORKERS": "3",
        }
    ) == 2
    assert world_generation_worker_limit(
        {"OMNIX_RPG_WORLD_GENERATION_WORKERS": "99"}
    ) == 2


def test_worker_pool_survives_a_short_empty_queue_between_dag_jobs(
    monkeypatch,
) -> None:
    responses = iter(
        [
            None,
            {"ok": True, "status": "completed"},
            None,
            None,
        ]
    )
    calls: list[int] = []

    def run_once(**kwargs):
        del kwargs
        calls.append(1)
        return next(responses)

    monkeypatch.setattr(generation_worker, "run_world_generation_worker_once", run_once)
    monkeypatch.setattr(generation_worker, "_DAG_IDLE_POLL_SECONDS", 0)
    monkeypatch.setattr(generation_worker, "_DAG_IDLE_POLLS_BEFORE_STOP", 2)
    state = _WorkerPoolState()

    _worker_loop(1, None, state)

    assert len(calls) == 4
    assert state.completion_generation == 1
    assert state.stop is True
