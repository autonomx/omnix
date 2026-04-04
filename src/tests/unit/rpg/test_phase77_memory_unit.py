"""Phase 7.7 — Unit Tests for Memory / Read-Model Layer.

Tests for:
- All memory model roundtrips (JournalEntry, RecapSnapshot, CodexEntry, CampaignMemorySnapshot)
- JournalBuilder
- RecapBuilder
- CodexBuilder
- CampaignMemoryBuilder
- MemoryPresenter
- CampaignMemoryCore serialization/deserialization
"""

from __future__ import annotations

from app.rpg.memory.models import (
    JournalEntry,
    RecapSnapshot,
    CodexEntry,
    CampaignMemorySnapshot,
)
from app.rpg.memory.journal_builder import JournalBuilder
from app.rpg.memory.recap_builder import RecapBuilder
from app.rpg.memory.codex_builder import CodexBuilder
from app.rpg.memory.campaign_memory_builder import CampaignMemoryBuilder
from app.rpg.memory.presenters import MemoryPresenter
from app.rpg.memory.core import CampaignMemoryCore

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
    """Create a CoherenceCore with optional seeded state."""
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
    """Create a SocialStateCore with optional seeded state."""
    ssc = SocialStateCore()
    for rumor in kwargs.get("rumors", []):
        ssc.state.rumors[rumor.rumor_id] = rumor
    for rel in kwargs.get("relationships", []):
        ssc.state.relationships[rel.relationship_id] = rel
    for alliance in kwargs.get("alliances", []):
        ssc.state.alliances[alliance.alliance_id] = alliance
    return ssc


def _make_creator_canon_state(**kwargs):
    """Create a CreatorCanonState with optional seeded facts."""
    ccs = CreatorCanonState()
    for fact in kwargs.get("facts", []):
        ccs.add_fact(fact)
    return ccs


# ---------------------------------------------------------------------------
# Model roundtrip tests
# ---------------------------------------------------------------------------

class TestJournalEntryRoundtrip:
    def test_journal_entry_roundtrip(self):
        entry = JournalEntry(
            entry_id="je-1",
            tick=5,
            entry_type="action",
            title="Attack the guard",
            summary="The player attacked the guard.",
            entity_ids=["player", "guard_1"],
            thread_ids=["thread_1"],
            location="castle_gate",
            metadata={"source": "test"},
        )
        d = entry.to_dict()
        restored = JournalEntry.from_dict(d)
        assert restored.entry_id == "je-1"
        assert restored.tick == 5
        assert restored.entry_type == "action"
        assert restored.title == "Attack the guard"
        assert restored.summary == "The player attacked the guard."
        assert restored.entity_ids == ["player", "guard_1"]
        assert restored.thread_ids == ["thread_1"]
        assert restored.location == "castle_gate"
        assert restored.metadata == {"source": "test"}

    def test_journal_entry_defaults(self):
        entry = JournalEntry(
            entry_id="je-2",
            tick=None,
            entry_type="transition",
            title="Scene change",
            summary="Moved to the forest.",
        )
        d = entry.to_dict()
        restored = JournalEntry.from_dict(d)
        assert restored.entity_ids == []
        assert restored.thread_ids == []
        assert restored.location is None
        assert restored.metadata == {}


class TestRecapSnapshotRoundtrip:
    def test_recap_snapshot_roundtrip(self):
        recap = RecapSnapshot(
            snapshot_id="recap-1",
            tick=10,
            title="Session Recap",
            summary="The party explored the dungeon.",
            scene_summary={"location": "dungeon"},
            active_threads=[{"thread_id": "t1", "title": "Find the key"}],
            recent_consequences=[{"summary": "Door opened"}],
            social_highlights=[{"type": "rumor", "summary": "Whispers"}],
            metadata={"custom": True},
        )
        d = recap.to_dict()
        restored = RecapSnapshot.from_dict(d)
        assert restored.snapshot_id == "recap-1"
        assert restored.tick == 10
        assert restored.title == "Session Recap"
        assert restored.summary == "The party explored the dungeon."
        assert restored.scene_summary == {"location": "dungeon"}
        assert len(restored.active_threads) == 1
        assert len(restored.recent_consequences) == 1
        assert len(restored.social_highlights) == 1
        assert restored.metadata == {"custom": True}


