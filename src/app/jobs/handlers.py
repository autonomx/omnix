"""Typed job-handler registry owned by the jobs kernel."""
from __future__ import annotations

from dataclasses import dataclass
import random
from threading import Event
from typing import Any, Callable

from pydantic import BaseModel, ConfigDict

from .models import CreateJobRequest, JobRecord, ResourceClass


class AnyJobInput(BaseModel):
    model_config = ConfigDict(extra="allow")


@dataclass(frozen=True, slots=True)
class Backoff:
    base_seconds: float = 2.0
    factor: float = 2.0
    max_seconds: float = 300.0
    jitter: float = 0.2

    def delay(self, attempt: int, *, random_value: float | None = None) -> float:
        bounded_attempt = max(0, int(attempt))
        raw = min(self.max_seconds, self.base_seconds * (self.factor ** bounded_attempt))
        if self.jitter <= 0:
            return raw
        unit = random.random() if random_value is None else max(0.0, min(1.0, random_value))
        return max(0.0, raw * (1.0 + ((unit * 2.0) - 1.0) * self.jitter))


@dataclass(slots=True)
class JobExecutionContext:
    job_store: Any
    services: Any = None
    cancellation: Event | None = None

    def cancelled(self) -> bool:
        return bool(self.cancellation and self.cancellation.is_set())


JobHandler = Callable[[JobExecutionContext, JobRecord], JobRecord]
SubmissionPolicy = Callable[[CreateJobRequest], CreateJobRequest]


@dataclass(frozen=True, slots=True)
class JobHandlerSpec:
    type: str
    handler: JobHandler
    input_model: type[BaseModel] = AnyJobInput
    resource_class: ResourceClass = ResourceClass.CPU
    timeout_seconds: float = 300.0
    max_attempts: int = 3
    retry_backoff: Backoff = Backoff()
    submission_policy: SubmissionPolicy | None = None

    def __post_init__(self) -> None:
        if not self.type.strip() or self.type != self.type.strip():
            raise ValueError("job handler type must be a non-empty normalized string")
        if self.timeout_seconds <= 0:
            raise ValueError("job handler timeout must be positive")
        if self.max_attempts < 1:
            raise ValueError("job handler max_attempts must be positive")


class JobHandlerRegistry:
    def __init__(self, specs: tuple[JobHandlerSpec, ...] = ()) -> None:
        self._handlers: dict[str, JobHandlerSpec] = {}
        for spec in specs:
            self.register(spec)

    def register(self, spec: JobHandlerSpec) -> None:
        if spec.type in self._handlers:
            raise ValueError(f"duplicate job handler type: {spec.type}")
        self._handlers[spec.type] = spec

    def get(self, job_type: str) -> JobHandlerSpec | None:
        return self._handlers.get(job_type)

    def require(self, job_type: str) -> JobHandlerSpec:
        spec = self.get(job_type)
        if spec is None:
            raise KeyError(job_type)
        return spec

    def types(self) -> tuple[str, ...]:
        return tuple(sorted(self._handlers))

    def validate_submission(self, request: CreateJobRequest) -> CreateJobRequest:
        spec = self.require(request.type)
        payload = spec.input_model.model_validate(request.input_payload or {})
        updated = request.model_copy(
            update={
                "input_payload": payload.model_dump(mode="python"),
                "resource_class": spec.resource_class,
            }
        )
        return spec.submission_policy(updated) if spec.submission_policy else updated

    def execute(self, context: JobExecutionContext, job: JobRecord) -> JobRecord:
        spec = self.require(job.type)
        payload = spec.input_model.model_validate(job.input_payload or {})
        if payload.model_dump(mode="python") != (job.input_payload or {}):
            job = job.model_copy(update={"input_payload": payload.model_dump(mode="python")})
        return spec.handler(context, job)


def registry_from_features(features: tuple[Any, ...]) -> JobHandlerRegistry:
    registry = JobHandlerRegistry()
    for feature in features:
        for spec in getattr(feature, "job_handlers", ()):
            registry.register(spec)
    return registry
