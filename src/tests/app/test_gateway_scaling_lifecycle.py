import asyncio
import os
from pathlib import Path
import subprocess
import sys
import threading
from types import SimpleNamespace

import pytest

from app.gateway.background_runtime import GatewayBackgroundRuntime
from app.gateway.lifecycle import gateway_lifespan
from app.chat import generation_jobs as jobs
from app.trading.metric_data import BinanceLiquidationBuffer


def test_gateway_composition_does_not_patch_fastapi_constructor():
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[2]))
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from fastapi import FastAPI; original = FastAPI.__init__; "
            "from app.gateway.main import create_gateway_app; gateway = create_gateway_app(); "
            "assert FastAPI.__init__ is original; "
            "assert not any(getattr(r, 'path', '').startswith('/api/') for r in FastAPI(title='Omnix Web Gateway').routes); "
            "assert gateway.state.features_registered",
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr


def test_lifecycle_cleans_partial_startup_and_continues_after_shutdown_failure():
    calls = []

    async def start():
        calls.append("start")
        raise ValueError("failed startup")

    def fail_stop():
        calls.append("failed stop")
        raise RuntimeError("failed shutdown")

    app = SimpleNamespace(
        state=SimpleNamespace(runtime_started=False),
        router=SimpleNamespace(
            on_startup=[start],
            on_shutdown=[lambda: calls.append("other stop"), fail_stop],
        ),
    )

    async def run():
        with pytest.raises(RuntimeError, match="shutdown callbacks"):
            async with gateway_lifespan(
                app,
                get_chat_store=object,
                get_job_store=object,
                recover_jobs=lambda *_: 0,
            ):
                pytest.fail("Failed startup became ready")

    asyncio.run(run())
    assert calls == ["start", "failed stop", "other stop"]
    assert app.state.runtime_started is False


def test_background_supervision_stops_partial_startup_in_reverse_order(monkeypatch):
    calls = []
    owner = GatewayBackgroundRuntime(object(), "workspace")
    monkeypatch.setattr(owner, "acquire", lambda: calls.append("acquire"))
    monkeypatch.setattr(owner, "release", lambda: calls.append("release"))
    monkeypatch.setattr(owner, "require_live", lambda: None)

    def fail():
        calls.append("second start")
        raise ValueError("failed worker")

    owner.register(
        "one",
        object(),
        [lambda: calls.append("first start")],
        [lambda: calls.append("first stop")],
    )
    owner.register("two", object(), [fail], [lambda: calls.append("second stop")])

    async def run():
        with pytest.raises(ValueError):
            async with owner.lifespan():
                await owner.startup()

    asyncio.run(run())
    assert calls == [
        "acquire",
        "first start",
        "second start",
        "second stop",
        "first stop",
        "release",
    ]


def test_dispatcher_shutdown_discards_pending_work_and_rejects_new_submissions():
    dispatcher = jobs._ChatGenerationDispatcher()
    dispatcher._started = True
    store = SimpleNamespace(
        get_job=lambda _: SimpleNamespace(status=jobs.JobStatus.COMPLETED)
    )
    item = jobs._ChatGenerationWork(
        chat_store=None,
        job_store=store,
        job=SimpleNamespace(id="closing", input_payload={"session_id": "session"}),
        request=None,
        context_builder=None,
        completion_hook=None,
    )
    dispatcher.submit(item)
    assert dispatcher.close() == 0
    assert dispatcher._outstanding == 0
    assert not dispatcher._pending
    with pytest.raises(jobs.ChatQueueFull):
        dispatcher.submit(item)


def test_api_role_never_starts_liquidation_streams_and_collector_shutdown_is_bounded(
    monkeypatch,
):
    monkeypatch.setenv("OMNIX_GATEWAY_BACKGROUND_ROLE", "api")
    buffer = BinanceLiquidationBuffer()
    buffer.ensure_started("BTCUSDT")
    assert buffer._threads == {}
    monkeypatch.setenv("OMNIX_GATEWAY_BACKGROUND_ROLE", "worker")
    entered = threading.Event()

    async def run(symbol):
        entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(buffer, "_run_async", run)
    buffer.ensure_started("BTCUSDT")
    assert entered.wait(1)
    buffer.close(1)
    assert not buffer.is_collecting("BTCUSDT")
    buffer.ensure_started("BTCUSDT")
    assert not buffer.is_collecting("BTCUSDT")


def test_canceled_providers_keep_capacity_until_their_invocations_exit(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor

    monkeypatch.setattr(jobs, "_provider_slots", threading.BoundedSemaphore(2))
    entered = []
    both_entered, release = threading.Event(), threading.Event()
    state = SimpleNamespace(status=jobs.JobStatus.RUNNING)
    store = SimpleNamespace(get_job=lambda _: state)

    def generate(*args, **kwargs):
        entered.append(True)
        if len(entered) == 2:
            both_entered.set()
        release.wait(3)
        return {"content": "late output"}

    monkeypatch.setattr(jobs, "_generate_reply", generate)

    def invoke(index):
        with pytest.raises(jobs._ChatGenerationInterrupted):
            jobs._generate_reply_with_interrupt(
                chat_store=None,
                job_store=store,
                session=None,
                user_message=None,
                request=None,
                context_items=[],
                job=SimpleNamespace(id=str(index)),
            )

    try:
        with ThreadPoolExecutor(6) as executor:
            futures = [executor.submit(invoke, index) for index in range(6)]
            assert both_entered.wait(1)
            state.status = jobs.JobStatus.CANCELED
            for future in futures:
                future.result(timeout=2)
        assert len(entered) == 2
        assert jobs._provider_slots._value == 0
    finally:
        release.set()


def test_delivery_worker_restarts_explicitly_and_drops_post_shutdown_checkpoints():
    from app.gateway.live_voice_runtime_offload import DeliveryPersistenceWorker

    received = []
    finished = threading.Event()

    def persist(payload):
        received.append(payload)
        finished.set()

    worker = DeliveryPersistenceWorker(persist, log=lambda *args: None)
    worker.enqueue({"turn": "first"})
    assert finished.wait(1)
    worker.stop(1)
    worker.enqueue({"turn": "closed"})
    assert worker._queue.empty()
    worker.start()
    finished.clear()
    worker.enqueue({"turn": "second"})
    assert finished.wait(1)
    worker.stop(1)
    assert received == [{"turn": "first"}, {"turn": "second"}]