class TestCodexEntryRoundtrip:
    def test_codex_entry_roundtrip(self):
        entry = CodexEntry(
            entry_id="codex-npc-1",
            entry_type="npc",
            title="Guard Captain",
            summary="Leader of the castle guard.",
            canonical=True,
            tags=["npc", "guard"],
            related_ids=["guard_captain"],
            metadata={"faction": "castle"},
        )
        d = entry.to_dict()
        restored = CodexEntry.from_dict(d)
        assert restored.entry_id == "codex-npc-1"
        assert restored.entry_type == "npc"
        assert restored.title == "Guard Captain"
        assert restored.summary == "Leader of the castle guard."
        assert restored.canonical is True
        assert restored.tags == ["npc", "guard"]
        assert restored.related_ids == ["guard_captain"]
        assert restored.metadata == {"faction": "castle"}

    def test_codex_entry_defaults(self):
        entry = CodexEntry(
            entry_id="codex-2",
            entry_type="lore",
            title="Ancient Prophecy",
            summary="A great darkness will return.",
        )
        d = entry.to_dict()
        restored = CodexEntry.from_dict(d)
        assert restored.canonical is True
        assert restored.tags == []
        assert restored.related_ids == []
        assert restored.metadata == {}


class TestCampaignMemorySnapshotRoundtrip:
    def test_campaign_memory_snapshot_roundtrip(self):
        snapshot = CampaignMemorySnapshot(
            snapshot_id="campaign-1",
            tick=20,
            title="Campaign Memory",
            current_scene={"location": "tavern"},
            active_threads=[{"thread_id": "t1"}],
            resolved_threads=[{"thread_id": "t0", "status": "resolved"}],
            major_consequences=[{"summary": "War began"}],
            social_summary={"relationship_count": 3},
            canon_summary={"fact_count": 5},
            metadata={"version": 1},
        )
        d = snapshot.to_dict()
        restored = CampaignMemorySnapshot.from_dict(d)
        assert restored.snapshot_id == "campaign-1"
        assert restored.tick == 20
        assert restored.title == "Campaign Memory"
        assert restored.current_scene == {"location": "tavern"}
        assert len(restored.active_threads) == 1
        assert len(restored.resolved_threads) == 1
        assert len(restored.major_consequences) == 1
        assert restored.social_summary == {"relationship_count": 3}
        assert restored.canon_summary == {"fact_count": 5}
        assert restored.metadata == {"version": 1}


# ---------------------------------------------------------------------------
# JournalBuilder tests
# ---------------------------------------------------------------------------

