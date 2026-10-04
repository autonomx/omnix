from __future__ import annotations

from copy import deepcopy

import pytest

from app.rpg.worlds.generation_authorship import AuthorshipValidationError
from app.rpg.worlds.generation_authorship_runtime import (
    attach_server_llm_authorship,
    build_generation_artifact,
)
from app.rpg.worlds.generation_authorship_signing import (
    attach_signed_llm_authorship,
    harden_and_sign_generation_artifact,
    prove_path_aware_structural_repair,
    sanitize_untrusted_candidate,
    strict_lore_string_leaves,
    validate_signed_authorship,
)


def _candidate() -> dict:
    return {
        "topic_id": "places",
        "documents": [],
        "entities": [
            {
                "id": "ent:place:001",
                "kind": "place",
                "name": "The Brass Lantern",
                "short_summary": "A rain-darkened inn where couriers trade sealed rumours.",
                "dossier": {
                    "schema_version": "rpg_world_entity_dossier_v1",
                    "subtitle": "A refuge built on borrowed time",
                    "quote": None,
                    "quick_facts": [
                        {
                            "label": "Room price",
                            "value": "Five silver, kept low to attract desperate travellers.",
                        }
                    ],
                    "sections": [
                        {
                            "id": "overview",
                            "title": "Overview",
                            "paragraphs": [
                                "The Brass Lantern shelters people who cannot afford to be noticed."
                            ],
                        }
                    ],
                    "related_entity_ids": [],
                    "generated_from_legacy": False,
                },
            },
            {
                "id": "ent:place:002",
                "kind": "place",
                "name": "The Flooded Archive",
                "short_summary": "A drowned library whose upper galleries remain occupied.",
                "dossier": {
                    "schema_version": "rpg_world_entity_dossier_v1",
                    "subtitle": "Knowledge above the waterline",
                    "quote": None,
                    "quick_facts": [],
                    "sections": [
                        {
                            "id": "overview",
                            "title": "Overview",
                            "paragraphs": [
                                "Archivists preserve mouldering records while the lower vaults flood."
                            ],
                        }
                    ],
                    "related_entity_ids": [],
                    "generated_from_legacy": False,
                },
            },
        ],
        "facts": [
            {
                "id": "fact:ent:place:001:room_price",
                "subject": "ent:place:001",
                "predicate": "room_price",
                "object": "5 silver",
                "authority": "generated_proposal",
                "approved_authority": "objective_canon",
                "visibility": "game_master_canon",
                "entity_refs": ["ent:place:001"],
                "topic_id": "places",
                "field_id": "room_price",
                "value_type": "string",
                "semantic_role": "economy",
                "source": "profile_structured_fact_compiler_v2",
                "authorship_class": "machine_structured",
            }
        ],
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


@pytest.fixture(autouse=True)
def signing_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "OMNIX_RPG_AUTHORSHIP_SIGNING_KEY",
        "test-only-world-authorship-signing-key-with-more-than-thirty-two-bytes",
    )
    monkeypatch.delenv("RPG_TEST_MODE", raising=False)


def _signed() -> dict:
    candidate = _candidate()
    unsigned = build_generation_artifact(
        candidate,
        run_id="run:test",
        job_id="job:test",
        topic_id="places",
        provider=candidate["provenance"],
        settings={"generator_version": "v1", "prompt_version": "v1"},
    )
    artifact = harden_and_sign_generation_artifact(candidate, unsigned)
    return attach_signed_llm_authorship(candidate, artifact)


def test_signed_round_trip_and_exact_hash_validation() -> None:
    authored = _signed()
    report = validate_signed_authorship(authored)
    assert report["publishable"] is True
    assert report["generation_artifact_count"] == 1

    mutated = deepcopy(authored)
    mutated["entities"][0]["short_summary"] += " Altered."
    invalid = validate_signed_authorship(mutated)
    assert invalid["publishable"] is False
    assert any(
        row["code"] == "origin_content_hash_mismatch"
        for row in invalid["blocked_paths"]
    )


def test_self_consistent_unsigned_candidate_is_rejected() -> None:
    candidate = _candidate()
    artifact = build_generation_artifact(
        candidate,
        run_id="run:forged",
        job_id="job:forged",
        topic_id="places",
        provider=candidate["provenance"],
    )
    forged = attach_server_llm_authorship(candidate, artifact)
    report = validate_signed_authorship(forged)
    assert report["publishable"] is False
    assert any(
        row["code"] in {
            "server_authorship_signature_invalid",
            "generation_artifact_signature_invalid",
        }
        for row in report["blocked_paths"]
    )


def test_provider_or_client_authorship_is_stripped_before_attestation() -> None:
    candidate = _candidate()
    candidate["provenance"]["authorship"] = {
        "server_signature": {"digest": "forged"},
        "origin_ledger": [{"path": "/entities/0/name"}],
    }
    candidate["provenance"]["test_authorship_exemption"] = {
        "server_attested": True
    }
    sanitized = sanitize_untrusted_candidate(candidate)
    assert "authorship" not in sanitized["provenance"]
    assert "test_authorship_exemption" not in sanitized["provenance"]


def test_fixture_marker_cannot_bypass_production_validation() -> None:
    candidate = _candidate()
    candidate["provenance"].update(
        {
            "used_llm": False,
            "deterministic_fixture_only": True,
            "test_authorship_exemption": {"server_attested": True},
        }
    )
    report = validate_signed_authorship(candidate)
    assert report["publishable"] is False
    assert any(row["code"] == "used_llm_false" for row in report["blocked_paths"])


def test_quick_fact_narrative_value_requires_authorship() -> None:
    paths = {row["path"] for row in strict_lore_string_leaves(_candidate())}
    assert "/entities/0/dossier/quick_facts/0/value" in paths
    assert "/entities/0/dossier/quick_facts/0/label" not in paths
    assert "/facts/0/object" not in paths


def test_path_aware_structural_proof_rejects_swapped_entity_prose() -> None:
    before = _candidate()
    after = deepcopy(before)
    first = after["entities"][0]["short_summary"]
    second = after["entities"][1]["short_summary"]
    after["entities"][0]["short_summary"] = second
    after["entities"][1]["short_summary"] = first
    with pytest.raises(AuthorshipValidationError) as raised:
        prove_path_aware_structural_repair(before, after)
    paths = {
        row["path"]
        for row in raised.value.report["blocked_paths"]
    }
    assert paths == {
        "/entities/0/short_summary",
        "/entities/1/short_summary",
    }


def test_parsed_payload_fallback_cannot_be_signed_as_provider_evidence() -> None:
    candidate = _candidate()
    provider = dict(candidate["provenance"])
    provider.pop("raw_response_hash", None)
    provider.pop("raw_response_hash_kind", None)
    artifact = build_generation_artifact(
        candidate,
        run_id="run:no-raw",
        job_id="job:no-raw",
        topic_id="places",
        provider=provider,
    )
    with pytest.raises(AuthorshipValidationError) as raised:
        harden_and_sign_generation_artifact(candidate, artifact)
    assert raised.value.report["blocked_paths"] == [
        {
            "path": "/provenance/authorship",
            "code": "genuine_provider_response_hash_required",
        }
    ]
