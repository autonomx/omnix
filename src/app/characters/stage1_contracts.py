"""Typed contracts and content-free report helpers for the Stage 1 rehearsal."""
from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

CheckStatus = Literal["pass", "fail", "review", "skipped"]
Decision = Literal["pass", "blocked", "needs_review"]


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def duration_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 3)


def safe_error(exc: Exception) -> str:
    text = " ".join(str(exc).strip().split())
    return (text or exc.__class__.__name__)[:500]


def report_decision(checks: list["Stage1Check"]) -> Decision:
    if any(check.status == "fail" for check in checks):
        return "blocked"
    if any(check.status in {"review", "skipped"} for check in checks):
        return "needs_review"
    return "pass"


class Stage1Check(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    status: CheckStatus
    summary: str
    duration_ms: float = Field(default=0, ge=0)
    observed: dict[str, Any] = Field(default_factory=dict)


class Stage1Metrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runtime_preload_ms: float | None = Field(default=None, ge=0)
    first_token_ms: float | None = Field(default=None, ge=0)
    first_audio_chunk_ms: float | None = Field(default=None, ge=0)
    response_character_count: int = Field(default=0, ge=0)
    first_audio_chunk_bytes: int = Field(default=0, ge=0)


class Stage1Checkpoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    format_version: Literal["character-stage1-v1"] = "character-stage1-v1"
    created_at: str
    base_url: str
    character_id: str
    character_display_name: str
    character_profile_version: int = Field(ge=1)
    character_session_id: str
    character_segment_id: str
    effective_identity_hash: str = Field(min_length=64, max_length=64)
    voice_asset_id: str | None = None
    prepare_checks: list[Stage1Check]
    prepare_metrics: Stage1Metrics


class Stage1Report(BaseModel):
    model_config = ConfigDict(extra="forbid")

    format_version: Literal["character-stage1-report-v1"] = "character-stage1-report-v1"
    generated_at: str
    mode: Literal["prepare", "verify-restart"]
    decision: Decision
    base_url: str
    character_id: str
    character_session_id: str | None = None
    checks: list[Stage1Check]
    metrics: Stage1Metrics
    checkpoint_path: str | None = None
    notes: list[str] = Field(default_factory=list)


class Stage1PrepareConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_url: str = "http://127.0.0.1:8000"
    character_id: str = "stage1-maya"
    display_name: str = "Maya Stage 1"
    personality_prompt: str = (
        "Be warm, relaxed, concise, and lightly humorous. Remain clearly an AI character."
    )
    greeting: str = "Hey, good to hear from you."
    voice_asset_id: str | None = None
    provider_id: str | None = None
    model_id: str | None = None
    probe_text: str = "Reply with one short sentence confirming that this Stage 1 call is ready."
    timeout_seconds: float = Field(default=120, gt=0, le=900)
    settle_seconds: float = Field(default=1.5, ge=0, le=30)
    skip_generation: bool = False
    skip_tts: bool = False
    update_existing_character: bool = False
    apply_voice_governance: bool = False
    confirm_voice_consent: bool = False
    voice_subject_owner: str = ""
    voice_source_type: str = ""
    voice_source_reference: str = ""
    voice_creator_id: str = ""


def write_report(report: Stage1Report, path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(report.model_dump_json(indent=2), encoding="utf-8")


__all__ = [
    "CheckStatus",
    "Decision",
    "Stage1Check",
    "Stage1Checkpoint",
    "Stage1Metrics",
    "Stage1PrepareConfig",
    "Stage1Report",
    "duration_ms",
    "report_decision",
    "safe_error",
    "utcnow",
    "write_report",
]