class TestJournalBuilder:
    def test_builds_action_entry(self):
        cc = _make_coherence_core()
        builder = JournalBuilder()
        resolution = {
            "resolved_action": {
                "action_id": "act-1",
                "title": "Strike the bandit",
                "summary": "Player struck the bandit with a sword.",
                "entity_ids": ["player", "bandit_1"],
                "location": "forest_clearing",
            },
            "consequences": [],
        }
        entries = builder.build_from_action_resolution(resolution, cc, tick=3)
        assert len(entries) == 1
        e = entries[0]
        assert e.entry_type == "action"
        assert e.title == "Strike the bandit"
        assert e.tick == 3
        assert "player" in e.entity_ids
        assert e.location == "forest_clearing"

    def test_builds_action_entry_with_consequences(self):
        cc = _make_coherence_core()
        builder = JournalBuilder()
        resolution = {
            "resolved_action": {
                "action_id": "act-2",
                "title": "Negotiate",
                "summary": "Negotiated with the merchant.",
                "entity_ids": ["player", "merchant"],
            },
            "consequences": [
                {"consequence_id": "c1", "summary": "Merchant agreed to lower prices.", "entity_ids": ["merchant"]},
            ],
        }
        entries = builder.build_from_action_resolution(resolution, cc, tick=4)
        assert len(entries) == 2
        assert entries[0].entry_type == "action"
        assert entries[1].title == "Consequence"
        assert entries[1].summary == "Merchant agreed to lower prices."

    def test_builds_scene_transition_entry(self):
        builder = JournalBuilder()
        transition = {"destination": "tavern", "reason": "Player entered the tavern."}
        entry = builder.build_from_scene_transition(transition, tick=5)
        assert entry is not None
        assert entry.entry_type == "transition"
        assert "tavern" in entry.title
        assert entry.location == "tavern"

    def test_scene_transition_returns_none_for_empty(self):
        builder = JournalBuilder()
        result = builder.build_from_scene_transition({}, tick=1)
        assert result is None

    def test_builds_thread_resolution_entry(self):
        thread = ThreadRecord(
            thread_id="t1",
            title="Find the key",
            status="resolved",
            resolved_tick=7,
            updated_tick=7,
            anchor_entity_ids=["player"],
        )
        cc = _make_coherence_core(threads=[thread])
        builder = JournalBuilder()
        entries = builder.build_from_thread_changes(cc, tick=7)
        assert len(entries) == 1
        assert entries[0].entry_type == "thread_resolution"
        assert "Find the key" in entries[0].title

    def test_builds_thread_progress_entry(self):
        thread = ThreadRecord(
            thread_id="t2",
            title="Defeat the dragon",
            status="unresolved",
            updated_tick=8,
            anchor_entity_ids=["dragon"],
        )
        cc = _make_coherence_core(threads=[thread])
        builder = JournalBuilder()
        entries = builder.build_from_thread_changes(cc, tick=8)
        assert len(entries) == 1
        assert entries[0].entry_type == "thread_progress"

    def test_builds_social_entries_from_rumors(self):
        rumor = RumorRecord(
            rumor_id="r1",
            source_npc_id="barkeep",
            subject_id="thief",
            rumor_type="gossip",
            summary="The thief was seen near the castle.",
            active=True,
        )
        ssc = _make_social_state_core(rumors=[rumor])
        builder = JournalBuilder()
        entries = builder.build_from_social_changes(ssc, tick=9)
        assert len(entries) == 1
        assert entries[0].entry_type == "rumor"
        assert "barkeep" in entries[0].entity_ids

    def test_social_changes_returns_empty_without_social(self):
        builder = JournalBuilder()
        entries = builder.build_from_social_changes(None, tick=10)
        assert entries == []

    def test_entry_id_deterministic(self):
        builder = JournalBuilder()
        id1 = builder._entry_id("action", 5, "act-1")
        id2 = builder._entry_id("action", 5, "act-1")
        assert id1 == id2
        assert id1 == "journal:action:5:act-1"


# ---------------------------------------------------------------------------
# RecapBuilder tests
# ---------------------------------------------------------------------------

class TestRecapBuilder:
    def test_builds_recap_from_state(self):
        cc = _make_coherence_core(
            threads=[
                ThreadRecord(thread_id="t1", title="Find the key", status="unresolved"),
            ],
            consequences=[
                ConsequenceRecord(consequence_id="c1", event_id="e1", tick=1, summary="Door opened"),
            ],
        )
        builder = RecapBuilder()
        recap = builder.build(cc, tick=10)
        assert recap.snapshot_id == "recap:10"
        assert recap.title == "Session Recap"
        assert "Find the key" in recap.summary
        assert len(recap.active_threads) == 1

    def test_builds_recap_with_social(self):
        cc = _make_coherence_core()
        rumor = RumorRecord(
            rumor_id="r1", source_npc_id="npc1", subject_id="npc2",
            rumor_type="gossip", summary="Big news", active=True,
        )
        ssc = _make_social_state_core(rumors=[rumor])
        builder = RecapBuilder()
        recap = builder.build(cc, social_state_core=ssc, tick=11)
        assert "rumor" in recap.summary.lower()
        assert len(recap.social_highlights) >= 1

    def test_recap_output_shape(self):
        cc = _make_coherence_core()
        builder = RecapBuilder()
        recap = builder.build(cc, tick=12)
        d = recap.to_dict()
        assert "snapshot_id" in d
        assert "summary" in d
        assert "scene_summary" in d
        assert "active_threads" in d
        assert "recent_consequences" in d
        assert "social_highlights" in d


# ---------------------------------------------------------------------------
# CodexBuilder tests
# ---------------------------------------------------------------------------

