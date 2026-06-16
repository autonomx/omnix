"""Shared Omnix job/run primitives."""
from .models import (
    CancelJobRequest,
    ClaimJobRequest,
    ClaimJobResponse,
    CompleteJobRequest,
    CreateJobRequest,
    FailJobRequest,
    JobListResponse,
    JobRecord,
    JobStatus,
    ResourceClass,
)
from .adapters import enqueue_image_job, enqueue_tts_job
from .executor import LocalJobExecutor
from .provider_control import create_worker_model_control_hooks, evict_worker_model, load_worker_model
from .residency import (
    ModelResidencyDiagnostics,
    GpuResidencyPolicy,
    GpuResidencyRequest,
    ModelResidencyRecord,
    ModelResidencyStatus,
    ResidencyDecision,
    ResidencyDecisionAction,
    SQLiteModelResidencyStore,
    create_model_evict_job_request,
    create_model_load_job_request,
    create_model_residency_handlers,
    default_model_residency_store,
    get_model_residency_diagnostics,
    plan_model_residency,
)
from .store import SQLiteJobStore, default_job_store
from .inline_feature_jobs import install_inline_feature_job_execution

install_inline_feature_job_execution(SQLiteJobStore)

__all__ = [
    "CancelJobRequest",
    "ClaimJobRequest",
    "ClaimJobResponse",
    "CompleteJobRequest",
    "CreateJobRequest",
    "FailJobRequest",
    "GpuResidencyPolicy",
    "GpuResidencyRequest",
    "JobListResponse",
    "JobRecord",
    "JobStatus",
    "LocalJobExecutor",
    "ModelResidencyDiagnostics",
    "ModelResidencyRecord",
    "ModelResidencyStatus",
    "ResourceClass",
    "ResidencyDecision",
    "ResidencyDecisionAction",
    "SQLiteJobStore",
    "SQLiteModelResidencyStore",
    "create_model_evict_job_request",
    "create_model_load_job_request",
    "create_model_residency_handlers",
    "create_worker_model_control_hooks",
    "default_model_residency_store",
    "default_job_store",
    "evict_worker_model",
    "enqueue_image_job",
    "enqueue_tts_job",
    "get_model_residency_diagnostics",
    "load_worker_model",
    "plan_model_residency",
]
