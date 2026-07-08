from __future__ import annotations

import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.assistant_memory.routes import register_assistant_memory_routes
from app.assistant_memory.settings import (
    AssistantMemorySettingsStore,
    AssistantMemorySettingsUpdate,
)
from app.chat.compaction import compaction_enabled
from app.chat.history_search import history_recall_enabled
from app.chat.memory_prompt import chat_memory_enabled
from app.chat.context_budget import prompt_budget_from_env
from app.assistant_memory.jobs import memory_suggestions_enabled
from app.assistant_memory.hermes_adapter import hermes_memory_sync_enabled


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


def test_persisted_settings_enforce_independent_server_features(tmp_path, monkeypatch):
    clear_feature_env(monkeypatch)
    path = tmp_path / "memory-settings.json"
    monkeypatch.setenv("OMNIX_CHAT_MEMORY_SETTINGS_PATH", str(path))
    store = AssistantMemorySettingsStore(path)

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
    assert chat_memory_enabled() is True
    assert memory_suggestions_enabled() is False
    assert history_recall_enabled() is True
    assert compaction_enabled() is False
    assert hermes_memory_sync_enabled() is True
    budget = prompt_budget_from_env()
    assert budget.memory_tokens == 3210
    assert budget.history_tokens == 6543
    assert json.loads(path.read_text(encoding="utf-8"))["retention_days"] == 90


def test_environment_overrides_are_reported_and_take_precedence(tmp_path, monkeypatch):
    clear_feature_env(monkeypatch)
    path = tmp_path / "memory-settings.json"
    store = AssistantMemorySettingsStore(path)
    store.update(AssistantMemorySettingsUpdate(curated_memory_enabled=False, memory_token_budget=1000))
    monkeypatch.setenv("OMNIX_CHAT_MEMORY_ENABLED", "1")
    monkeypatch.setenv("OMNIX_CHAT_MEMORY_TOKEN_BUDGET", "7777")

    status = store.load_effective()

    assert status.settings.curated_memory_enabled is True
    assert status.settings.memory_token_budget == 7777
    assert status.environment_overrides == ["curated_memory_enabled", "memory_token_budget"]


def test_inferred_memory_approval_cannot_be_disabled(tmp_path):
    store = AssistantMemorySettingsStore(tmp_path / "memory-settings.json")

    try:
        store.update(AssistantMemorySettingsUpdate(require_approval_for_inferred_memory=False))
    except ValueError as exc:
        assert str(exc) == "approval is required for inferred memory"
    else:
        raise AssertionError("approval policy must remain locked")

    assert store.load_effective().settings.require_approval_for_inferred_memory is True


def test_settings_routes_return_content_free_diagnostics_and_are_hidden(tmp_path, monkeypatch):
    clear_feature_env(monkeypatch)
    path = tmp_path / "memory-settings.json"
    monkeypatch.setenv("OMNIX_CHAT_MEMORY_SETTINGS_PATH", str(path))
    app = FastAPI()
    register_assistant_memory_routes(app)
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
    assert "content" not in json.dumps(payload).casefold()

    rejected = client.post(
        "/api/assistant/memory/settings",
        json={"require_approval_for_inferred_memory": False},
    )
    assert rejected.status_code == 403
    assert rejected.json()["detail"]["code"] == "memory_privacy_policy_rejected"

    schema = client.get("/openapi.json").json()
    assert "/api/assistant/memory/settings" not in schema["paths"]
