"""Typed, content-free contracts for the Character Mode Stage 3 pilot."""
from __future__ import annotations

import hashlib
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Stage3Status = Literal["pass", "fail", "review"]
Stage3Decision = Literal["pass", "blocked", "needs_review"]


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def duration_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 3)


def safe_error(exc: Exception) -> str:
    text = " ".join(str(exc).strip().split())
    return (text or exc.__class__.__name__)[:500]


def decision(checks: list["Stage3Check"]) -> Stage3Decision:
    if any(check.status == "fail" for check in checks):
        return "blocked"
    if any(check.status == "review" for check in checks):
        return "needs_review"
    return "pass"


def marker(run_id: str, label: str) -> str:
    digest = hashlib.sha256(f"{run_id}\n{label}".encode("utf-8")).hexdigest()[:16]
    return f"STAGE3-{label.upper()}-{digest.upper()}"


def marker_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def marker_memory(run_id: str, label: str) -> str:
    return f"Synthetic Stage 3 memory marker: {marker(run_id, label)}."


class Stage3Check(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    status: Stage3Status
    summary: str
    duration_ms: float = Field(default=0, ge=0)
    observed: dict[str, Any] = Field(default_factory=dict)


class Stage3Metrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    first_token_ms: float | None = Field(default=None, ge=0)
    restart_first_token_ms: float | None = Field(default=None, ge=0)
    explicit_record_count: int = Field(default=0, ge=0)
    pending_candidate_count: int = Field(default=0, ge=0)
    approved_record_count: int = Field(default=0, ge=0)
    snapshot_record_count: int = Field(default=0, ge=0)


class Stage3PrepareConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_url: str = "http://127.0.0.1:8000"
    provider_id: str | None = "lmstudio"
    model_id: str | None = None
    maya_character_id: str = "stage3-maya"
    alex_character_id: str = "stage3-alex"
    run_id: str = "stage3-write-v1"
    timeout_seconds: float = Field(default=120, gt=0, le=900)
    settle_seconds: float = Field(default=8, ge=0, le=120)
    token_budget: int = Field(default=4_000, ge=256, le=64_000)


class Stage3Checkpoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    format_version: Literal["character-stage3-v1"] = "character-stage3-v1"
    created_at: str
    base_url: str
    provider_id: str | None = None
    model_id: str | None = None
    run_id: str
    maya_character_id: str
    alex_character_id: str
    maya_rw_session_id: str
    maya_write_only_session_id: str
    alex_control_session_id: str
    maya_explicit_memory_id: str
    maya_write_only_memory_id: str
    approved_candidate_id: str | None = None
    approved_candidate_memory_id: str | None = None
    rejected_candidate_id: str | None = None
    maya_segment_id: str
    maya_identity_hash: str = Field(min_length=64, max_length=64)
    maya_snapshot_id: str | None = None
    maya_snapshot_revision: int | None = Field(default=None, ge=1)
    marker_hashes: dict[str, str]
    prepare_checks: list[Stage3Check]
    prepare_metrics: Stage3Metrics


class Stage3Report(BaseModel):
    model_config = ConfigDict(extra="forbid")

    format_version: Literal["character-stage3-report-v1"] = "character-stage3-report-v1"
    generated_at: str
    mode: Literal["prepare", "verify-restart"]
    decision: Stage3Decision
    base_url: str
    run_id: str
    maya_character_id: str
    maya_rw_session_id: str | None = None
    checks: list[Stage3Check]
    metrics: Stage3Metrics
    checkpoint_path: str | None = None
    notes: list[str] = Field(default_factory=list)


def write_report(report: Stage3Report, path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(report.model_dump_json(indent=2), encoding="utf-8")


__all__ = [
    "Stage3Check",
    "Stage3Checkpoint",
    "Stage3Metrics",
    "Stage3PrepareConfig",
    "Stage3Report",
    "decision",
    "duration_ms",
    "marker",
    "marker_hash",
    "marker_memory",
    "safe_error",
    "utcnow",
    "write_report",
]
