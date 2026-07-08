from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.assistant_memory import (
    DEFAULT_PROFILE_ID,
    DEFAULT_WORKSPACE_ID,
    MemoryCandidate,
    MemoryRecord,
    candidate_acceptance,
    explicit_save_decision,
    move_scope_decision,
    prompt_eligibility,
    resolve_chat_scope,
    source_requires_approval,
)

NOW = "2026-07-08T00:00:00+00:00"


def record(**overrides) -> MemoryRecord:
    payload = {
        "id": "memory:one",
        "scope": "project",
        "scope_id": "project:omnix",
        "category": "instruction",
        "source": "user_saved",
        "content": "Use the rpg branch as the source of truth.",
        "normalized_content": "use the rpg branch as the source of truth",
        "confidence": 1.0,
        "trust_level": "user_approved",
        "sensitivity": "normal",
        "provenance_type": "user_message",
        "provenance_id": "msg:one",
        "created_at": NOW,
        "updated_at": NOW,
    }
    payload.update(overrides)
    return MemoryRecord.model_validate(payload)


def candidate(**overrides) -> MemoryCandidate:
    payload = {
        "id": "candidate:one",
        "source_session_id": "chat:one",
        "source_message_id": "msg:one",
        "candidate_fingerprint": "fingerprint-one",
        "proposed_scope": "project",
        "proposed_scope_id": "project:omnix",
        "proposed_category": "instruction",
        "proposed_content": "Use GitHub Actions as verification truth.",
        "confidence": 0.9,
        "source": "assistant_suggested",
        "trust_level": "unverified_agent",
        "created_at": NOW,
    }
    payload.update(overrides)
    return MemoryCandidate.model_validate(payload)


def test_scope_resolution_uses_backend_defaults_and_validates_identifiers(monkeypatch):
    monkeypatch.delenv("OMNIX_CHAT_PROFILE_ID", raising=False)
    monkeypatch.delenv("OMNIX_CHAT_WORKSPACE_ID", raising=False)

    scope = resolve_chat_scope("chat:one", project_id="project:omnix")

    assert scope.profile_id == DEFAULT_PROFILE_ID
    assert scope.workspace_id == DEFAULT_WORKSPACE_ID
    assert scope.project_id == "project:omnix"
    with pytest.raises(ValueError):
        resolve_chat_scope("chat:one", project_id="../../other-project")


def test_prompt_eligibility_filters_scope_status_expiry_trust_and_secrets():
    context = resolve_chat_scope("chat:one", project_id="project:omnix")
    assert prompt_eligibility(record(), context).allowed is True
    assert prompt_eligibility(record(scope_id="project:other"), context).reason == "scope_mismatch"
    assert prompt_eligibility(record(status="archived"), context).reason == "record_archived"
    assert prompt_eligibility(record(trust_level="unverified_agent"), context).reason == "trust_not_approved"
    assert prompt_eligibility(record(sensitivity="secret"), context).reason == "secret_content_blocked"
    assert (
        prompt_eligibility(
            record(expires_at="2026-07-07T00:00:00+00:00"),
            context,
            now=datetime(2026, 7, 8, tzinfo=timezone.utc),
        ).reason
        == "record_expired"
    )


def test_pending_candidate_cannot_self_approve_or_enter_prompt_contract():
    assert candidate_acceptance(candidate()).allowed is True
    assert candidate_acceptance(candidate(status="accepted")).reason == "candidate_accepted"
    assert candidate_acceptance(candidate(trust_level="user_approved")).reason == "candidate_cannot_self_approve"
    assert candidate_acceptance(candidate(sensitivity="secret")).reason == "secret_content_blocked"


def test_sources_and_external_content_require_review():
    assert source_requires_approval("user_saved") is False
    assert source_requires_approval("assistant_suggested") is True
    assert source_requires_approval("imported") is True
    assert source_requires_approval("hermes") is True
    assert explicit_save_decision(sensitivity="normal", content_source="user_message").allowed is True
    assert explicit_save_decision(sensitivity="normal", content_source="web").reason == "external_content_requires_review"
    assert explicit_save_decision(sensitivity="secret", content_source="user_message").reason == "secret_content_blocked"


def test_move_scope_requires_source_visibility_and_available_target():
    project_context = resolve_chat_scope("chat:one", project_id="project:omnix")
    no_project_context = resolve_chat_scope("chat:one")

    assert move_scope_decision(record(), "workspace", project_context).allowed is True
    assert move_scope_decision(record(), "project", no_project_context).reason == "source_scope_mismatch"
    workspace_record = record(scope="workspace", scope_id=DEFAULT_WORKSPACE_ID)
    assert move_scope_decision(workspace_record, "project", no_project_context).reason == "target_scope_unavailable"
