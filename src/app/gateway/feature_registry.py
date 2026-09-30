"""Registry-driven FeatureModule composition."""

import logging

from fastapi import Depends

from app.config.env import environment
from app.config.load import load_feature_config
from app.jobs.handlers import JobHandlerRegistry
from app.persistence.repository_registry import install_repository_specs, reset_repository_specs
from app.persistence.shared_repository_specs import shared_repository_specs
from app.runtime.background import register_background_worker
from app.runtime.feature_catalog import enabled_feature_ids, load_feature
from app.runtime.features import FeatureContext, FeatureLifecycle
from app.runtime.hooks import install_runtime_hooks


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


def _register_feature_modules(gateway) -> None:
    config = gateway.state.runtime_config
    capabilities = gateway.state.runtime_capabilities
    services = getattr(gateway.state, "runtime_services", None)
    registry = getattr(gateway.state, "background_registry", None)
    registered: list[str] = []
    loaded_features = []
    job_handlers = JobHandlerRegistry()
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
        for router_factory in feature.routers:
            gateway.include_router(
                router_factory(context),
                dependencies=[Depends(feature_guard(feature.id))],
            )
        for router_factory in feature.internal_routers:
            gateway.include_router(
                router_factory(context),
                dependencies=[Depends(feature_guard(feature.id))],
                include_in_schema=False,
            )
        for worker_factory in feature.background_workers:
            worker = worker_factory(context)
            if worker is not None:
                register_background_worker(registry, worker)
        if feature.lifecycle is not None:
            register_feature_lifecycle(gateway, feature.lifecycle)
        registered.append(feature.id)

    gateway.state.feature_modules = tuple(registered)
    gateway.state.loaded_feature_modules = tuple(loaded_features)
    gateway.state.job_handler_registry = job_handlers
    jobs = getattr(services, "jobs", None)
    configure_handlers = getattr(jobs, "configure_handler_registry", None)
    if callable(configure_handlers):
        configure_handlers(job_handlers)


def _install_kernel_extensions(gateway) -> None:
    from .blocking_route_offload import register_blocking_route_offload
    from .event_loop_lag_monitor import register_event_loop_lag_monitor

    register_event_loop_lag_monitor(gateway)
    register_blocking_route_offload(gateway)


def compose_features(gateway):
    if getattr(gateway.state, "features_registered", False):
        return
    _install_kernel_extensions(gateway)
    _register_feature_modules(gateway)
    gateway.state.features_registered = True
