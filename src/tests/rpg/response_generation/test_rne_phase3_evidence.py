from __future__ import annotations

from app.rpg.narrative_engine import (
    AuthorityClass,
    EvidenceAccessContext,
    EvidenceBroker,
    EvidenceQuery,
    InMemoryEvidenceSource,
    narrative_fixture_evidence,
)


def _broker() -> EvidenceBroker:
    return EvidenceBroker([InMemoryEvidenceSource(narrative_fixture_evidence(), source_id="fixtures")])


def test_vexira_retrieval_returns_character_scene_and_lore_evidence() -> None:
    result = _broker().retrieve(
        EvidenceQuery(
            text="Vexira explain the summoning ritual and the Unmaker at the Vanta Gate",
            entity_ids=("npc:vexira", "location:vanta_gate", "lore:summoning"),
            access=EvidenceAccessContext(
                speaker_id="npc:vexira",
                actor_ids=("npc:vexira",),
                narrator_mode=True,
            ),
        )
    )
    selected = set(result.trace.selected_ids)
    assert "npc:vexira:personality" in selected
    assert "npc:vexira:belief:returned_unmaker" in selected
    assert "location:vanta_gate:mirrorstone" in selected
    assert "lore:summoning:ritual" in selected
    assert "npc:vexira:gm_secret" not in selected


def test_private_vexira_history_is_not_available_to_bran() -> None:
    result = _broker().retrieve(
        EvidenceQuery(
            text="What happened to Vexira at the Vanta Gate?",
            entity_ids=("npc:vexira", "location:vanta_gate"),
            access=EvidenceAccessContext(speaker_id="npc:bran", actor_ids=("npc:bran",)),
        )
    )
    selected = set(result.trace.selected_ids)
    assert "npc:vexira:history:gate_vigil" not in selected
    excluded = dict(result.trace.excluded)
    assert excluded["npc:vexira:history:gate_vigil"] == "npc_private"


def test_vexira_belief_does_not_become_objective_canon() -> None:
    result = _broker().retrieve(
        EvidenceQuery(
            text="Is the player the Unmaker?",
            entity_ids=("npc:vexira", "lore:unmaker"),
            access=EvidenceAccessContext(speaker_id="npc:vexira"),
        )
    )
    belief = next(record for record in result.evidence if record.evidence_id == "npc:vexira:belief:returned_unmaker")
    assert belief.authority is AuthorityClass.NPC_BELIEF


def test_retrieval_order_is_process_stable() -> None:
    query = EvidenceQuery(
        text="Bran road rain tavern",
        entity_ids=("npc:bran", "location:rusty_flagon"),
        access=EvidenceAccessContext(speaker_id="npc:bran", narrator_mode=True),
    )
    first = _broker().retrieve(query).trace.selected_ids
    second = _broker().retrieve(query).trace.selected_ids
    assert first == second
