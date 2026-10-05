from __future__ import annotations

import asyncio
import contextvars
import threading

import pytest

from app.runtime.model_executor import ModelExecutor

REQUEST = contextvars.ContextVar("request", default="")


def test_work_runs_on_named_pool_threads_with_the_callers_context() -> None:
    executor = ModelExecutor("probe", max_workers=2)

    def work(value: int) -> tuple[int, str, str]:
        return value * 2, threading.current_thread().name, REQUEST.get()

    async def call() -> tuple[int, str, str]:
        REQUEST.set("request-1")
        return await executor.run(work, 21)

    try:
        doubled, thread_name, request = asyncio.run(call())
    finally:
        executor.shutdown()

    assert doubled == 42
    assert thread_name.startswith("omnix-probe")
    assert request == "request-1"


def test_the_pool_needs_at_least_one_worker() -> None:
    with pytest.raises(ValueError):
        ModelExecutor("empty", max_workers=0)
