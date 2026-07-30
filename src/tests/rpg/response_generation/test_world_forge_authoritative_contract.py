from __future__ import annotations

import json

import pytest

from app.providers.structured.errors import (
    StructuredDecodeError,
    StructuredResourceError,
)
from app.providers.structured.parsing import (
    decode_exact_json_object,
    validate_json_resources,
)
from app.rpg.session.genesis.world_forge_contract import CampaignTopicNode
from app.rpg.worlds.generation_contract_bundle import build_topic_contract_bundle
from app.rpg.worlds.generation_first_pass_provider import _authored_system_prompt
from app.rpg.worlds.generation_contract_receipt import (
    canonical_candidate_content_hash,
    require_authoritative_contract_receipt,
)


def _node(topic_id: str = "setting_rules") -> CampaignTopicNode:
    return CampaignTopicNode(
        topic_id=topic_id,
        title="Setting Rules",
        category="lore",
        target_count=1,
        metadata={"entity_kind": "setting_rule"},
    )


def _draft(bundle, *, prose: str = "Magic always leaves visible evidence."):
    return {
        "topic_id": "setting_rules",
        "documents": [],
        "entities": [
            {
                "id": "ent:setting_rules:001",
                "kind": "setting_rule",
                "name": "The Cost of Magic",
                "short_summary": "Every working has an observable price.",
                "attributes": {},
                "dossier": {
                    "sections": {
                        section_id: {"paragraphs": [prose]}
                        for section_id, _title in bundle.dossier_template
                    }
                },
            }
        ],
        "relationships": [],
        "knowledge_rules": [],
        "story_threads": [],
    }


def test_authored_contract_omits_server_owned_fields_and_fixes_setting_sections() -> None:
    bundle = build_topic_contract_bundle(
        _node(),
        allocated_entity_ids=("ent:setting_rules:001",),
        dependencies={},
    )
    schema_text = json.dumps(bundle.authored_draft_model.model_json_schema())

    assert '"provenance"' not in schema_text
    assert '"facts"' not in schema_text
    assert [section_id for section_id, _ in bundle.dossier_template] == [
        "overview",
        "foundations",
        "lived_experience",
        "boundaries",
        "consequences",
    ]


def test_authored_prompt_has_one_unambiguous_wire_contract() -> None:
    node = _node()
    entity_ids = ("ent:setting_rules:001",)
    bundle = build_topic_contract_bundle(
        node,
        allocated_entity_ids=entity_ids,
        dependencies={},
    )

    prompt = _authored_system_prompt(
        node,
        bundle,
        batch_index=0,
        batch_count=1,
        existing_entities=(),
        assigned_entity_ids=entity_ids,
        assigned_entities=(),
    )

    assert "Return exactly one bare JSON object" in prompt
    assert "Never return provenance or facts" in prompt
    assert "entities[].dossier.sections" in prompt
    assert "Set provenance to exactly {}" not in prompt
    assert "Dossier sections use stable IDs" not in prompt


def test_materializer_assigns_canonical_structure_and_content_bound_receipt() -> None:
    bundle = build_topic_contract_bundle(
        _node(),
        allocated_entity_ids=("ent:setting_rules:001",),
        dependencies={},
    )
    authored = bundle.authored_draft_model.model_validate(_draft(bundle))
    bundle.semantic_validator(authored)
    candidate = bundle.materializer(authored)

    dossier = candidate.entities[0].model_dump()["dossier"]
    assert dossier["schema_version"] == "rpg_world_entity_dossier_v1"
    assert [row["id"] for row in dossier["sections"]] == [
        section_id for section_id, _ in bundle.dossier_template
    ]
    receipt = require_authoritative_contract_receipt(candidate)
    assert receipt["canonical_content_hash"] == canonical_candidate_content_hash(
        candidate
    )
    assert receipt["canonical_contract_hash"] == bundle.canonical_contract_hash


def test_semantic_contract_rejects_mojibake_and_repeated_long_prose() -> None:
    bundle = build_topic_contract_bundle(
        _node(),
        allocated_entity_ids=("ent:setting_rules:001",),
        dependencies={},
    )
    mojibake = bundle.authored_draft_model.model_validate(
        _draft(bundle, prose="The gate\u00e2\u20ac\u2122s price is visible.")
    )
    with pytest.raises(ValueError, match="mojibake"):
        bundle.semantic_validator(mojibake)

    repeated = "The same unusually long paragraph is repeated without variation. " * 4
    duplicate = bundle.authored_draft_model.model_validate(
        _draft(bundle, prose=repeated)
    )
    with pytest.raises(ValueError, match="repeated_long_prose"):
        bundle.semantic_validator(duplicate)


def test_exact_json_and_resource_limits_fail_closed() -> None:
    with pytest.raises(StructuredDecodeError):
        decode_exact_json_object("```json\n{}\n```")
    with pytest.raises(StructuredDecodeError):
        decode_exact_json_object('preface {"ok": true}')
    assert decode_exact_json_object('{"ok":true}') == {"ok": True}

    with pytest.raises(StructuredResourceError):
        validate_json_resources({"rows": ["x" * 20]}, max_string_length=8)
    with pytest.raises(StructuredResourceError):
        validate_json_resources({"rows": [1, 2, 3]}, max_array_length=2)
