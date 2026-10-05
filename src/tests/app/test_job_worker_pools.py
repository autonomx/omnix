from types import SimpleNamespace
import threading
import asyncio

import pytest

from app.config.runtime import GatewayRole, RuntimeConfig
from app.jobs.handlers import JobHandlerRegistry, JobHandlerSpec
from app.jobs.models import ResourceClass
from app.runtime.capabilities import RuntimeCapabilities, RuntimeCapability
from app.runtime.background import BackgroundWorker, GatewayBackgroundRuntime
from app.composition.worker.health import create_worker_health_app
from app.composition.worker.__main__ import build_parser
from app.composition.worker_runtime import DurableFeatureJobWorker
from app.composition.worker_runtime import durable_feature_worker
from app.composition.worker_runtime.pool_runtime import JobWorkerPoolRuntime
from app.composition.worker_runtime.pools import DEFAULT_POOLS, RESOURCE_POOLS, parse_pools


def test_default_pools_cover_each_registered_durable_resource_class():
    pools = parse_pools(DEFAULT_POOLS)
    covered = {resource for pool in pools for resource in pool.resource_classes}

    assert {ResourceClass(member).value for member in ResourceClass} <= covered
    assert {pool.name: pool.concurrency for pool in pools} == {
        "llm": 2,
        "image": 1,
        "tts": 1,
        "research": 2,
        "cpu": 4,
        "stt": 1,
    }


def test_pool_parser_rejects_unknown_duplicate_and_unsafe_concurrency():
    for value, reason in (
        ("gpu=1", "unknown job worker pool"),
        ("cpu=1,cpu=2", "duplicate job worker pool"),
        ("cpu=0", "between 1 and 64"),
        ("cpu=65", "between 1 and 64"),
        ("cpu=x", "must be an integer"),
        ("", "at least one"),
    ):
        with pytest.raises(ValueError, match=reason):
            parse_pools(value)


def test_worker_pools_claim_only_the_registered_types_in_their_resource_class():
    registry = JobHandlerRegistry((
        JobHandlerSpec(
            type="test.cpu",
            handler=lambda context, job: job,
            resource_class=ResourceClass.CPU,
        ),
        JobHandlerSpec(
            type="test.image",
            handler=lambda context, job: job,
            resource_class=ResourceClass.GPU_IMAGE,
        ),
        JobHandlerSpec(
            type="test.tts.preview",
            handler=lambda context, job: job,
            resource_class=ResourceClass.GPU_TTS_PREVIEW,
        ),
    ))
    pools = parse_pools("cpu=2,image=1,tts=3")
    runtime = JobWorkerPoolRuntime(object(), registry, pools)

    assert runtime.workers["cpu"].job_types == ("test.cpu",)
    assert runtime.workers["cpu"].resource_classes == ("cpu", "rpg_campaign_genesis", "rpg_map_materialization", "rpg_world_generation")
    assert runtime.workers["image"].job_types == ("test.image",)
    assert runtime.workers["tts"].job_types == ("test.tts.preview",)
    assert runtime.workers["tts"].max_concurrency == 3


def test_job_worker_role_has_no_gateway_or_scheduler_authority():
    config = RuntimeConfig(gateway_role=GatewayRole.JOB_WORKER)
    capabilities = RuntimeCapabilities.from_config(config)

    assert not config.owns_background_runtime
    assert not config.runs_schedulers
    assert config.allow_local_tts
    assert not capabilities.allows(RuntimeCapability.OWN_BACKGROUND_RUNTIME)
    assert not capabilities.allows(RuntimeCapability.RUN_SCHEDULERS)
    assert capabilities.allows(RuntimeCapability.SERVE_API)
    assert not capabilities.allows(RuntimeCapability.RUN_CHAT_DISPATCH)
    assert capabilities.allows(RuntimeCapability.RUN_JOB_WORKERS)


def test_only_job_worker_role_starts_feature_job_worker_hooks(monkeypatch):
    events = []
    job_worker = BackgroundWorker(
        name="feature-job-worker",
        monitor=object(),
        startup=(lambda: events.append("job-start"),),
        shutdown=(lambda: events.append("job-stop"),),
        requires=frozenset({RuntimeCapability.RUN_JOB_WORKERS}),
    )
    gateway = GatewayBackgroundRuntime(
        object(),
        "workspace:test",
        config=RuntimeConfig(gateway_role=GatewayRole.WORKER),
    )
    monkeypatch.setattr(gateway, "require_live", lambda: None)
    gateway.register_worker(job_worker)
    asyncio.run(gateway.startup())
    assert events == []

    standalone = GatewayBackgroundRuntime(
        object(),
        "workspace:test",
        config=RuntimeConfig(gateway_role=GatewayRole.JOB_WORKER),
    )
    standalone.register_worker(job_worker)
    asyncio.run(standalone.startup())
    assert events == ["job-start"]
    asyncio.run(standalone.shutdown())
    assert events == ["job-start", "job-stop"]


