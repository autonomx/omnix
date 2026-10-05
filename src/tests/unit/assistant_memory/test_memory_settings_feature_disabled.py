"""Chat keeps working when the assistant-memory feature is disabled."""
from __future__ import annotations

from types import SimpleNamespace

from app.platform.assistant_memory import settings as memory_settings
from app.platform.assistant_memory.settings import AssistantMemoryRuntimeSettings


def test_unregistered_memory_settings_fall_back_to_defaults(monkeypatch) -> None:
    # A settings service without the assistant-memory spec, as composed when
    # OMNIX_FEATURES excludes assistant-memory (the multi-host topology).
    monkeypatch.setattr("app.settings.access.current_settings_service", lambda: SimpleNamespace(specs={}))
    status = memory_settings.load_memory_runtime_status()
    assert status.settings_source == "feature_disabled_defaults"
    defaults = AssistantMemoryRuntimeSettings()
    assert status.settings.transcript_retention_enabled == defaults.transcript_retention_enabled
    assert memory_settings.load_memory_runtime_settings().transcript_retention_enabled is True
