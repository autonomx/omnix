from __future__ import annotations

import threading
import time

from app.gateway.live_voice_runtime_offload import (
    CachedTtsProviderResolver,
    DeliveryPersistenceWorker,
)


def test_delivery_persistence_runs_without_blocking_caller() -> None:
    started = threading.Event()
    release = threading.Event()
    finished = threading.Event()
    worker_thread_ids: list[int] = []

    def persist(_details: dict[str, object]) -> None:
        worker_thread_ids.append(threading.get_ident())
        started.set()
        release.wait(1.0)
        finished.set()

    worker = DeliveryPersistenceWorker(persist, max_queue_size=8, log=lambda *_args, **_kwargs: None)
    caller_thread_id = threading.get_ident()
    started_at = time.perf_counter()
    worker.enqueue({"assistant_turn_id": "assistant-turn:test"})
    caller_elapsed = time.perf_counter() - started_at

    assert caller_elapsed < 0.025
    assert started.wait(1.0)
    assert worker_thread_ids == [worker_thread_ids[0]]
    assert worker_thread_ids[0] != caller_thread_id

    release.set()
    assert finished.wait(1.0)
    worker.stop(timeout=1.0)


def test_cached_provider_returns_immediately_while_refresh_runs() -> None:
    provider = object()
    refresh_finished = threading.Event()
    calls = 0

    def resolve() -> object:
        nonlocal calls
        calls += 1
        time.sleep(0.050)
        if calls >= 2:
            refresh_finished.set()
        return provider

    resolver = CachedTtsProviderResolver(
        resolve,
        active_streams=lambda: {},
        refresh_seconds=0.010,
        log=lambda *_args, **_kwargs: None,
    )
    assert resolver.refresh() is provider
    time.sleep(0.015)

    started_at = time.perf_counter()
    assert resolver.get() is provider
    caller_elapsed = time.perf_counter() - started_at

    assert caller_elapsed < 0.025
    assert refresh_finished.wait(1.0)
    assert calls == 2


def test_cached_provider_defers_refresh_during_active_tts() -> None:
    provider = object()
    calls = 0

    def resolve() -> object:
        nonlocal calls
        calls += 1
        return provider

    resolver = CachedTtsProviderResolver(
        resolve,
        active_streams=lambda: {"stream-1": {"age_ms": 10.0}},
        refresh_seconds=0.001,
        log=lambda *_args, **_kwargs: None,
    )
    assert resolver.refresh() is provider
    time.sleep(0.005)

    assert resolver.get() is provider
    time.sleep(0.025)
    assert calls == 1
