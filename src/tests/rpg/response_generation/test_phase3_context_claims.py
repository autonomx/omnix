from __future__ import annotations

from app.rpg.response_generation.claim_ledger import (
    ClaimLedger,
    ClaimRecord,
    derive_claim_ledger,
)
from app.rpg.response_generation.context_compiler import (
    EvidenceCard,
    NarrationContextCompiler,
)
from app.rpg.response_generation.contracts import (
    ResponseMode,
    ResponseRequest,
    SectionType,
    SemanticResponsePlan,
    SemanticSection,
)
from app.rpg.response_generation.semantic_plan import validate_semantic_plan


def test_phase3_claim_ledger_derives_resolved_state_claims():
    ledger = derive_claim_ledger(
        "turn-3",
        {
            "allowed_claim_refs": ["service.room_price"],
            "resolved_result": {
                "current_location": "rusty_flagon",
                "location_changed": False,
                "currency_delta": {"silver": -5},
                "inventory_delta": {"room_key": 1},
                "new_facts": ["Bran rents rooms"],
            },
            "approved_proposal_refs": ["proposal.market_lead"],
            "prohibited_claim_refs": ["quest.completed"],
        },
    )

    assert ledger.schema_version == "rpg_claim_ledger_v1"
    assert ledger.contains("service.room_price")
    assert ledger.contains("location.current")
    assert ledger.contains("currency.silver")
    assert ledger.contains("inventory.room_key")
    assert ledger.contains("fact.bran_rents_rooms")
    assert ledger.contains("proposal.market_lead")
    assert ledger.prohibited_claim_refs == ("quest.completed",)


def test_phase3_production_grounding_cannot_be_silently_disabled():
    ledger = derive_claim_ledger(
        "turn-production",
        {
            "production_rpg_response": True,
            "grounding_required": False,
        },
    )

    assert ledger.grounding_required is True
    assert ledger.as_policy_payload()["strict_claim_refs"] is True


def test_phase3_context_is_current_turn_first_compact_and_hides_evidence():
    request = ResponseRequest(
        turn_id="turn-context",
        player_input="Where is the Moonwell?",
        speaker_id="npc_bran",
        authoritative_turn_result={
            "must_answer": "Explain what Bran knows about the Moonwell.",
            "response_mode": "investigation",
            "visible_facts": {"location": "Rusty Flagon"},
            "scene_card": {"scene_id": "tavern", "description": "x" * 900},
            "entity_cards": [
                {"entity_id": f"npc-{index}", "name": f"NPC {index}"}
                for index in range(12)
            ],
            "speaker_card": {"entity_id": "npc_bran", "name": "Bran"},
            "allowed_claim_refs": ["fact.moonwell_unknown"],
        },
    )
    evidence = [
        EvidenceCard("visible-1", "journal", "No confirmed Moonwell entry."),
        EvidenceCard("hidden-1", "director", "A hidden Moonwell exists.", visibility="hidden"),
    ]

    context = NarrationContextCompiler(max_entities=3).compile(request, evidence=evidence)
    payload = context.as_prompt_payload()

    assert context.response_mode is ResponseMode.INVESTIGATION
    assert context.player_input == "Where is the Moonwell?"
    assert context.must_answer.startswith("Explain what Bran knows")
    assert list(payload)[2] == "current_turn"
    assert payload["current_turn"]["player_input"] == request.player_input
    assert len(context.entity_cards) == 3
    assert context.trace.truncated_fields == ("entity_cards",)
    assert context.trace.hidden_evidence_ids == ("hidden-1",)
    assert context.trace.included_evidence_ids == ("visible-1",)
    assert "A hidden Moonwell exists" not in str(payload)
    assert "full_transcript" in context.trace.omitted_fields


def test_phase3_semantic_sections_require_valid_typed_references():
    ledger = ClaimLedger(
        schema_version="rpg_claim_ledger_v1",
        turn_id="turn-semantic",
        records=(
            ClaimRecord("service.room_price", "service", value=5, speaker_ids=("npc_bran",)),
            ClaimRecord("fact.hidden", "fact", visibility="hidden"),
        ),
        prohibited_claim_refs=("quest.completed",),
    )
    valid = SemanticResponsePlan(
        mode=ResponseMode.DIALOGUE,
        sections=(
            SemanticSection(
                section_id="bran-price",
                section_type=SectionType.NPC_DIALOGUE,
                speaker_id="npc_bran",
                claim_refs=("service.room_price",),
                text="Five silver for the night.",
            ),
        ),
    )
    invalid = SemanticResponsePlan(
        mode=ResponseMode.ACTION,
        sections=(
            SemanticSection(
                section_id="unreferenced",
                section_type=SectionType.RESULT,
                text="The quest is complete.",
            ),
            SemanticSection(
                section_id="hidden",
                section_type=SectionType.RESULT,
                claim_refs=("fact.hidden",),
                text="The hidden route is revealed.",
            ),
            SemanticSection(
                section_id="unknown",
                section_type=SectionType.RESULT,
                claim_refs=("quest.completed",),
                text="The quest is complete.",
            ),
        ),
    )

    valid_report = validate_semantic_plan(valid, ledger)
    invalid_report = validate_semantic_plan(invalid, ledger)

    assert valid_report.ok is True
    assert valid_report.referenced_claims == ("service.room_price",)
    assert invalid_report.ok is False
    assert "missing_reference:unreferenced" in invalid_report.issues
    assert "unknown_claim:hidden:fact.hidden" in invalid_report.issues
    assert "prohibited_claim:unknown:quest.completed" in invalid_report.issues


def test_phase3_soft_truth_requires_explicit_allowance():
    ledger = ClaimLedger("rpg_claim_ledger_v1", "turn-soft", ())
    plan = SemanticResponsePlan(
        mode=ResponseMode.RECOVERY,
        sections=(
            SemanticSection(
                section_id="rumor",
                section_type=SectionType.NARRATION,
                soft_truth_refs=("rumor.northern_caravan",),
                text="A caravan rumor points north.",
                metadata={"factual": True},
            ),
        ),
    )

    rejected = validate_semantic_plan(plan, ledger)
    accepted = validate_semantic_plan(
        plan,
        ledger,
        allowed_soft_truth_refs=("rumor.northern_caravan",),
    )

    assert rejected.ok is False
    assert accepted.ok is True
