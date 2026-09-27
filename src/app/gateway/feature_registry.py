"""Registry-driven FeatureModule composition."""

import logging

from app.jobs.handlers import JobHandlerRegistry
from app.runtime.background import register_background_worker
from app.runtime.feature_catalog import enabled_feature_ids, load_feature
from app.runtime.features import FeatureContext, FeatureLifecycle


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


def _register_feature_modules(gateway) -> None:
    config = gateway.state.runtime_config
    capabilities = gateway.state.runtime_capabilities
    services = getattr(gateway.state, "runtime_services", None)
    registry = getattr(gateway.state, "background_registry", None)
    registered: list[str] = []
    loaded_features = []
    job_handlers = JobHandlerRegistry()

    for feature_id in enabled_feature_ids(config):
        feature = load_feature(feature_id)
        capabilities.require(*feature.requires)
        loaded_features.append(feature)
        for handler in feature.job_handlers:
            job_handlers.register(handler)
        context = FeatureContext(
            feature_id=feature.id,
            config=None,
            runtime=config,
            capabilities=capabilities,
            services=services,
            logger=logging.getLogger(f"app.feature.{feature.id}"),
        )
        for installer in feature.installers:
            installer(gateway, context)
        for router_factory in feature.routers:
            gateway.include_router(router_factory(context))
        for router_factory in feature.internal_routers:
            gateway.include_router(router_factory(context))
        for worker_factory in feature.background_workers:
            register_background_worker(registry, worker_factory(context))
        if feature.lifecycle is not None:
            register_feature_lifecycle(gateway, feature.lifecycle)
        registered.append(feature.id)

    gateway.state.feature_modules = tuple(registered)
    gateway.state.loaded_feature_modules = tuple(loaded_features)
    gateway.state.job_handler_registry = job_handlers


def _install_kernel_extensions(gateway) -> None:
    from .blocking_route_offload import register_blocking_route_offload
    from .event_loop_lag_monitor import register_event_loop_lag_monitor

    register_event_loop_lag_monitor(gateway)
    register_blocking_route_offload(gateway)


def register_gateway_features(gateway):
    if getattr(gateway.state, "features_registered", False):
        return
    _install_kernel_extensions(gateway)
    _register_feature_modules(gateway)
    gateway.state.features_registered = True
