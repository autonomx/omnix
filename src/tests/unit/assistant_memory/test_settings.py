from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.assistant_memory.routes import register_assistant_memory_routes
from app.assistant_memory.settings import AssistantMemorySettingsUpdate
from app.chat.compaction import compaction_enabled
from app.chat.context_budget import prompt_budget_from_env
from app.chat.history_search import history_recall_enabled
from app.chat.memory_prompt import chat_memory_enabled
from app.assistant_memory.jobs import memory_suggestions_enabled
from app.assistant_memory.hermes_adapter import hermes_memory_sync_enabled
from tests.support.assistant_memory_settings import (
    InMemorySettingsService,
    in_memory_assistant_memory_settings_store,
)
from app.settings.service import SettingRevisionConflict


def _install_service(monkeypatch):
    import app.settings.access as settings_access

    service, store = in_memory_assistant_memory_settings_store()
    monkeypatch.setattr(settings_access, "current_settings_service", lambda: service)
    return service, store


def clear_feature_env(monkeypatch):
    for name in (
        "OMNIX_CHAT_MEMORY_ENABLED",
        "OMNIX_CHAT_MEMORY_SUGGESTIONS_ENABLED",
        "OMNIX_CHAT_HISTORY_RECALL_ENABLED",
        "OMNIX_CHAT_COMPACTION_ENABLED",
        "OMNIX_HERMES_MEMORY_SYNC_ENABLED",
        "OMNIX_CHAT_MEMORY_TOKEN_BUDGET",
        "OMNIX_CHAT_HISTORY_TOKEN_BUDGET",
    ):
        monkeypatch.delenv(name, raising=False)


def test_persisted_settings_enforce_independent_server_features(monkeypatch):
    clear_feature_env(monkeypatch)
    _service, store = _install_service(monkeypatch)

    status = store.update(
        AssistantMemorySettingsUpdate(
            curated_memory_enabled=True,
            suggestions_enabled=False,
            history_recall_enabled=True,
            compaction_enabled=False,
            hermes_sync_enabled=True,
            memory_token_budget=3210,
            history_token_budget=6543,
            retention_days=90,
        )
    )

    assert status.settings.curated_memory_enabled is True
    assert status.settings.suggestions_enabled is False
    assert status.settings_source == "settings_service"
    assert chat_memory_enabled() is True
    assert memory_suggestions_enabled() is False
    assert history_recall_enabled() is True
    assert compaction_enabled() is False
    assert hermes_memory_sync_enabled() is True
    budget = prompt_budget_from_env()
    assert budget.memory_tokens == 3210
    assert budget.history_tokens == 6543
    assert store.load_persisted().retention_days == 90


def test_environment_overrides_are_reported_and_take_precedence(monkeypatch):
    clear_feature_env(monkeypatch)
    _service, store = _install_service(monkeypatch)
    store.update(
        AssistantMemorySettingsUpdate(
            curated_memory_enabled=False,
            memory_token_budget=1000,
        )
    )
    monkeypatch.setenv("OMNIX_CHAT_MEMORY_ENABLED", "1")
    monkeypatch.setenv("OMNIX_CHAT_MEMORY_TOKEN_BUDGET", "7777")

    status = store.load_effective()

    assert status.settings.curated_memory_enabled is True
    assert status.settings.memory_token_budget == 7777
    assert status.environment_overrides == [
        "curated_memory_enabled",
        "memory_token_budget",
    ]


def test_inferred_memory_approval_cannot_be_disabled(monkeypatch):
    _service, store = _install_service(monkeypatch)

    try:
        store.update(
            AssistantMemorySettingsUpdate(
                require_approval_for_inferred_memory=False
            )
        )
    except ValueError as exc:
        assert str(exc) == "approval is required for inferred memory"
    else:
        raise AssertionError("approval policy must remain locked")

    assert store.load_effective().settings.require_approval_for_inferred_memory is True


def test_settings_read_fails_closed_without_a_settings_service(monkeypatch):
    import app.settings.access as settings_access
    from app.assistant_memory.settings import load_memory_runtime_status

    def unavailable_service():
        raise RuntimeError("settings service is not installed")

    monkeypatch.setattr(settings_access, "current_settings_service", unavailable_service)
    with pytest.raises(RuntimeError, match="settings service is not installed"):
        load_memory_runtime_status()


def test_memory_settings_updates_use_optimistic_revisions(monkeypatch):
    service = InMemorySettingsService()
    from app.assistant_memory.persistence.settings_store import (
        ASSISTANT_MEMORY_SETTINGS_KEY,
        SettingsServiceAssistantMemorySettingsStore,
    )

    first = SettingsServiceAssistantMemorySettingsStore(service)
    second = SettingsServiceAssistantMemorySettingsStore(service)
    current = service.get(ASSISTANT_MEMORY_SETTINGS_KEY)
    assert current is not None
    stale_revision = int(current["revision"])
    first.update(AssistantMemorySettingsUpdate(memory_token_budget=1200))
    assert first.load_persisted().memory_token_budget == 1200
    assert second.load_persisted().memory_token_budget == 1200
    assert stale_revision == 0
    with pytest.raises(SettingRevisionConflict, match="revision conflict"):
        service.set(
            ASSISTANT_MEMORY_SETTINGS_KEY,
            first.load_persisted().model_dump(mode="json"),
            expected_revision=stale_revision,
        )


def test_settings_routes_are_content_free_and_typed_in_openapi():
    _service, store = in_memory_assistant_memory_settings_store()
    app = FastAPI()
    register_assistant_memory_routes(
        app,
        memory_settings_store_factory=lambda: store,
    )
    client = TestClient(app)

    updated = client.post(
        "/api/assistant/memory/settings",
        json={
            "curated_memory_enabled": True,
            "history_recall_enabled": False,
            "suggestions_enabled": True,
            "show_memory_use_indicator": True,
        },
    )
    assert updated.status_code == 200
    payload = updated.json()
    assert payload["settings"]["curated_memory_enabled"] is True
    assert payload["settings"]["history_recall_enabled"] is False
    assert payload["diagnostics_policy"] == "content_free"
    assert "records" not in payload
    assert "candidates" not in payload
    assert "memory_ids" not in payload

    rejected = client.post(
        "/api/assistant/memory/settings",
        json={"require_approval_for_inferred_memory": False},
    )
    assert rejected.status_code == 403
    assert rejected.json()["detail"]["code"] == "memory_privacy_policy_rejected"

    schema = client.get("/openapi.json").json()
    operations = schema["paths"]["/api/assistant/memory/settings"]
    assert {"get", "post"} <= set(operations)
    assert "application/json" in operations["post"]["requestBody"]["content"]
    assert "application/json" in operations["get"]["responses"]["200"]["content"]
