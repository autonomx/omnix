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
from .image_inline import install_image_job_execution
from .provider_control import create_worker_model_control_hooks, evict_worker_model, load_worker_model
from .research_inline import install_research_job_execution
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
from . import inline_feature_jobs as _inline_feature_jobs
from .inline_feature_jobs import install_inline_feature_job_execution
from .rpg_debug_job_hook import install_rpg_debug_job_hook
from .rpg_last10_report import (
    RPG_LAST10_REPORT_JOB_TYPE,
    build_rpg_last10_report_payload,
    install_rpg_last10_report_inline_job,
)
from .rpg_turn_job_guard import install_rpg_turn_job_guard
from .voice_inline import install_voice_studio_job_execution

install_inline_feature_job_execution(SQLiteJobStore)
install_rpg_last10_report_inline_job()
_inline_feature_jobs.BACKGROUND_INLINE_FEATURE_JOB_TYPES.discard(RPG_LAST10_REPORT_JOB_TYPE)
install_rpg_turn_job_guard(SQLiteJobStore)
install_voice_studio_job_execution(SQLiteJobStore)
install_image_job_execution(SQLiteJobStore)
install_research_job_execution(SQLiteJobStore)
install_rpg_debug_job_hook(SQLiteJobStore)

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
    "RPG_LAST10_REPORT_JOB_TYPE",
    "ResourceClass",
    "ResidencyDecision",
    "ResidencyDecisionAction",
    "SQLiteJobStore",
    "SQLiteModelResidencyStore",
    "build_rpg_last10_report_payload",
    "create_model_evict_job_request",
    "create_model_load_job_request",
    "create_model_residency_handlers",
    "create_worker_model_control_hooks",
    "default_job_store",
    "evict_worker_model",
    "get_model_residency_diagnostics",
    "install_rpg_last10_report_inline_job",
    "load_worker_model",
    "plan_model_residency",
]
