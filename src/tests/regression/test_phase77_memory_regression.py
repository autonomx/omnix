"""Phase 7.7 — Regression Tests for Memory / Read-Model Layer.

Tests that verify:
- Memory remains derived and deterministic
- Refreshing memory does not mutate coherence/social state
- Snapshot restore preserves journal/recap/codex continuity
- Repeated refresh with same state produces same output
"""

from __future__ import annotations

from app.rpg.memory.core import CampaignMemoryCore
from app.rpg.memory.codex_builder import CodexBuilder
from app.rpg.coherence.core import CoherenceCore
from app.rpg.coherence.models import (
    FactRecord,
    ThreadRecord,
    CommitmentRecord,
    ConsequenceRecord,
)
from app.rpg.social_state.core import SocialStateCore
from app.rpg.social_state.models import (
    RumorRecord,
    RelationshipStateRecord,
    AllianceRecord,
)
from app.rpg.creator.canon import CreatorCanonState, CreatorCanonFact


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_coherence_core(**kwargs):
    cc = CoherenceCore()
    for fact in kwargs.get("facts", []):
        cc.insert_fact(fact)
    for thread in kwargs.get("threads", []):
        cc.insert_thread(thread)
    for commitment in kwargs.get("commitments", []):
        cc.insert_commitment(commitment)
    for consequence in kwargs.get("consequences", []):
        cc.state.recent_changes.append(consequence)
    return cc


def _make_social_state_core(**kwargs):
    ssc = SocialStateCore()
    for rumor in kwargs.get("rumors", []):
        ssc.state.rumors[rumor.rumor_id] = rumor
    for rel in kwargs.get("relationships", []):
        ssc.state.relationships[rel.relationship_id] = rel
    for alliance in kwargs.get("alliances", []):
        ssc.state.alliances[alliance.alliance_id] = alliance
    return ssc


def _make_creator_canon_state(**kwargs):
    ccs = CreatorCanonState()
    for fact in kwargs.get("facts", []):
        ccs.add_fact(fact)
    return ccs


def _build_seeded_state():
    """Build a common set of seeded state for regression tests."""
    cc = _make_coherence_core(
        facts=[
            FactRecord(
                fact_id="npc:guard", category="npc", subject="guard",
                predicate="is_npc", value=True, authority="engine_confirmed",
            ),
            FactRecord(
                fact_id="loc:market", category="location", subject="market",
                predicate="is_location", value=True, authority="engine_confirmed",
            ),
        ],
        threads=[
            ThreadRecord(thread_id="t1", title="Main quest", status="unresolved"),
        ],
        consequences=[
            ConsequenceRecord(consequence_id="c1", event_id="e1", tick=1, summary="Battle won"),
        ],
    )
    ssc = _make_social_state_core(
        rumors=[
            RumorRecord(
                rumor_id="r1", source_npc_id="barkeep", subject_id="thief",
                rumor_type="gossip", summary="Thief spotted", active=True,
            ),
        ],
        relationships=[
            RelationshipStateRecord(
                relationship_id="rel1", source_id="player", target_id="guard", trust=0.3,
            ),
        ],
    )
    ccs = _make_creator_canon_state(facts=[
        CreatorCanonFact(fact_id="f1", subject="world", predicate="name", value="Testworld"),
    ])
    return cc, ssc, ccs


# ---------------------------------------------------------------------------
# Regression tests
# ---------------------------------------------------------------------------

class TestMemoryRefreshDoesNotMutateAuthoritativeState:
    """Memory refresh must not change coherence or social state."""

    def test_memory_refresh_does_not_mutate_authoritative_state(self):
        cc, ssc, ccs = _build_seeded_state()

        # Snapshot authoritative state before memory operations
        cc_snapshot = cc.serialize_state()
        ssc_snapshot = ssc.serialize_state()
        ccs_snapshot = ccs.serialize_state()

        core = CampaignMemoryCore()
        core.record_action_resolution(
            resolution={
                "resolved_action": {"action_id": "a1", "title": "Act", "summary": "Did it", "entity_ids": []},
                "consequences": [],
            },
            coherence_core=cc,
            social_state_core=ssc,
            tick=1,
        )
        core.refresh_recap(cc, ssc, ccs, tick=1)
        core.refresh_codex(cc, ssc, ccs)
        core.refresh_campaign_snapshot(cc, ssc, ccs, tick=1)

        # Verify authoritative state unchanged
        assert cc.serialize_state() == cc_snapshot
        assert ssc.serialize_state() == ssc_snapshot
        assert ccs.serialize_state() == ccs_snapshot


