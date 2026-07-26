from __future__ import annotations

from copy import deepcopy

import pytest

from app.rpg.worlds.generation_authorship_policy_signing import (
    bind_signed_authorship_policy,
    validate_policy_bound_authorship,
)
from app.rpg.worlds.generation_authorship_runtime import build_generation_artifact
from app.rpg.worlds.generation_authorship_signing import (
    attach_signed_llm_authorship,
    harden_and_sign_generation_artifact,
)


@pytest.fixture(autouse=True)
def signing_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "OMNIX_RPG_AUTHORSHIP_SIGNING_KEY",
        "test-only-policy-signing-key-with-more-than-thirty-two-bytes",
    )
    monkeypatch.delenv("RPG_TEST_MODE", raising=False)


def _candidate() -> dict:
    return {
        "topic_id": "actors",
        "entities": [
            {
                "id": "ent:actor:001",
                "kind": "actor",
                "name": "Mara Venn",
                "disposition": "neutral",
                "description": "A courier who knows which checkpoints change guards at dusk.",
            }
        ],
        "documents": [],
        "facts": [],
        "relationships": [],
        "knowledge_rules": [],
        "story_threads": [],
        "provenance": {
            "generator": "structured_world_forge_provider_v1",
            "provider": "lmstudio",
            "model": "qwen-test",
            "raw_response_hash": "a" * 64,
            "raw_response_hash_kind": "provider_response",
        },
    }


def _policy() -> dict:
    return {
        "schema_version": "rpg_world_field_authorship_policy_v1",
        "default_policy": "authored_required",
        "production_generated_default_policy": "llm_required",
        "entity_fields": {
            "name": "authored_required",
            "description": "authored_required",
            "disposition": "machine_allowed",
        },
        "presentation_fields": {"name": "llm_required", "description": "llm_required"},
    }


def _authored() -> dict:
    candidate = _candidate()
    policy = _policy()
    unsigned = build_generation_artifact(
        candidate,
        run_id="run:policy",
        job_id="job:policy",
        topic_id="actors",
        provider=candidate["provenance"],
    )
    artifact = harden_and_sign_generation_artifact(
        candidate,
        unsigned,
        policy=policy,
    )
    payload = attach_signed_llm_authorship(candidate, artifact, policy=policy)
    return bind_signed_authorship_policy(payload, policy)


def test_signed_policy_allows_schema_declared_machine_enum() -> None:
    report = validate_policy_bound_authorship(_authored())
    assert report["publishable"] is True
    assert report["origin_count"] == 2


def test_signed_policy_tampering_invalidates_authorship_record() -> None:
    payload = deepcopy(_authored())
    payload["provenance"]["authorship"]["authorship_policy"]["entity_fields"][
        "description"
    ] = "machine_allowed"
    report = validate_policy_bound_authorship(payload)
    assert report["publishable"] is False
    assert any(
        row["code"] == "server_authorship_signature_invalid"
        for row in report["blocked_paths"]
    )
