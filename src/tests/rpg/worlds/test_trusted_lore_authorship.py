from __future__ import annotations

from copy import deepcopy

import pytest

from app.rpg.session.genesis.world_forge_authorship_policy import (
    AUTHORED_REQUIRED,
    MACHINE_ALLOWED,
    STRUCTURAL_ONLY,
    field_authorship_policy,
    topic_authorship_policy,
)
from app.rpg.session.genesis.world_forge_profiles import FieldDefinition
from app.rpg.worlds.authorship_audit import _topic_audit
from app.rpg.worlds.generation_authorship import AuthorshipValidationError
from app.rpg.worlds.generation_authorship_runtime import (
    attach_human_authorship,
    attach_server_llm_authorship,
    build_generation_artifact,
    prove_structural_repair_non_authoring,
    validate_publishable_authorship,
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
                "short_summary": (
                    "A rain-darkened inn where couriers trade sealed rumours beneath "
                    "the watch of an indebted proprietor."
                ),
                "dossier": {
                    "schema_version": "rpg_world_entity_dossier_v1",
                    "subtitle": "A refuge built on borrowed time",
                    "quote": None,
                    "quick_facts": [{"label": "Room price", "value": "5 silver"}],
                    "sections": [
                        {
                            "id": "overview",
                            "title": "Overview",
                            "paragraphs": [
                                "The Brass Lantern survives by sheltering people who cannot afford to be noticed elsewhere."
                            ],
                        },
                        {
                            "id": "pressures",
                            "title": "Current Pressures",
                            "paragraphs": [
                                "Its proprietor owes protection money to a syndicate that now wants the cellar for clandestine meetings."
                            ],
                        },
                    ],
                    "related_entity_ids": [],
                    "generated_from_legacy": False,
                },
            }
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
            "raw_response_hash_kind": "provider_response_set",
        },
    }


def _authored() -> tuple[dict, dict]:
    candidate = _candidate()
    artifact = build_generation_artifact(
        candidate,
        run_id="run:test",
        job_id="job:test",
        topic_id="places",
        provider=candidate["provenance"],
        settings={"generator_version": "v1", "prompt_version": "v1"},
    )
    return attach_server_llm_authorship(candidate, artifact), artifact


def test_round_trip_requires_exact_string_hashes_and_server_artifact() -> None:
    authored, artifact = _authored()

    report = validate_publishable_authorship(authored, server_artifact=artifact)

    assert report["publishable"] is True
    assert report["generation_artifact_id"] == artifact["generation_artifact_id"]
    assert report["machine_structured_string_count"] >= 1

    mutated = deepcopy(authored)
    mutated["entities"][0]["dossier"]["sections"][0]["paragraphs"][0] += " Changed."
    invalid = validate_publishable_authorship(mutated, server_artifact=artifact)

    assert invalid["publishable"] is False
    assert {
        row["path"]
        for row in invalid["blocked_paths"]
    } >= {"/entities/0/dossier/sections/0/paragraphs/0"}


def test_forged_topic_level_provenance_is_not_authorship_proof() -> None:
    candidate = _candidate()
    candidate["provenance"].update(
        {
            "used_llm": True,
            "provider_authored_presentation": True,
        }
    )

    report = validate_publishable_authorship(candidate)

    assert report["publishable"] is False
    assert any(
        row["code"] in {"trusted_authorship_missing", "server_generation_artifact_missing"}
        for row in report["blocked_paths"]
    )


def test_human_edit_preserves_llm_parent_lineage_without_ai_relabelling() -> None:
    authored, artifact = _authored()
    edited = deepcopy(authored)
    edited["entities"][0]["short_summary"] = (
        "A rain-darkened refuge where couriers trade sealed rumours while its owner "
        "struggles beneath syndicate debt."
    )

    mixed = attach_human_authorship(
        edited,
        event_id="humanedit:test",
        prior_candidate=authored,
        edited_llm=True,
    )
    report = validate_publishable_authorship(mixed, server_artifact=artifact)
    origins = {
        row["path"]: row
        for row in mixed["provenance"]["authorship"]["origin_ledger"]
    }

    assert report["publishable"] is True
    assert origins["/entities/0/short_summary"]["authorship_class"] == "human_edited_llm"
    assert origins["/entities/0/short_summary"]["human_edit_event_id"] == "humanedit:test"
    assert origins["/entities/0/short_summary"]["parent_origin"]["authorship_class"] == "llm_authored"


def test_structured_fact_value_is_machine_structured_not_lore_prose() -> None:
    authored, artifact = _authored()
    origins = {
        row["path"]: row
        for row in authored["provenance"]["authorship"]["origin_ledger"]
    }

    assert origins["/facts/0/object"]["authorship_class"] == "machine_structured"
    assert origins["/facts/0/object"]["generation_artifact_id"] == ""
    assert validate_publishable_authorship(authored, server_artifact=artifact)["publishable"]


def test_deterministic_marker_blocks_otherwise_valid_candidate() -> None:
    authored, artifact = _authored()
    authored["provenance"]["generator"] = "deterministic_world_forge_v1"

    report = validate_publishable_authorship(authored, server_artifact=artifact)

    assert report["publishable"] is False
    assert any(
        row["code"] == "deterministic_world_forge_v1"
        for row in report["blocked_paths"]
    )


def test_structural_repair_proves_no_lore_strings_changed() -> None:
    candidate = _candidate()
    proof = prove_structural_repair_non_authoring(
        {"response": candidate},
        candidate,
    )
    assert proof["non_authoring"] is True

    changed = deepcopy(candidate)
    changed["entities"][0]["dossier"]["sections"][0]["paragraphs"].append(
        "Application-authored filler is forbidden."
    )
    with pytest.raises(AuthorshipValidationError):
        prove_structural_repair_non_authoring(candidate, changed)


def test_profile_fields_publish_explicit_authorship_policy() -> None:
    description = FieldDefinition("description", "string", required=True)
    price = FieldDefinition("price", "number")
    location = FieldDefinition(
        "location_id",
        "entity_ref",
        allowed_target_domains=("places",),
    )

    assert field_authorship_policy(description) == AUTHORED_REQUIRED
    assert field_authorship_policy(price) == MACHINE_ALLOWED
    assert field_authorship_policy(location) == STRUCTURAL_ONLY
    policy = topic_authorship_policy((description, price, location))
    assert policy["entity_fields"] == {
        "description": AUTHORED_REQUIRED,
        "price": MACHINE_ALLOWED,
        "location_id": STRUCTURAL_ONLY,
    }


def test_audit_classifies_verified_and_missing_lore() -> None:
    authored, _artifact = _authored()
    verified = _topic_audit(
        {
            "topic_id": "places",
            "source": "ai",
            "status": "ready",
            "content": authored,
        }
    )
    assert verified["classification"] == "verified_authored"
    assert verified["publishable"] is True

    missing = _candidate()
    missing["entities"][0]["short_summary"] = ""
    missing["entities"][0]["dossier"] = {
        "schema_version": "rpg_world_entity_dossier_v1",
        "sections": [],
        "generation_required": True,
    }
    missing["provenance"] = {}
    audited = _topic_audit(
        {
            "topic_id": "places",
            "source": "legacy",
            "status": "ready",
            "content": missing,
        }
    )
    assert audited["classification"] == "missing_lore"
    assert audited["entities"][0]["generation_required"] is True
