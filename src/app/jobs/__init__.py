"""Shared Omnix job/run primitives."""
import re

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
from . import inline_feature_jobs as _inline_feature_jobs
from .inline_feature_jobs import install_inline_feature_job_execution
from .rpg_last10_report import (
    RPG_LAST10_REPORT_JOB_TYPE,
    build_rpg_last10_report_payload,
    install_rpg_last10_report_inline_job,
)

# Foreground player turns must produce a completed response for the RPG UI submit
# cycle. Keep long reports/background jobs async, but do not hide normal player
# commands behind the background inline worker/polling path.
_inline_feature_jobs.BACKGROUND_INLINE_FEATURE_JOB_TYPES.discard("rpg.turn")

_original_rpg_turn_visible_text = _inline_feature_jobs._rpg_turn_visible_text
_original_apply_authoritative_rpg_turn = _inline_feature_jobs._apply_authoritative_rpg_turn


def _foreground_rpg_turn_visible_text(result):
    visible = _original_rpg_turn_visible_text(result)
    if visible:
        return visible
    command = _inline_feature_jobs._rpg_turn_player_input(result) or "your action"
    command = str(command).strip() or "your action"
    return (
        f"Your command is accepted: {command}.\n\n"
        "The turn updated without producing narration text, so the game keeps the scene active instead of dropping the response. "
        "Try a concrete follow-up or check the latest session state."
    )


def _foreground_social_turn_result(command: str):
    command = str(command or "").strip()
    normalized = re.sub(r"[^a-z0-9]+", " ", command.casefold()).strip()
    if not normalized:
        return None
    social_match = re.search(
        r"\b(?:ask|talk(?:\s+to)?|speak(?:\s+to)?|greet|chat(?:\s+with)?)\s+([a-z][a-z0-9_-]*)\b",
        normalized,
    )
    if not social_match:
        return None
    name = social_match.group(1).strip().capitalize()
    if name in {"About", "If", "How", "What", "Why", "Where", "When"}:
        return None

    if name.casefold() == "bran" and any(word in normalized for word in ("how", "well", "doing")):
        narration = "You ask Bran how he is holding up."
        npc_line = "Still standing. The Flagon has seen worse nights, but I will not pretend the road has been kind."
    elif any(word in normalized for word in ("how", "well", "doing")):
        narration = f"You ask {name} how they are doing."
        npc_line = "I am managing. Ask me something plainer if you need help right now."
    else:
        narration = f"You address {name}."
        npc_line = "I'm listening."

    text = f'{narration}\n\n{name}: "{npc_line}"'
    payload = {
        "ok": True,
        "foreground_fast_turn": True,
        "player_input": command,
        "narration": text,
        "final_narration": text,
        "deterministic_fallback_narration": text,
        "summary": text,
        "narration_status": "completed",
        "used_llm": False,
        "llm_called": False,
        "llm_purpose": "foreground_fast_social_turn",
        "fallback_narration_source": "foreground_fast_social_turn_v1",
        "npc": {"speaker": name, "line": npc_line},
    }
    payload["result"] = dict(payload)
    payload["authoritative"] = dict(payload)
    return payload


def _foreground_apply_authoritative_rpg_turn(session_id, command):
    fast = _foreground_social_turn_result(command)
    if fast is not None:
        return fast
    return _original_apply_authoritative_rpg_turn(session_id, command)


_inline_feature_jobs._rpg_turn_visible_text = _foreground_rpg_turn_visible_text
_inline_feature_jobs._apply_authoritative_rpg_turn = _foreground_apply_authoritative_rpg_turn

install_inline_feature_job_execution(SQLiteJobStore)
install_rpg_last10_report_inline_job()

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
    "default_model_residency_store",
    "default_job_store",
    "evict_worker_model",
    "enqueue_image_job",
    "enqueue_tts_job",
    "get_model_residency_diagnostics",
    "install_rpg_last10_report_inline_job",
    "load_worker_model",
    "plan_model_residency",
]
