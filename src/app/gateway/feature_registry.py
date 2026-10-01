"""Registry-driven FeatureModule composition."""

import logging
from typing import cast

from fastapi import Depends

from app.config.env import environment
from app.config.load import load_feature_config
from app.jobs.handlers import JobHandlerRegistry
from app.jobs.probe import PLATFORM_PROBE_JOB
from app.persistence.repository_registry import install_repository_specs, reset_repository_specs
from app.persistence.shared_repository_specs import shared_repository_specs
from app.runtime.background import register_background_worker
from app.runtime.feature_catalog import enabled_feature_ids, load_feature
from app.runtime.features import FeatureContext, FeatureLifecycle
from app.runtime.hooks import install_runtime_hooks
from app.runtime.scheduler import ScheduledTaskSpec as RuntimeScheduledTaskSpec
from app.security.permissions import feature_permission_guard, internal_permission_guard


def register_feature_lifecycle(gateway, feature: FeatureLifecycle):
    capabilities = getattr(gateway.state, "runtime_capabilities", None)
    if capabilities is not None:
        capabilities.require(*feature.requires)
    lifecycles = getattr(gateway.state, "feature_lifecycles", None)
    if lifecycles is None:
        for callback in feature.startup:
            gateway.router.add_event_handler("startup", callback)
        for callback in feature.shutdown:
            gateway.router.add_event_handler("shutdown", callback)
        return
    if any(item.name == feature.name for item in lifecycles):
        raise ValueError(f"Feature lifecycle already registered: {feature.name}")
    lifecycles.append(feature)


def feature_guard(feature_id: str):
    """Return the composition-level feature policy hook for mounted routes."""
    def guard() -> None:
        return None

    guard.__name__ = "feature_guard_" + feature_id.replace("-", "_")
    return guard


def _router_paths(router) -> list[str]:
    try:
        from fastapi.routing import iter_route_contexts
    except ImportError:  # FastAPI without lazy router inclusion
        return [str(route.path) for route in router.routes if getattr(route, "path", None)]
    return [
        str(context.path or context.original_route.path)
        for context in iter_route_contexts(router.routes)
    ]


def _register_feature_modules(gateway) -> None:
    config = gateway.state.runtime_config
    capabilities = gateway.state.runtime_capabilities
    services = getattr(gateway.state, "runtime_services", None)
    registry = getattr(gateway.state, "background_registry", None)
    scheduler_registry = getattr(gateway.state, "scheduler_registry", None)
    registered: list[str] = []
    loaded_features = []
    internal_paths: list[str] = []
    public_paths: list[str] = []
    job_handlers = JobHandlerRegistry()
    # Kernel-owned synthetic job used by canaries and deployment tests.
    job_handlers.register(PLATFORM_PROBE_JOB)
    reset_repository_specs()
    install_repository_specs(shared_repository_specs())

    for feature_id in enabled_feature_ids(config):
        feature = load_feature(feature_id)
        capabilities.require(*feature.requires)
        loaded_features.append(feature)
        settings_service = getattr(services, "settings", None)
        if feature.settings and settings_service is not None:
            settings_service.register_specs(tuple(feature.settings))
        install_runtime_hooks(feature.hooks)
        for handler in feature.job_handlers:
            job_handlers.register(handler)
        for observer_factory in feature.job_observers:
            observer = observer_factory()
            if observer is not None:
                job_handlers.register_observer(observer)
        if feature.repositories:
            install_repository_specs(tuple(feature.repositories))
        context = FeatureContext(
            feature_id=feature.id,
            config=load_feature_config(feature.id, feature.config_model, env=environment()),
            runtime=config,
            capabilities=capabilities,
            services=services,
            logger=logging.getLogger(f"app.feature.{feature.id}"),
            runtime_state=gateway.state,
        )
        # Every feature route is authorized (WP-4.3): its declared permission,
        # else the feature's read/write default.
        permission_guard = feature_permission_guard(feature.id)
        for router_factory in feature.routers:
            gateway.include_router(
                router_factory(context),
                dependencies=[Depends(feature_guard(feature.id)), Depends(permission_guard)],
            )
        for router_factory in feature.internal_routers:
            internal_router = router_factory(context)
            internal_paths.extend(_router_paths(internal_router))
            gateway.include_router(
                internal_router,
                dependencies=[Depends(feature_guard(feature.id)), Depends(internal_permission_guard)],
                include_in_schema=False,
            )
        public_paths.extend(sorted(feature.public_paths))
        for worker_factory in feature.background_workers:
            worker = worker_factory(context)
            if worker is not None:
                register_background_worker(registry, worker)
        for task_factory in feature.scheduled_tasks:
            task = task_factory(context)
            if task is not None:
                if scheduler_registry is None:
                    raise RuntimeError(
                        f"Feature {feature.id} declares scheduled tasks without a scheduler registry"
                    )
                scheduler_registry.register_task(cast(RuntimeScheduledTaskSpec, task))
        if feature.lifecycle is not None:
            register_feature_lifecycle(gateway, feature.lifecycle)
        registered.append(feature.id)

    # The authentication middleware accepts the service token only on these
    # paths and lets declared public paths through without a principal.
    gateway.state.internal_route_paths = tuple(dict.fromkeys(internal_paths))
    gateway.state.public_route_paths = tuple(dict.fromkeys(public_paths))
    gateway.state.feature_modules = tuple(registered)
    gateway.state.loaded_feature_modules = tuple(loaded_features)
    gateway.state.job_handler_registry = job_handlers
    from app.events.outbox_relay import outbox_consumer_registry

    gateway.state.outbox_consumers = outbox_consumer_registry(loaded_features)
    jobs = getattr(services, "jobs", None)
    configure_handlers = getattr(jobs, "configure_handler_registry", None)
    if callable(configure_handlers):
        configure_handlers(job_handlers)


def _install_kernel_extensions(gateway) -> None:
    from .event_loop_lag_monitor import register_event_loop_lag_monitor

    register_event_loop_lag_monitor(gateway)


def compose_features(gateway):
    if getattr(gateway.state, "features_registered", False):
        return
    _install_kernel_extensions(gateway)
    _register_feature_modules(gateway)
    gateway.state.features_registered = True
