from __future__ import annotations

from fastapi import APIRouter, FastAPI
from pydantic import BaseModel

import app.gateway.feature_registry as feature_registry
from app.config.load import load_feature_config
from app.runtime.capabilities import RuntimeCapabilities
from app.runtime.config import RuntimeConfig
from app.runtime.features import FeatureModule
from app.runtime.scheduler import ScheduledTaskSpec


class SampleFeatureConfig(BaseModel):
    enabled: bool = False
    retries: int = 2


def test_feature_config_reads_only_prefixed_values_and_validates_types():
    config = load_feature_config(
        "sample-feature",
        SampleFeatureConfig,
        env={
            "OMNIX_SAMPLE_FEATURE_ENABLED": "true",
            "OMNIX_SAMPLE_FEATURE_RETRIES": "5",
            "OMNIX_OTHER_RETRIES": "not-an-integer",
        },
    )

    assert isinstance(config, SampleFeatureConfig)
    assert config.enabled is True
    assert config.retries == 5


def test_feature_config_errors_name_variables_without_echoing_values():
    try:
        load_feature_config(
            "sample-feature",
            SampleFeatureConfig,
            env={"OMNIX_SAMPLE_FEATURE_RETRIES": "private-value"},
        )
    except ValueError as error:
        assert "retries" in str(error)
        assert "private-value" not in str(error)
    else:
        raise AssertionError("invalid feature config must fail closed")

    try:
        load_feature_config(
            "sample-feature",
            SampleFeatureConfig,
            env={"OMNIX_SAMPLE_FEATURE_UNRECOGNIZED": "private-value"},
        )
    except ValueError as error:
        assert "OMNIX_SAMPLE_FEATURE_UNRECOGNIZED" in str(error)
        assert "private-value" not in str(error)
    else:
        raise AssertionError("unknown feature config must fail closed")


def test_feature_composition_passes_validated_config_to_router_factory(monkeypatch):
    captured = []

    def router_factory(context):
        captured.append(context.config)
        router = APIRouter()

        @router.get("/sample-feature/probe")
        def probe():
            return {"ok": True}

        return router

    feature = FeatureModule(
        id="sample-feature",
        title="Sample feature",
        config_model=SampleFeatureConfig,
        routers=(router_factory,),
    )
    env = {"OMNIX_SAMPLE_FEATURE_ENABLED": "true", "OMNIX_SAMPLE_FEATURE_RETRIES": "4"}
    monkeypatch.setattr(feature_registry, "enabled_feature_ids", lambda _config: (feature.id,))
    monkeypatch.setattr(feature_registry, "load_feature", lambda _feature_id: feature)
    monkeypatch.setattr(feature_registry, "environment", lambda: env)
    monkeypatch.setattr(feature_registry, "reset_repository_specs", lambda: None)
    monkeypatch.setattr(feature_registry, "install_repository_specs", lambda _specs: None)
    monkeypatch.setattr(feature_registry, "shared_repository_specs", lambda: ())
    monkeypatch.setattr(feature_registry, "install_runtime_hooks", lambda _hooks: None)

    gateway = FastAPI()
    gateway.state.runtime_config = RuntimeConfig()
    gateway.state.runtime_capabilities = RuntimeCapabilities.from_config(RuntimeConfig())
    gateway.state.runtime_services = None
    gateway.state.background_registry = None
    included = []
    include_router = gateway.include_router

    def capture_include_router(router, **options):
        included.append((router, options))
        return include_router(router, **options)

    monkeypatch.setattr(gateway, "include_router", capture_include_router)

    feature_registry._register_feature_modules(gateway)

    assert captured == [SampleFeatureConfig(enabled=True, retries=4)]
    assert "/sample-feature/probe" in gateway.openapi()["paths"]
    assert len(included) == 1
    dependencies = included[0][1]["dependencies"]
    assert dependencies[0].dependency.__name__ == "feature_guard_sample_feature"


def test_feature_composition_registers_scheduled_tasks(monkeypatch):
    registered_tasks = []

    class SchedulerRegistry:
        def register_task(self, task):
            registered_tasks.append(task)

    async def run(_context):
        return None

    task = ScheduledTaskSpec(
        task_id="sample-feature.scheduled",
        run=run,
        interval_seconds=1,
    )
    feature = FeatureModule(
        id="sample-feature",
        title="Sample feature",
        scheduled_tasks=(lambda _context: task,),
    )
    monkeypatch.setattr(feature_registry, "enabled_feature_ids", lambda _config: (feature.id,))
    monkeypatch.setattr(feature_registry, "load_feature", lambda _feature_id: feature)
    monkeypatch.setattr(feature_registry, "environment", lambda: {})
    monkeypatch.setattr(feature_registry, "reset_repository_specs", lambda: None)
    monkeypatch.setattr(feature_registry, "install_repository_specs", lambda _specs: None)
    monkeypatch.setattr(feature_registry, "shared_repository_specs", lambda: ())
    monkeypatch.setattr(feature_registry, "install_runtime_hooks", lambda _hooks: None)

    gateway = FastAPI()
    gateway.state.runtime_config = RuntimeConfig()
    gateway.state.runtime_capabilities = RuntimeCapabilities.from_config(RuntimeConfig())
    gateway.state.runtime_services = None
    gateway.state.background_registry = None
    gateway.state.scheduler_registry = SchedulerRegistry()

    feature_registry._register_feature_modules(gateway)

    assert registered_tasks == [task]
