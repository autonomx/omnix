"""Gateway adapter for the feature-neutral background runtime."""
from __future__ import annotations

from app.runtime.background import (
    BackgroundOwnershipUnavailable,
    BackgroundRegistry,
    BackgroundWorker,
    GatewayBackgroundRuntime,
    register_background_worker as register_runtime_background_worker,
)
from app.runtime.capabilities import RuntimeCapability


class GatewayBackgroundRegistryAdapter(BackgroundRegistry):
    """Adapt gateway state/lifecycle fallback to the neutral registry contract."""

    def __init__(self, gateway):
        self.gateway = gateway

    def register_worker(self, worker: BackgroundWorker) -> None:
        runtime = getattr(self.gateway.state, "background_runtime", None)
        required = RuntimeCapability.OWN_BACKGROUND_RUNTIME
        if required not in worker.requires:
            raise ValueError("Background workers must declare background ownership")

        if runtime is not None:
            register_runtime_background_worker(runtime, worker)
            return

        capabilities = getattr(self.gateway.state, "runtime_capabilities", None)
        if capabilities is not None:
            def denied(*args, **kwargs):
                raise BackgroundOwnershipUnavailable(
                    "No live background owner is composed for this gateway"
                )

            if hasattr(worker.monitor, "start"):
                worker.monitor.start = denied
            return

        from .feature_registry import FeatureLifecycle, register_feature_lifecycle

        register_feature_lifecycle(
            self.gateway,
            FeatureLifecycle(
                worker.name,
                worker.startup,
                worker.shutdown,
                worker.requires,
            ),
        )


def register_background_worker(gateway, worker: BackgroundWorker) -> None:
    """Compatibility adapter for gateway-owned registration call sites."""
    registry = getattr(gateway.state, "background_registry", None)
    if registry is None:
        registry = GatewayBackgroundRegistryAdapter(gateway)
        gateway.state.background_registry = registry
    register_runtime_background_worker(registry, worker)


__all__ = [
    "BackgroundOwnershipUnavailable",
    "BackgroundWorker",
    "GatewayBackgroundRegistryAdapter",
    "GatewayBackgroundRuntime",
    "register_background_worker",
]