class TestCodexBuilder:
    def test_builds_npc_entries_from_facts(self):
        cc = _make_coherence_core(facts=[
            FactRecord(
                fact_id="npc:guard", category="npc", subject="guard_captain",
                predicate="is_npc", value=True, authority="engine_confirmed",
            ),
        ])
        builder = CodexBuilder()
        entries = builder.build_npc_entries(cc)
        assert len(entries) == 1
        assert entries[0].entry_type == "npc"
        assert entries[0].title == "guard_captain"

    def test_builds_npc_entries_from_commitments(self):
        cc = _make_coherence_core(commitments=[
            CommitmentRecord(
                commitment_id="c1", actor_id="innkeeper", target_id="player",
                kind="promise", text="Will provide info",
            ),
        ])
        builder = CodexBuilder()
        entries = builder.build_npc_entries(cc)
        assert len(entries) == 1
        assert entries[0].title == "innkeeper"

    def test_builds_npc_entries_from_social(self):
        cc = _make_coherence_core()
        rel = RelationshipStateRecord(
            relationship_id="rel1", source_id="player", target_id="blacksmith",
            trust=0.5,
        )
        ssc = _make_social_state_core(relationships=[rel])
        builder = CodexBuilder()
        entries = builder.build_npc_entries(cc, ssc)
        assert any(e.title == "blacksmith" for e in entries)

    def test_builds_faction_entries(self):
        cc = _make_coherence_core(facts=[
            FactRecord(
                fact_id="faction:guild", category="faction", subject="thieves_guild",
                predicate="is_faction", value=True, authority="engine_confirmed",
            ),
        ])
        builder = CodexBuilder()
        entries = builder.build_faction_entries(cc)
        assert len(entries) == 1
        assert entries[0].entry_type == "faction"

    def test_builds_location_entries(self):
        cc = _make_coherence_core(facts=[
            FactRecord(
                fact_id="loc:tavern", category="location", subject="tavern",
                predicate="is_location", value=True, authority="engine_confirmed",
            ),
        ])
        builder = CodexBuilder()
        entries = builder.build_location_entries(cc)
        assert len(entries) == 1
        assert entries[0].entry_type == "location"

    def test_builds_lore_entries(self):
        ccs = _make_creator_canon_state(facts=[
            CreatorCanonFact(
                fact_id="lore:prophecy", subject="ancient_prophecy",
                predicate="text", value="A great darkness will return.",
            ),
        ])
        builder = CodexBuilder()
        entries = builder.build_lore_entries(ccs)
        assert len(entries) == 1
        assert entries[0].entry_type == "lore"
        assert entries[0].canonical is True

    def test_builds_rumor_entries(self):
        rumor = RumorRecord(
            rumor_id="r1", source_npc_id="barkeep", subject_id="thief",
            rumor_type="gossip", summary="The thief was seen near the castle.",
            active=True,
        )
        ssc = _make_social_state_core(rumors=[rumor])
        builder = CodexBuilder()
        entries = builder.build_rumor_entries(ssc)
        assert len(entries) == 1
        assert entries[0].entry_type == "rumor"
        assert entries[0].canonical is False

    def test_builds_thread_entries(self):
        cc = _make_coherence_core(threads=[
            ThreadRecord(thread_id="t1", title="Find the key", status="unresolved"),
        ])
        builder = CodexBuilder()
        entries = builder.build_thread_entries(cc)
        assert len(entries) == 1
        assert entries[0].entry_type == "thread"

    def test_npc_entries_deduplicated(self):
        cc = _make_coherence_core(
            facts=[
                FactRecord(
                    fact_id="npc:guard", category="npc", subject="guard",
                    predicate="is_npc", value=True, authority="engine_confirmed",
                ),
            ],
            commitments=[
                CommitmentRecord(
                    commitment_id="c1", actor_id="guard", target_id="player",
                    kind="threat", text="Will attack",
                ),
            ],
        )
        builder = CodexBuilder()
        entries = builder.build_npc_entries(cc)
        assert len(entries) == 1

    def test_codex_output_sorted(self):
        cc = _make_coherence_core(facts=[
            FactRecord(fact_id="npc:z", category="npc", subject="zara", predicate="is_npc", value=True, authority="engine_confirmed"),
            FactRecord(fact_id="npc:a", category="npc", subject="alice", predicate="is_npc", value=True, authority="engine_confirmed"),
        ])
        builder = CodexBuilder()
        entries = builder.build_npc_entries(cc)
        assert entries[0].title == "alice"
        assert entries[1].title == "zara"


