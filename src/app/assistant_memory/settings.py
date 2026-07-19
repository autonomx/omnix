"""Persisted server-enforced Chat memory settings and content-free diagnostics."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.runtime_paths import resources_data_root

CompanionRolloutStage = Literal[
    "authority_only",
    "shadow",
    "read_only_pilot",
    "explicit_typed",
    "review_required",
    "automatic_assertions",
    "gentle_initiative",
    "active_initiative",
    "paralinguistic_pilot",
]
_COMPANION_STAGES: tuple[CompanionRolloutStage, ...] = (
    "authority_only",
    "shadow",
    "read_only_pilot",
    "explicit_typed",
    "review_required",
    "automatic_assertions",
    "gentle_initiative",
    "active_initiative",
    "paralinguistic_pilot",
)


class AssistantMemoryRuntimeSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    curated_memory_enabled: bool = False
    suggestions_enabled: bool = False
    history_recall_enabled: bool = False
    compaction_enabled: bool = False
    hermes_sync_enabled: bool = False
    require_approval_for_inferred_memory: bool = True
    automatic_direct_assertion_memory: bool = False
    proactive_memory_enabled: bool = True
    paralinguistic_signals_enabled: bool = True
    transcript_retention_enabled: bool = True
    companion_master_enabled: bool = True
    companion_rollout_stage: CompanionRolloutStage = "paralinguistic_pilot"
    memory_token_budget: int = Field(default=4_000, ge=0, le=64_000)
    history_token_budget: int = Field(default=8_000, ge=0, le=64_000)
    retention_days: int = Field(default=365, ge=1, le=3_650)
    show_memory_use_indicator: bool = True


class AssistantMemorySettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    curated_memory_enabled: bool | None = None
    suggestions_enabled: bool | None = None
    history_recall_enabled: bool | None = None
    compaction_enabled: bool | None = None
    hermes_sync_enabled: bool | None = None
    require_approval_for_inferred_memory: bool | None = None
    automatic_direct_assertion_memory: bool | None = None
    proactive_memory_enabled: bool | None = None
    paralinguistic_signals_enabled: bool | None = None
    transcript_retention_enabled: bool | None = None
    companion_master_enabled: bool | None = None
    companion_rollout_stage: CompanionRolloutStage | None = None
    memory_token_budget: int | None = Field(default=None, ge=0, le=64_000)
    history_token_budget: int | None = Field(default=None, ge=0, le=64_000)
    retention_days: int | None = Field(default=None, ge=1, le=3_650)
    show_memory_use_indicator: bool | None = None


class AssistantMemoryRuntimeStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    settings: AssistantMemoryRuntimeSettings
    settings_path: str
    environment_overrides: list[str] = Field(default_factory=list)
    approval_policy_locked: bool = True
    diagnostics_policy: str = "content_free"


def default_memory_settings_path() -> Path:
    override = (os.environ.get("OMNIX_CHAT_MEMORY_SETTINGS_PATH") or "").strip()
    return Path(override) if override else resources_data_root() / "omnix_chat_memory_settings.json"


def _env_bool(name: str, fallback: bool) -> tuple[bool, bool]:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return fallback, False
    return raw.strip().lower() in {"1", "true", "yes", "on"}, True


def _env_int(name: str, fallback: int, minimum: int, maximum: int) -> tuple[int, bool]:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return fallback, False
    try:
        value = int(raw)
    except ValueError:
        return fallback, True
    return min(maximum, max(minimum, value)), True


def _env_stage(fallback: CompanionRolloutStage) -> tuple[CompanionRolloutStage, bool]:
    raw = (os.environ.get("OMNIX_COMPANION_ROLLOUT_STAGE") or "").strip()
    if not raw:
        return fallback, False
    return (raw if raw in _COMPANION_STAGES else fallback), True  # type: ignore[return-value]


class AssistantMemorySettingsStore:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else default_memory_settings_path()

    def load_persisted(self) -> AssistantMemoryRuntimeSettings:
        if not self.path.is_file():
            return AssistantMemoryRuntimeSettings()
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            return AssistantMemoryRuntimeSettings.model_validate(payload)
        except (OSError, ValueError, TypeError):
            return AssistantMemoryRuntimeSettings()

    def load_effective(self) -> AssistantMemoryRuntimeStatus:
        settings = self.load_persisted()
        overrides: list[str] = []
        values = settings.model_dump()
        bool_fields = {
            "curated_memory_enabled": "OMNIX_CHAT_MEMORY_ENABLED",
            "suggestions_enabled": "OMNIX_CHAT_MEMORY_SUGGESTIONS_ENABLED",
            "history_recall_enabled": "OMNIX_CHAT_HISTORY_RECALL_ENABLED",
            "compaction_enabled": "OMNIX_CHAT_COMPACTION_ENABLED",
            "hermes_sync_enabled": "OMNIX_HERMES_MEMORY_SYNC_ENABLED",
            "automatic_direct_assertion_memory": "OMNIX_MEMORY_AUTOMATIC_DIRECT_ASSERTIONS",
            "proactive_memory_enabled": "OMNIX_COMPANION_PROACTIVE_MEMORY_ENABLED",
            "paralinguistic_signals_enabled": "OMNIX_COMPANION_PARALINGUISTIC_ENABLED",
            "transcript_retention_enabled": "OMNIX_CHAT_TRANSCRIPT_RETENTION_ENABLED",
            "companion_master_enabled": "OMNIX_COMPANION_MASTER_ENABLED",
        }
        for field, env_name in bool_fields.items():
            value, overridden = _env_bool(env_name, bool(values[field]))
            values[field] = value
            if overridden:
                overrides.append(field)
        stage, stage_overridden = _env_stage(values["companion_rollout_stage"])
        values["companion_rollout_stage"] = stage
        if stage_overridden:
            overrides.append("companion_rollout_stage")
        memory_budget, memory_overridden = _env_int(
            "OMNIX_CHAT_MEMORY_TOKEN_BUDGET",
            int(values["memory_token_budget"]),
            0,
            64_000,
        )
        history_budget, history_overridden = _env_int(
            "OMNIX_CHAT_HISTORY_TOKEN_BUDGET",
            int(values["history_token_budget"]),
            0,
            64_000,
        )
        values["memory_token_budget"] = memory_budget
        values["history_token_budget"] = history_budget
        if memory_overridden:
            overrides.append("memory_token_budget")
        if history_overridden:
            overrides.append("history_token_budget")
        values["require_approval_for_inferred_memory"] = True
        return AssistantMemoryRuntimeStatus(
            settings=AssistantMemoryRuntimeSettings.model_validate(values),
            settings_path=str(self.path),
            environment_overrides=sorted(overrides),
        )

    def update(self, request: AssistantMemorySettingsUpdate) -> AssistantMemoryRuntimeStatus:
        current = self.load_persisted()
        changes = request.model_dump(exclude_none=True)
        if changes.get("require_approval_for_inferred_memory") is False:
            raise ValueError("approval is required for inferred memory")
        changes["require_approval_for_inferred_memory"] = True
        updated = current.model_copy(update=changes)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(updated.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.path)
        return self.load_effective()


def load_memory_runtime_status() -> AssistantMemoryRuntimeStatus:
    return AssistantMemorySettingsStore().load_effective()


def load_memory_runtime_settings() -> AssistantMemoryRuntimeSettings:
    return load_memory_runtime_status().settings


__all__ = [
    "AssistantMemoryRuntimeSettings",
    "AssistantMemoryRuntimeStatus",
    "AssistantMemorySettingsStore",
    "AssistantMemorySettingsUpdate",
    "CompanionRolloutStage",
    "load_memory_runtime_settings",
    "load_memory_runtime_status",
]