class TestMemoryOutputsDeterministicForSameState:
    """Repeated refresh with same state produces same output."""

    def test_memory_outputs_are_deterministic_for_same_state(self):
        cc, ssc, ccs = _build_seeded_state()
        core = CampaignMemoryCore()

        # First pass
        recap1 = core.refresh_recap(cc, ssc, ccs, tick=5)
        codex1 = core.refresh_codex(cc, ssc, ccs)
        snapshot1 = core.refresh_campaign_snapshot(cc, ssc, ccs, tick=5)

        # Second pass with identical state
        core2 = CampaignMemoryCore()
        recap2 = core2.refresh_recap(cc, ssc, ccs, tick=5)
        codex2 = core2.refresh_codex(cc, ssc, ccs)
        snapshot2 = core2.refresh_campaign_snapshot(cc, ssc, ccs, tick=5)

        assert recap1 == recap2
        assert codex1 == codex2
        assert snapshot1 == snapshot2


class TestCampaignMemoryCoreSurvivesSnapshotRestore:
    """Snapshot restore preserves journal/recap/codex continuity."""

    def test_campaign_memory_core_survives_snapshot_restore(self):
        cc, ssc, ccs = _build_seeded_state()
        core = CampaignMemoryCore()

        # Build up state
        core.record_action_resolution(
            resolution={
                "resolved_action": {"action_id": "a1", "title": "Fight", "summary": "Fought enemies", "entity_ids": ["player"]},
                "consequences": [{"consequence_id": "c1", "summary": "Enemies defeated", "entity_ids": ["enemy"]}],
            },
            coherence_core=cc,
            social_state_core=ssc,
            tick=1,
        )
        core.refresh_recap(cc, ssc, ccs, tick=1)
        core.refresh_codex(cc, ssc, ccs)
        core.refresh_campaign_snapshot(cc, ssc, ccs, tick=1)

        # Serialize and restore
        data = core.serialize_state()
        core2 = CampaignMemoryCore()
        core2.deserialize_state(data)

        # Verify continuity
        assert len(core2.journal_entries) == len(core.journal_entries)
        for i, entry in enumerate(core2.journal_entries):
            assert entry.entry_id == core.journal_entries[i].entry_id
            assert entry.title == core.journal_entries[i].title

        assert core2.last_recap is not None
        assert core2.last_recap.snapshot_id == core.last_recap.snapshot_id
        assert core2.last_recap.summary == core.last_recap.summary

        assert core2.last_campaign_snapshot is not None
        assert core2.last_campaign_snapshot.snapshot_id == core.last_campaign_snapshot.snapshot_id

        assert len(core2.codex_entries) == len(core.codex_entries)
        for key in core.codex_entries:
            assert key in core2.codex_entries
            assert core2.codex_entries[key].title == core.codex_entries[key].title


class TestCodexDeduplicatesEntriesDeterministically:
    """Codex entries are deduplicated deterministically."""

    def test_codex_deduplicates_entries_deterministically(self):
        # Create state with duplicate NPC references
        cc = _make_coherence_core(
            facts=[
                FactRecord(
                    fact_id="npc:guard_a", category="npc", subject="guard",
                    predicate="is_npc", value=True, authority="engine_confirmed",
                ),
                FactRecord(
                    fact_id="npc:guard_b", category="npc", subject="guard",
                    predicate="role", value="patrol", authority="engine_confirmed",
                ),
            ],
            commitments=[
                CommitmentRecord(
                    commitment_id="c1", actor_id="guard", target_id="player",
                    kind="threat", text="Will attack on sight",
                ),
            ],
        )

        builder = CodexBuilder()

        # Run multiple times
        entries1 = builder.build_npc_entries(cc)
        entries2 = builder.build_npc_entries(cc)

        # Should produce exactly 1 deduplicated entry for "guard"
        assert len(entries1) == 1
        assert entries1[0].title == "guard"

        # Should be deterministic
        assert len(entries1) == len(entries2)
        assert entries1[0].entry_id == entries2[0].entry_id
        assert entries1[0].title == entries2[0].title