# ---------------------------------------------------------------------------
# CampaignMemoryBuilder tests
# ---------------------------------------------------------------------------

class TestCampaignMemoryBuilder:
    def test_builds_campaign_snapshot(self):
        cc = _make_coherence_core(
            threads=[
                ThreadRecord(thread_id="t1", title="Main quest", status="unresolved"),
                ThreadRecord(thread_id="t2", title="Side quest", status="resolved"),
            ],
            consequences=[
                ConsequenceRecord(consequence_id="c1", event_id="e1", tick=1, summary="Battle won"),
            ],
        )
        builder = CampaignMemoryBuilder()
        snapshot = builder.build(cc, tick=15)
        assert snapshot.snapshot_id == "campaign:15"
        assert snapshot.title == "Campaign Memory"
        assert len(snapshot.active_threads) == 1  # only unresolved
        assert len(snapshot.resolved_threads) == 1

    def test_builds_with_social_and_canon(self):
        cc = _make_coherence_core()
        ssc = _make_social_state_core(
            relationships=[
                RelationshipStateRecord(
                    relationship_id="rel1", source_id="player", target_id="npc1", trust=0.5,
                ),
            ],
            rumors=[
                RumorRecord(rumor_id="r1", source_npc_id="npc1", subject_id="npc2",
                            rumor_type="gossip", summary="News", active=True),
            ],
        )
        ccs = _make_creator_canon_state(facts=[
            CreatorCanonFact(fact_id="f1", subject="world", predicate="name", value="Testworld"),
        ])
        builder = CampaignMemoryBuilder()
        snapshot = builder.build(cc, ssc, ccs, tick=20)
        assert snapshot.social_summary.get("relationship_count") == 1
        assert snapshot.social_summary.get("active_rumor_count") == 1
        assert snapshot.canon_summary.get("fact_count") == 1

    def test_snapshot_output_shape(self):
        cc = _make_coherence_core()
        builder = CampaignMemoryBuilder()
        snapshot = builder.build(cc)
        d = snapshot.to_dict()
        assert "snapshot_id" in d
        assert "current_scene" in d
        assert "active_threads" in d
        assert "resolved_threads" in d
        assert "major_consequences" in d
        assert "social_summary" in d
        assert "canon_summary" in d


# ---------------------------------------------------------------------------
# MemoryPresenter tests
# ---------------------------------------------------------------------------

class TestMemoryPresenter:
    def test_present_journal_entries_ui_safe(self):
        presenter = MemoryPresenter()
        entries = [
            {"entry_id": "je-1", "entry_type": "action", "title": "Attack", "summary": "Hit", "tick": 1, "location": "forest"},
        ]
        result = presenter.present_journal_entries(entries)
        assert result["title"] == "Journal"
        assert result["count"] == 1
        assert len(result["items"]) == 1
        item = result["items"][0]
        assert "entry_id" in item
        assert "title" in item

    def test_present_recap_ui_safe(self):
        presenter = MemoryPresenter()
        recap = {
            "title": "Session Recap",
            "summary": "Things happened.",
            "scene_summary": {"location": "tavern"},
            "active_threads": [],
            "recent_consequences": [],
            "social_highlights": [],
        }
        result = presenter.present_recap(recap)
        assert result["title"] == "Session Recap"
        assert result["summary"] == "Things happened."

    def test_present_codex_ui_safe(self):
        presenter = MemoryPresenter()
        entries = [
            {"entry_id": "c1", "entry_type": "npc", "title": "Guard", "summary": "A guard", "canonical": True, "tags": ["npc"]},
        ]
        result = presenter.present_codex(entries)
        assert result["title"] == "Codex"
        assert result["count"] == 1

    def test_present_campaign_memory_ui_safe(self):
        presenter = MemoryPresenter()
        snapshot = {
            "title": "Campaign Memory",
            "current_scene": {"location": "castle"},
            "active_threads": [{"thread_id": "t1"}],
            "resolved_threads": [],
            "major_consequences": [],
            "social_summary": {},
            "canon_summary": {},
        }
        result = presenter.present_campaign_memory(snapshot)
        assert result["title"] == "Campaign Memory"
        assert len(result["active_threads"]) == 1

    def test_present_journal_entry(self):
        presenter = MemoryPresenter()
        entry = {"entry_id": "je-1", "entry_type": "action", "title": "Hit", "summary": "Player hit", "tick": 3, "location": "forest"}
        result = presenter.present_journal_entry(entry)
        assert result["entry_id"] == "je-1"
        assert result["title"] == "Hit"

    def test_present_codex_entry(self):
        presenter = MemoryPresenter()
        entry = {"entry_id": "c1", "entry_type": "npc", "title": "Guard", "summary": "A guard", "canonical": True, "tags": ["npc"]}
        result = presenter.present_codex_entry(entry)
        assert result["entry_id"] == "c1"
        assert result["canonical"] is True