def test_job_worker_health_reports_each_pool_and_prometheus_metrics():
    class Runtime:
        ready = False

        def diagnostics(self):
            return {
                "ready": False,
                "pools": {
                    "cpu": {
                        "ready": True,
                        "active_jobs": 2,
                        "max_concurrency": 4,
                        "claim_count": 10,
                        "completed_count": 8,
                        "failure_count": 1,
                    },
                    "image": {
                        "ready": False,
                        "active_jobs": 0,
                        "max_concurrency": 1,
                        "claim_count": 0,
                        "completed_count": 0,
                        "failure_count": 0,
                    },
                },
            }

    from fastapi.testclient import TestClient

    client = TestClient(create_worker_health_app(Runtime()))
    readiness = client.get("/health/ready")
    metrics = client.get("/metrics")

    assert readiness.status_code == 503
    assert readiness.json()["pools"]["cpu"]["active_jobs"] == 2
    assert 'omnix_job_worker_pool_active_jobs{pool="cpu"} 2' in metrics.text
    assert 'omnix_job_worker_pool_ready{pool="image"} 0' in metrics.text
    assert "omnix_job_execution_seconds" in metrics.text


def test_cli_parser_uses_standalone_defaults_and_accepts_example_pools():
    args = build_parser().parse_args(
        ["--pools", "llm=2,image=1,tts=1,research=2,cpu=4"]
    )

    assert args.pools == "llm=2,image=1,tts=1,research=2,cpu=4"
    assert len(parse_pools()) == 6
    assert len(parse_pools(args.pools)) == 5


def test_worker_claim_query_is_filtered_by_pool_resources_and_types(monkeypatch):
    captured = {}

    class Jobs:
        def claim_next(self, context, **kwargs):
            captured.update(kwargs)
            return None

    class Work:
        jobs = Jobs()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def rollback(self):
            pass

    registry = JobHandlerRegistry((
        JobHandlerSpec("only.cpu", lambda context, job: job, resource_class=ResourceClass.CPU),
        JobHandlerSpec("only.image", lambda context, job: job, resource_class=ResourceClass.GPU_IMAGE),
    ))
    worker = DurableFeatureJobWorker(
        SimpleNamespace(database=object(), context=object()),
        registry,
        pool_name="cpu",
        resource_classes=RESOURCE_POOLS["cpu"],
    )
    monkeypatch.setattr(durable_feature_worker, "unit_of_work", lambda database: Work())

    assert worker._claim_one() is None
    assert captured["resource_classes"] == sorted(RESOURCE_POOLS["cpu"])
    assert captured["job_types"] == ["only.cpu"]


def test_shutdown_cancels_and_releases_a_job_after_the_drain_deadline(monkeypatch):
    released = []
    cancellation = threading.Event()
    execution_thread = threading.Thread(target=cancellation.wait, args=(5,), daemon=True)
    job = SimpleNamespace(
        id="job:shutdown",
        lease=SimpleNamespace(worker_id="worker:cpu", token="lease:shutdown"),
    )

    class Jobs:
        def release(self, context, **kwargs):
            released.append(kwargs)

    class Work:
        jobs = Jobs()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def commit(self):
            pass

    worker = DurableFeatureJobWorker(
        SimpleNamespace(database=object(), context="tenant"),
        JobHandlerRegistry(),
        pool_name="cpu",
        resource_classes=("cpu",),
        shutdown_grace_seconds=0,
    )
    execution_thread.start()
    worker._active[job.id] = durable_feature_worker._ActiveExecution(
        job, cancellation, execution_thread
    )
    monkeypatch.setattr(durable_feature_worker, "unit_of_work", lambda database: Work())

    worker.stop(grace_seconds=0)

    assert cancellation.is_set()
    assert released == [{
        "job_id": "job:shutdown",
        "worker_id": "worker:cpu",
        "lease_token": "lease:shutdown",
        "reason": "worker shutdown drain deadline elapsed",
    }]
