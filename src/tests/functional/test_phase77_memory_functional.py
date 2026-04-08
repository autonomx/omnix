"""Phase 7.7 — Functional Tests for Memory / Read-Model Layer.

Tests that verify end-to-end behavior of memory layer integration
with coherence, social state, and creator canon systems.
"""

from __future__ import annotations

from app.rpg.coherence.core import CoherenceCore
from app.rpg.coherence.models import (
    CommitmentRecord,
    ConsequenceRecord,
    FactRecord,
    ThreadRecord,
)
from app.rpg.creator.canon import CreatorCanonFact, CreatorCanonState
from app.rpg.memory.core import CampaignMemoryCore
from app.rpg.memory.presenters import MemoryPresenter
from app.rpg.social_state.core import SocialStateCore
from app.rpg.social_state.models import (
    AllianceRecord,
    RelationshipStateRecord,
    RumorRecord,
)

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


# ---------------------------------------------------------------------------
# Functional tests
# ---------------------------------------------------------------------------

class TestActionResolutionRecordsJournalEntry:
    """Resolving an option produces journal entries through CampaignMemoryCore."""

    def test_action_resolution_records_journal_entry(self):
        cc = _make_coherence_core()
        ssc = _make_social_state_core()
        core = CampaignMemoryCore()

        resolution = {
            "resolved_action": {
                "action_id": "act-1",
                "title": "Sneak past the guards",
                "summary": "The player carefully snuck past the guards.",
                "entity_ids": ["player", "guard_1"],
                "location": "castle_gate",
            },
            "consequences": [
                {"consequence_id": "c1", "summary": "Guards remain unaware.", "entity_ids": ["guard_1"]},
            ],
        }

        core.record_action_resolution(resolution, cc, ssc, tick=1)

        assert len(core.journal_entries) >= 1
        action_entries = [e for e in core.journal_entries if e.entry_type == "action"]
        assert len(action_entries) >= 1
        assert action_entries[0].title == "Sneak past the guards"
        assert action_entries[0].tick == 1


class TestRecapPanelReflectsState:
    """Recap refresh reflects actual coherence/social state."""

    def test_recap_panel_reflects_current_scene_and_threads(self):
        cc = _make_coherence_core(
            threads=[
                ThreadRecord(thread_id="t1", title="Rescue the princess", status="unresolved"),
                ThreadRecord(thread_id="t2", title="Find the artifact", status="unresolved"),
            ],
            consequences=[
                ConsequenceRecord(consequence_id="c1", event_id="e1", tick=1, summary="Princess captured"),
            ],
        )
        rumor = RumorRecord(
            rumor_id="r1", source_npc_id="guard", subject_id="dragon",
            rumor_type="warning", summary="Dragon was spotted nearby", active=True,
        )
        ssc = _make_social_state_core(rumors=[rumor])

        core = CampaignMemoryCore()
        result = core.refresh_recap(cc, ssc, tick=5)

        assert result["title"] == "Session Recap"
        assert "Rescue the princess" in result["summary"]
        assert "rumor" in result["summary"].lower()
        assert len(result["active_threads"]) == 2
        assert len(result["social_highlights"]) >= 1


class TestCodexPanelIncludesEntries:
    """Codex refresh produces NPC/faction/location entries."""

    def test_codex_panel_includes_npc_and_location_entries(self):
        cc = _make_coherence_core(facts=[
            FactRecord(
                fact_id="npc:blacksmith", category="npc", subject="blacksmith",
                predicate="is_npc", value=True, authority="engine_confirmed",
            ),
            FactRecord(
                fact_id="loc:market", category="location", subject="market_square",
                predicate="is_location", value=True, authority="engine_confirmed",
            ),
        ])
        ccs = _make_creator_canon_state(facts=[
            CreatorCanonFact(fact_id="lore:dragon", subject="dragon_lore", predicate="text", value="Ancient dragon sleeps under the mountain."),
        ])

        core = CampaignMemoryCore()
        result = core.refresh_codex(cc, creator_canon_state=ccs)

        assert result["title"] == "Codex"
        assert result["count"] >= 3  # at least NPC, location, and lore
        entry_types = {item["entry_type"] for item in result["items"]}
        assert "npc" in entry_types
        assert "location" in entry_types
        assert "lore" in entry_types


class TestCampaignMemoryPanelReturnsPresented:
    """Campaign memory panel returns a UI-safe payload."""

    def test_campaign_memory_panel_returns_presented_snapshot(self):
        cc = _make_coherence_core(
            threads=[
                ThreadRecord(thread_id="t1", title="Active quest", status="unresolved"),
                ThreadRecord(thread_id="t2", title="Old quest", status="resolved"),
            ],
            consequences=[
                ConsequenceRecord(consequence_id="c1", event_id="e1", tick=1, summary="Major battle"),
            ],
        )
        ssc = _make_social_state_core(
            relationships=[
                RelationshipStateRecord(
                    relationship_id="rel1", source_id="player", target_id="merchant", trust=0.7,
                ),
            ],
        )
        ccs = _make_creator_canon_state(facts=[
            CreatorCanonFact(fact_id="f1", subject="world", predicate="name", value="Testworld"),
        ])

        core = CampaignMemoryCore()
        result = core.refresh_campaign_snapshot(cc, ssc, ccs, tick=10)

        assert result["title"] == "Campaign Memory"
        assert "current_scene" in result
        assert "active_threads" in result
        assert "resolved_threads" in result
        assert "major_consequences" in result
        assert "social_summary" in result
        assert "canon_summary" in result
        assert result["social_summary"].get("relationship_count") == 1
        assert result["canon_summary"].get("fact_count") == 1
