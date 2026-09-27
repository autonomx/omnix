"""Feature-module contracts used by the composition root."""
from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any, Callable, TYPE_CHECKING

from fastapi import APIRouter
from pydantic import BaseModel

from .background import BackgroundWorker
from .capabilities import RuntimeCapabilities, RuntimeCapability
from .config import RuntimeConfig

if TYPE_CHECKING:
    from app.runtime.contracts import AssetService, ChatService, JobService, ModelResidencyService


@dataclass(frozen=True, slots=True)
class FeatureLifecycle:
    name: str
    startup: tuple[Callable[[], Any], ...] = ()
    shutdown: tuple[Callable[[], Any], ...] = ()
    requires: frozenset[RuntimeCapability] = frozenset({RuntimeCapability.SERVE_API})


@dataclass(frozen=True, slots=True)
class FeatureContext:
    feature_id: str
    config: BaseModel | None
    runtime: RuntimeConfig
    capabilities: RuntimeCapabilities
    services: Any
    logger: logging.Logger


RouterFactory = Callable[[FeatureContext], APIRouter]
BackgroundWorkerFactory = Callable[[FeatureContext], BackgroundWorker]
GatewayInstaller = Callable[[Any, FeatureContext], None]


@dataclass(frozen=True, slots=True)
class FeatureModule:
    id: str
    title: str
    requires: frozenset[RuntimeCapability] = frozenset({RuntimeCapability.SERVE_API})
    depends_on: tuple[str, ...] = ()
    config_model: type[BaseModel] | None = None
    routers: tuple[RouterFactory, ...] = ()
    installers: tuple[GatewayInstaller, ...] = ()
    internal_routers: tuple[RouterFactory, ...] = ()
    job_handlers: tuple[Any, ...] = ()
    background_workers: tuple[BackgroundWorkerFactory, ...] = ()
    scheduled_tasks: tuple[Any, ...] = ()
    repositories: tuple[Any, ...] = ()
    outbox_consumers: tuple[Any, ...] = ()
    settings: tuple[Any, ...] = ()
    permissions: tuple[Any, ...] = ()
    public_paths: frozenset[str] = frozenset()
    lifecycle: FeatureLifecycle | None = None

    def __post_init__(self) -> None:
        feature_id = self.id.strip()
        if not feature_id or feature_id != self.id or not feature_id.replace("_", "").replace("-", "").isalnum():
            raise ValueError(f"Invalid feature id: {self.id!r}")
        if self.id in self.depends_on:
            raise ValueError(f"Feature {self.id} cannot depend on itself")
