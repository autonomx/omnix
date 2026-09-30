"""Feature-module contracts used by the composition root."""
from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any, Callable, Protocol

from fastapi import APIRouter
from pydantic import BaseModel

from .background import BackgroundWorker
from .capabilities import RuntimeCapabilities, RuntimeCapability
from .config import RuntimeConfig
from .hooks import RuntimeHookSpec

from app.runtime.contracts import KernelServices


class JobHandlerSpec(Protocol):
    """Structural job-handler contract without importing the jobs kernel."""

    type: str
    handler: Callable[..., object]
    input_model: type[BaseModel]
    resource_class: object
    timeout_seconds: float
    max_attempts: int
    retry_backoff: object
    submission_policy: Callable[..., object] | None


class JobObserverFactory(Protocol):
    """Feature factory that returns an enabled kernel job observer, if any."""

    def __call__(self) -> object | None: ...


class ScheduledTaskSpec(Protocol):
    """Structural contract for a feature-owned scheduled task."""

    task_id: str
    run: Callable[..., object]


class RepositorySpec(Protocol):
    """Structural repository factory contract without importing persistence."""

    type: object
    factory: Callable[..., object]
    alias: str | None


class OutboxConsumerSpec(Protocol):
    """Structural contract for a feature-owned outbox consumer."""

    event_type: str
    consume: Callable[..., object]


class SettingSpec(Protocol):
    """Structural settings contract without importing the settings kernel."""

    key: str
    value_type: type
    default: object
    feature: str
    writable: bool


class PermissionSpec(Protocol):
    """Structural permission contract; authorization policy is feature owned."""

    action: str
    resource: str


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
    services: "KernelServices"
    logger: logging.Logger
    runtime_state: Any = None


RouterFactory = Callable[[FeatureContext], APIRouter]
BackgroundWorkerFactory = Callable[[FeatureContext], BackgroundWorker | None]


@dataclass(frozen=True, slots=True)
class FeatureModule:
    id: str
    title: str
    requires: frozenset[RuntimeCapability] = frozenset({RuntimeCapability.SERVE_API})
    depends_on: tuple[str, ...] = ()
    config_model: type[BaseModel] | None = None
    routers: tuple[RouterFactory, ...] = ()
    internal_routers: tuple[RouterFactory, ...] = ()
    job_handlers: tuple[JobHandlerSpec, ...] = ()
    job_observers: tuple[JobObserverFactory, ...] = ()
    background_workers: tuple[BackgroundWorkerFactory, ...] = ()
    scheduled_tasks: tuple[ScheduledTaskSpec, ...] = ()
    repositories: tuple[RepositorySpec, ...] = ()
    hooks: tuple[RuntimeHookSpec, ...] = ()
    outbox_consumers: tuple[OutboxConsumerSpec, ...] = ()
    settings: tuple[SettingSpec, ...] = ()
    permissions: tuple[PermissionSpec, ...] = ()
    public_paths: frozenset[str] = frozenset()
    lifecycle: FeatureLifecycle | None = None

    def __post_init__(self) -> None:
        feature_id = self.id.strip()
        if not feature_id or feature_id != self.id or not feature_id.replace("_", "").replace("-", "").isalnum():
            raise ValueError(f"Invalid feature id: {self.id!r}")
        if self.id in self.depends_on:
            raise ValueError(f"Feature {self.id} cannot depend on itself")