# ---------------------------------------------------------------------------
# CampaignMemoryCore tests
# ---------------------------------------------------------------------------

class TestCampaignMemoryCore:
    def test_serialization_roundtrip(self):
        core = CampaignMemoryCore()
        cc = _make_coherence_core(
            threads=[ThreadRecord(thread_id="t1", title="Quest", status="unresolved")],
        )
        core.record_action_resolution(
            resolution={
                "resolved_action": {"action_id": "a1", "title": "Act", "summary": "Did it", "entity_ids": []},
                "consequences": [],
            },
            coherence_core=cc,
            tick=1,
        )
        core.refresh_recap(cc, tick=1)
        core.refresh_codex(cc)
        core.refresh_campaign_snapshot(cc, tick=1)

        data = core.serialize_state()
        core2 = CampaignMemoryCore()
        core2.deserialize_state(data)

        assert len(core2.journal_entries) == len(core.journal_entries)
        assert core2.last_recap is not None
        assert core2.last_recap.snapshot_id == core.last_recap.snapshot_id
        assert core2.last_campaign_snapshot is not None
        assert len(core2.codex_entries) == len(core.codex_entries)

    def test_set_mode(self):
        core = CampaignMemoryCore()
        core.set_mode("replay")
        assert core._mode == "replay"

    def test_record_multiple_actions(self):
        core = CampaignMemoryCore()
        cc = _make_coherence_core()
        for i in range(3):
            core.record_action_resolution(
                resolution={
                    "resolved_action": {"action_id": f"a{i}", "title": f"Act {i}", "summary": f"Did {i}", "entity_ids": []},
                    "consequences": [],
                },
                coherence_core=cc,
                tick=i,
            )
        assert len(core.journal_entries) == 3

    def test_refresh_recap_returns_presenter_shape(self):
        core = CampaignMemoryCore()
        cc = _make_coherence_core()
        result = core.refresh_recap(cc, tick=1)
        assert "title" in result
        assert "summary" in result
        assert "scene_summary" in result

    def test_refresh_codex_returns_presenter_shape(self):
        core = CampaignMemoryCore()
        cc = _make_coherence_core(facts=[
            FactRecord(fact_id="npc:guard", category="npc", subject="guard",
                       predicate="is_npc", value=True, authority="engine_confirmed"),
        ])
        result = core.refresh_codex(cc)
        assert "title" in result
        assert result["title"] == "Codex"
        assert "count" in result

    def test_refresh_campaign_snapshot_returns_presenter_shape(self):
        core = CampaignMemoryCore()
        cc = _make_coherence_core()
        result = core.refresh_campaign_snapshot(cc, tick=5)
        assert "title" in result
        assert result["title"] == "Campaign Memory"
        assert "current_scene" in result

    def test_empty_serialization(self):
        core = CampaignMemoryCore()
        data = core.serialize_state()
        core2 = CampaignMemoryCore()
        core2.deserialize_state(data)
        assert core2.journal_entries == []
        assert core2.last_recap is None
        assert core2.last_campaign_snapshot is None
        assert core2.codex_entries == {}
