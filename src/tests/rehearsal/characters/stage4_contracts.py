"""Typed, content-free contracts for the Character Mode Stage 4 pilot."""
from __future__ import annotations

import hashlib
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Stage4Status = Literal["pass", "fail", "review"]
Stage4Decision = Literal["pass", "blocked", "needs_review"]


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def duration_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 3)


def safe_error(exc: Exception) -> str:
    text = " ".join(str(exc).strip().split())
    return (text or exc.__class__.__name__)[:500]


def decision(checks: list["Stage4Check"]) -> Stage4Decision:
    if any(check.status == "fail" for check in checks):
        return "blocked"
    if any(check.status == "review" for check in checks):
        return "needs_review"
    return "pass"


def marker(run_id: str, label: str) -> str:
    digest = hashlib.sha256(f"{run_id}\n{label}".encode()).hexdigest()[:16]
    return f"STAGE4-{label.upper()}-{digest.upper()}"


def marker_memory(run_id: str, label: str) -> str:
    return f"Synthetic Stage 4 memory marker: {marker(run_id, label)}."


class Stage4Check(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    status: Stage4Status
    summary: str
    duration_ms: float = Field(default=0, ge=0)
    observed: dict[str, Any] = Field(default_factory=dict)


class Stage4Metrics(BaseModel):
    model_config = ConfigDict(extra="forbid")
    first_token_ms: float | None = Field(default=None, ge=0)
    restart_first_token_ms: float | None = Field(default=None, ge=0)
    shared_selected_count: int = Field(default=0, ge=0)
    shared_excluded_count: int = Field(default=0, ge=0)
    segment_switch_count: int = Field(default=0, ge=0)


class Stage4PrepareConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    base_url: str = "http://127.0.0.1:8000"
    provider_id: str | None = "lmstudio"
    model_id: str | None = None
    character_id: str = "stage4-maya"
    run_id: str = "stage4-shared-readonly-v1"
    timeout_seconds: float = Field(default=120, gt=0, le=900)


class Stage4Checkpoint(BaseModel):
    model_config = ConfigDict(extra="forbid")
    format_version: Literal["character-stage4-v1"] = "character-stage4-v1"
    created_at: str
    base_url: str
    provider_id: str | None = None
    model_id: str | None = None
    run_id: str
    character_id: str
    shared_session_id: str
    control_session_id: str
    system_setup_session_id: str
    shared_segment_id: str
    shared_identity_hash: str = Field(min_length=64, max_length=64)
    fixture_memory_ids: dict[str, str]
    prepare_checks: list[Stage4Check]
    prepare_metrics: Stage4Metrics


class Stage4Report(BaseModel):
    model_config = ConfigDict(extra="forbid")
    format_version: Literal["character-stage4-report-v1"] = "character-stage4-report-v1"
    generated_at: str
    mode: Literal["prepare", "verify-restart"]
    decision: Stage4Decision
    base_url: str
    run_id: str
    character_id: str
    shared_session_id: str | None = None
    checks: list[Stage4Check]
    metrics: Stage4Metrics
    checkpoint_path: str | None = None
    notes: list[str] = Field(default_factory=list)


def write_report(report: Stage4Report, path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(report.model_dump_json(indent=2), encoding="utf-8")
